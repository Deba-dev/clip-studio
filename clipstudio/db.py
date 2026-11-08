"""The local library: sessions, markers, chat, and clips, in one SQLite file."""
import json
import os
import sqlite3
import time

from .paths import data_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, source TEXT NOT NULL, created REAL NOT NULL,
    record_start REAL, duration REAL DEFAULT 0, status TEXT DEFAULT 'new', error TEXT DEFAULT '',
    chat_lag REAL, facecam TEXT DEFAULT '', language TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS markers (
    id INTEGER PRIMARY KEY, session INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    t REAL NOT NULL, kind TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS chat (
    id INTEGER PRIMARY KEY, session INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    t REAL NOT NULL, platform TEXT NOT NULL, author TEXT NOT NULL, text TEXT NOT NULL, added REAL NOT NULL);
CREATE TABLE IF NOT EXISTS clips (
    id INTEGER PRIMARY KEY, session INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    rank INTEGER NOT NULL, start REAL NOT NULL, end REAL NOT NULL, peak REAL NOT NULL, score REAL NOT NULL,
    reasons TEXT NOT NULL, title TEXT DEFAULT '', words TEXT DEFAULT '[]', layout TEXT DEFAULT 'auto',
    state TEXT DEFAULT 'new', exported TEXT DEFAULT '');
CREATE INDEX IF NOT EXISTS chat_by_session ON chat(session, t);
"""
CHAT_KEEP_DAYS = 30     # YouTube caps stored API data at 30 days; the clips keep what they need


class Library:
    def __init__(self, path=None):
        self.path = path or os.path.join(data_dir(), "library.db")
        self.con = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute("PRAGMA foreign_keys=ON")
        self.con.executescript(SCHEMA)
        columns = [r["name"] for r in self.con.execute("PRAGMA table_info(sessions)")]
        # view: where the game sits in the recording, "x,y,w,h". report: what the game reader saw, as JSON.
        for column in ("url", "folder", "game", "view", "report"):    # libraries made by older versions
            if column not in columns:
                self.con.execute("ALTER TABLE sessions ADD COLUMN %s TEXT DEFAULT ''" % column)
        columns = [r["name"] for r in self.con.execute("PRAGMA table_info(clips)")]
        # captioned: "1" once speech recognition has run on the clip. Clips made by older versions were all captioned.
        for column, empty in (("tags", "[]"), ("events", "[]"), ("edit", "{}"), ("captioned", "1")):
            if column not in columns:
                self.con.execute("ALTER TABLE clips ADD COLUMN %s TEXT DEFAULT '%s'" % (column, empty))

    def close(self):
        self.con.close()

    # ---- sessions
    def add_session(self, name, source, record_start=None, url="", folder=""):
        with self.con:
            cur = self.con.execute("INSERT INTO sessions(name, source, created, record_start, url, folder) "
                                   "VALUES (?,?,?,?,?,?)", (name, source, time.time(), record_start, url, folder))
        return cur.lastrowid

    def session(self, sid):
        return self.con.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()

    def sessions(self):
        return self.con.execute("SELECT s.*, (SELECT COUNT(*) FROM clips c WHERE c.session=s.id) AS clip_count "
                                "FROM sessions s ORDER BY created DESC, id DESC").fetchall()

    def update_session(self, sid, **fields):
        names = ", ".join(k + "=?" for k in fields)
        with self.con:
            self.con.execute("UPDATE sessions SET %s WHERE id=?" % names, (*fields.values(), sid))

    def delete_session(self, sid):
        """Removes the library entry only. The recording belongs to the streamer and stays on disk."""
        with self.con:
            self.con.execute("DELETE FROM sessions WHERE id=?", (sid,))

    # ---- signals
    def add_marker(self, sid, t, kind="hotkey"):
        with self.con:
            self.con.execute("INSERT INTO markers(session, t, kind) VALUES (?,?,?)", (sid, t, kind))

    def markers(self, sid):
        return [(r["t"], r["kind"]) for r in
                self.con.execute("SELECT t, kind FROM markers WHERE session=? ORDER BY t", (sid,))]

    def add_chat(self, sid, rows):
        """rows: (t, platform, author, text)"""
        now = time.time()
        with self.con:
            self.con.executemany("INSERT INTO chat(session, t, platform, author, text, added) VALUES (?,?,?,?,?,?)",
                                 [(sid, t, p, a, x, now) for t, p, a, x in rows])

    def chat(self, sid):
        return [(r["t"], r["platform"], r["author"], r["text"]) for r in
                self.con.execute("SELECT t, platform, author, text FROM chat WHERE session=? ORDER BY t", (sid,))]

    def purge_old_chat(self, days=CHAT_KEEP_DAYS):
        with self.con:
            return self.con.execute("DELETE FROM chat WHERE added<?", (time.time() - days * 86400,)).rowcount

    # ---- clips
    def replace_clips(self, sid, clips):
        """A re-analysis must never eat work: anything kept or exported survives untouched."""
        with self.con:
            self.con.execute("DELETE FROM clips WHERE session=? AND state='new'", (sid,))
            kept = self.con.execute("SELECT start, end FROM clips WHERE session=?", (sid,)).fetchall()
            rank = len(kept)
            for c in clips:
                if any(c["start"] < k["end"] and k["start"] < c["end"] for k in kept):
                    continue
                rank += 1
                self._insert(sid, rank, c)

    def _insert(self, sid, rank, c):
        self.con.execute(
            "INSERT INTO clips(session, rank, start, end, peak, score, reasons, title, words, tags, events, edit, "
            "captioned) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (sid, rank, c["start"], c["end"], c["peak"], c["score"], json.dumps(c["reasons"]),
             c.get("title", ""), json.dumps(c.get("words", [])), json.dumps(c.get("tags", [])),
             json.dumps(c.get("events", [])), json.dumps(c.get("edit") or {}),
             "1" if c.get("captioned", True) else "0"))

    def add_kill_clips(self, sid, clips):
        """Adds kill clips found later, by a taught model. Never touches a kept or exported clip.

        A new, untouched clip on the same moment that is not already a kill clip gives way to the kill clip, which
        inherits its tags and reasons. Returns how many clips were added.
        """
        added = 0
        with self.con:
            for c in clips:
                overlapping = [self._clip(r) for r in self.con.execute(
                    "SELECT * FROM clips WHERE session=? AND start<? AND end>?", (sid, c["end"], c["start"]))]
                if any("kills" in o["tags"] or o["state"] != "new" or o["edit"] for o in overlapping):
                    continue
                for o in overlapping:
                    c["tags"] = c["tags"] + [t for t in o["tags"] if t not in c["tags"]]
                    c["reasons"] = c["reasons"] + [r for r in o["reasons"] if r not in c["reasons"]]
                    self.con.execute("DELETE FROM clips WHERE id=?", (o["id"],))
                rank = self.con.execute("SELECT COALESCE(MAX(rank), 0) FROM clips WHERE session=?",
                                        (sid,)).fetchone()[0] + 1
                self._insert(sid, rank, dict(c, captioned=False))
                added += 1
        return added

    def clips(self, sid):
        return [self._clip(r) for r in
                self.con.execute("SELECT * FROM clips WHERE session=? ORDER BY rank", (sid,))]

    def uncaptioned(self, sid):
        """Clips still waiting for speech recognition, best first."""
        return [self._clip(r) for r in self.con.execute(
            "SELECT * FROM clips WHERE session=? AND captioned='0' ORDER BY rank", (sid,))]

    def clip(self, cid):
        row = self.con.execute("SELECT * FROM clips WHERE id=?", (cid,)).fetchone()
        return self._clip(row) if row else None

    @staticmethod
    def _clip(row):
        c = dict(row)
        c["reasons"] = json.loads(c["reasons"])
        c["words"] = json.loads(c["words"] or "[]")
        c["tags"] = json.loads(c.get("tags") or "[]")
        c["events"] = json.loads(c.get("events") or "[]")
        c["edit"] = json.loads(c.get("edit") or "{}")
        return c

    def split_clip(self, cid, t):
        """Makes two clips from one at time t. Returns the new clip's id. The second half sits right after the first."""
        c = self.clip(cid)
        with self.con:
            self.con.execute("UPDATE clips SET rank=rank+1 WHERE session=? AND rank>?", (c["session"], c["rank"]))
            self.con.execute("UPDATE clips SET end=? WHERE id=?", (t, cid))
            cur = self.con.execute(
                "INSERT INTO clips(session, rank, start, end, peak, score, reasons, title, words, tags, events, layout, edit, "
                "captioned) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (c["session"], c["rank"] + 1, t, c["end"], (t + c["end"]) / 2, c["score"], json.dumps(c["reasons"]),
                 (c["title"] + " (part 2)") if c["title"] else "", json.dumps(c["words"]), json.dumps(c["tags"]),
                 json.dumps(c["events"]), c["layout"], json.dumps(c["edit"]), c["captioned"]))
        return cur.lastrowid

    def join_clips(self, cid, other):
        """Undoes a split."""
        first, second = self.clip(cid), self.clip(other)
        with self.con:
            self.con.execute("UPDATE clips SET end=? WHERE id=?", (second["end"], cid))
            self.con.execute("DELETE FROM clips WHERE id=?", (other,))
            self.con.execute("UPDATE clips SET rank=rank-1 WHERE session=? AND rank>?", (first["session"], second["rank"]))

    def update_clip(self, cid, **fields):
        for key in ("words", "edit"):
            if key in fields:
                fields[key] = json.dumps(fields[key])
        names = ", ".join(k + "=?" for k in fields)
        with self.con:
            self.con.execute("UPDATE clips SET %s WHERE id=?" % names, (*fields.values(), cid))
