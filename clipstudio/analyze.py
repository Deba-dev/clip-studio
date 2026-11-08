"""The post-stream pipeline. Three passes make it fast on any PC:

1. Audio, chat and hotkeys rank the whole stream in about the time FFmpeg takes to read the audio. Sound tagging rides
   along on that same read and finds laughter and gunfire.
2. The game picture is found inside the recording (a vertical stream stacks the webcam over a cropped game), and
   its keyframes are read for Valorant's own scoreboard, which is how kills and deaths are found. Every kill is then
   checked for being the streamer's own. Other games use the kill notice they were taught (teach.py).
3. Speech recognition then runs on the best clips first, so the review desk opens quickly. Every other moment found
   is saved as a clip too, and a separate background job captions those one by one afterwards.
"""
import json
import shutil

import numpy as np

from . import detect, games, hud, media, teach, view
from .paths import clip_thumb, session_thumb, signals_file
from .settings import Settings

WINDOW_PAD = 10         # extra audio around a candidate, so the transcript can find where the thought began
ALL_MOMENTS = 250       # a sanity cap on clips per stream: every kill round and every death is a clip now


def make_previews(source, sid, picks, report):
    for i, pick in enumerate(picks):
        report("Making previews", i / max(len(picks), 1))
        media.frame_png(source, pick["peak"], clip_thumb(sid, pick["peak"]), 480)
    if picks:
        try:
            shutil.copyfile(clip_thumb(sid, picks[0]["peak"]), session_thumb(sid))
        except OSError:
            pass


def make_tagger(duration):
    """Sound tagging is a bonus: without it, or offline on the first run, analysis still finishes."""
    try:
        from .sound import Tagger
        return Tagger(duration)
    except Exception:
        return None


def game_view(library, sid, source, info):
    """Where the game is in this recording, found once and remembered. Returns (area, layout, ffmpeg filter)."""
    size = (info["width"], info["height"])
    session = library.session(sid)
    area = view.parse(session["view"])
    layout = "remembered"
    if not area:
        area, layout = view.find_game_area(source, size, info["duration"])
        library.update_session(sid, view="%d,%d,%d,%d" % area)
    return area, layout, view.game_filter(area, size)


def which_game(settings, session):
    """The stream's own game if it has one, then the main game in Settings, then whatever the title names."""
    return games.key_of(session["game"]) or games.key_of(settings.get("game")) or games.guess(session["name"])


def read_game(source, info, report, vf="scale=1920:1080"):
    """Valorant's HUD through the game picture. Returns (game or None, a sentence on what was seen)."""
    try:
        times, slots, strips = hud.scan(source, info["duration"], lambda v: report("Reading the game", v), vf)
    except (OSError, ValueError, RuntimeError) as e:
        return None, "The video could not be read for the game: %s" % str(e)[:80]
    game = hud.read_game(times, slots, strips)
    return game, ("Followed %d rounds" % game["rounds"]) if game else hud.diagnose(times, slots)


def credit_kills(source, game, lanes, vf, report):
    """Looks at every kill for the streamer's own skull banner. Returns (own [(t, round)], team bursts)."""
    events = detect.located(game, lanes)
    deaths = {e["round"]: e["from"] for e in events if e["kind"] == "you_down"}
    groups = detect.bursts(events)
    own, team = [], []
    for i, burst in enumerate(groups):
        report("Checking kills", i / max(len(groups), 1))
        seen = hud.own_kills(source, burst[0]["at"] - 6, burst[-1]["at"] + 2, vf)
        times = detect.mine(seen, deaths.get(burst[0]["round"]))
        own += [(t, burst[0]["round"]) for t in times]
        if not times:
            team.append(burst)
    return own, team


def load_lanes(sid):
    """The sound lanes saved by analysis, for jobs that run later. Missing lanes read as silence."""
    try:
        with np.load(signals_file(sid)) as z:
            lanes = {k: z[k].astype(np.float32) for k in ("laugh", "gun") if k in z.files}
    except (OSError, ValueError):
        return None
    if not lanes:
        return None
    n = max(v.size for v in lanes.values())
    for k in ("laugh", "gun", "shout"):
        lanes.setdefault(k, np.zeros(n, dtype=np.float32))
    return lanes


def other_view(source):
    """The game filter for a recording outside this job's stream, found from the recording itself."""
    try:
        info = media.probe(source)
    except (OSError, RuntimeError, ValueError):
        return "scale=1920:1080"
    size = (info["width"], info["height"])
    return view.game_filter(view.find_game_area(source, size, info["duration"])[0], size)


def find_taught_kills(library, sid, report=lambda stage, value: None):
    """Teach a kill: learns from every kill marked for this stream's game, then finds them all in this stream.

    Returns (kills found, clips added, what was learned).
    """
    session = library.session(sid)
    key = games.key_of(session["game"])
    if not key:
        raise ValueError("Choose this stream's game in the review desk first.")
    source = session["source"]
    info = media.probe(source)
    _, _, vf = game_view(library, sid, source, info)
    marked = teach.examples(key)
    for e in marked:            # kills marked before a stream's game area was known
        if not e.get("view"):
            e["view"] = vf if e["source"] == source else other_view(e["source"])
    here = [e["t"] for e in marked if e["source"] == source]
    report("Learning your kill", 0.0)
    pos, after, before, negatives = teach.gather(marked, (source, vf, info["duration"], here),
                                                 lambda v: report("Learning your kill", v))
    model, message = teach.learn(pos, after, before, negatives, key)
    if model is None:
        raise ValueError(message)
    teach.save(key, model)
    lanes = load_lanes(sid)
    spans = teach.windows(lanes["gun"] if lanes else None, info["duration"])
    kills = teach.scan(source, vf, model, spans, lambda v: report("Finding every kill", v))
    moments = detect.fight_moments(kills, lanes, info["duration"], key)
    added = library.add_kill_clips(sid, moments)
    make_previews(source, sid, moments, report)
    seen = json.loads(session["report"] or "{}")
    seen.update(reader="taught", kills=len(kills), why="")
    library.update_session(sid, report=json.dumps(seen))
    return len(kills), added, message


def placeholder(pick):
    """A title for a clip that has no transcript yet. The transcript replaces it later."""
    return {"kills": "Kill", "deaths": "Death reaction", "funny": "Funny moment",
            "marked": "Marked moment"}.get((pick.get("tags") or ["hype"])[0], "Hype moment")


def caption(model, source, pick, settings, language, game="", refine=True, keep_title=True):
    """Speech recognition for one clip. refine=False keeps the clip's edges, for clips the user already changed.

    A title from the game (Kill, Death reaction) or from the user stays; otherwise the words spoken at the peak become
    the title.
    """
    from .transcribe import GAME_WORDS, transcribe_window
    mode = settings.get("caption_mode")
    start = max(pick["start"] - WINDOW_PAD, 0.0)
    length = pick["end"] - start + WINDOW_PAD
    words, _ = transcribe_window(model, source, start, length, language, bool(settings.get("roman_script")),
                                 task="translate" if mode == "english" else "transcribe", hotwords=GAME_WORDS.get(game))
    refine = refine and not (pick.get("edit") or {}).get("cuts")       # cuts only fit the clip's own edges
    out = detect.refine_with_words(pick, words) if refine else dict(pick)
    out["words"] = [w for w in words if w["e"] > out["start"] and w["s"] < out["end"]]
    own = pick.get("title") if keep_title else ""
    out["title"] = own or detect.title_from(words, pick["peak"]) or placeholder(pick)
    out["captioned"] = True
    return out


def caption_stored(library, sid, cid, model, settings):
    """Captions one saved clip. Edges move only for clips nobody has touched yet."""
    session, clip = library.session(sid), library.clip(cid)
    untouched = clip["state"] == "new" and not clip["edit"]
    # The placeholder only stood in for a transcript; a game title (Kill) or one the user typed is kept.
    keep = clip["title"] != placeholder(clip) or (clip["tags"] or [""])[0] in ("kills", "deaths")
    done = caption(model, session["source"], clip, settings, session["language"] or settings.get("language") or None,
                   session["game"], refine=untouched, keep_title=keep)
    fields = {"words": done["words"], "title": done["title"], "captioned": "1"}
    if untouched:
        fields.update(start=done["start"], end=done["end"], score=done["score"], reasons=json.dumps(done["reasons"]))
    library.update_clip(cid, **fields)


def caption_rest(library, sid, settings=None, report=lambda stage, value, note="": None):
    """The background pass: captions every clip analysis saved without a transcript, best first."""
    settings = settings or Settings()
    waiting = library.uncaptioned(sid)
    if not waiting:
        return 0
    from .transcribe import load_model, model_for
    report("Captioning more clips", 0.0, "Loading the speech model")
    model = load_model(model_for(settings.get("model"), settings.get("caption_mode")))
    total = len(waiting)
    for i, clip in enumerate(waiting):
        if library.clip(clip["id"]) is None:
            continue                # deleted while waiting
        caption_stored(library, sid, clip["id"], model, settings)
        report("Captioning more clips", (i + 1) / total, "%d of %d" % (i + 1, total))
    return total


def wanted(settings):
    return {name: int(settings.get("want_" + name)) / 100 for name in ("funny", "kills", "deaths", "hype")}


def run(library, sid, settings=None, report=lambda stage, value: None, model=None):
    settings = settings or Settings()
    session = library.session(sid)
    source = session["source"]
    library.update_session(sid, status="analyzing", error="")
    info = media.probe(source)
    library.update_session(sid, duration=info["duration"])

    report("Reading audio", 0.0)
    tagger = make_tagger(info["duration"])
    loud = media.loudness_per_second(source, on_progress=lambda v: report("Reading audio", v), total=info["duration"],
                                     tap=tagger.feed if tagger else None)
    lanes = tagger.finish() if tagger else None
    key = which_game(settings, session)
    area, layout, vf = game_view(library, sid, source, info)
    seen = {"layout": layout, "area": list(area), "game": games.name_of(key), "reader": "", "why": ""}
    game = None
    if key in ("", "valorant"):
        game, seen["why"] = read_game(source, info, report, vf)
        if game:
            key = "valorant"
            seen["reader"] = "valorant"
    report("Finding moments", 0.5)
    parts = detect.score_moments(loud, library.chat(sid), library.markers(sid), info["duration"],
                                 lag=session["chat_lag"])
    first = int(settings.get("max_clips"))
    picks = detect.pick_moments(parts, info["duration"], ALL_MOMENTS, int(settings.get("clip_length")))
    if game:        # lobbies and scoreboards can be loud, but nobody wants a clip of them
        picks = [p for p in picks if p["score"] >= 100 or hud.is_live(game, p["peak"])]
    moments = list(picks)
    if lanes:
        moments += detect.laugh_moments(lanes, info["duration"])
    lesson = teach.load(key) if key and not game else None
    if game:
        own, team = credit_kills(source, game, lanes, vf, report)
        moments += detect.game_moments(game, lanes, info["duration"], own, team, key)
        kinds = [e["kind"] for e in game["events"]]
        seen.update(rounds=game["rounds"], kills=len(own), team_kills=kinds.count("enemy_down") - len(own),
                    deaths=kinds.count("you_down"), clutches=kinds.count("clutch"))
    elif lesson is not None:
        spans = teach.windows(lanes["gun"] if lanes else None, info["duration"])
        kills = teach.scan(source, vf, lesson, spans, lambda v: report("Finding your kills", v))
        moments += detect.fight_moments(kills, lanes, info["duration"], key)
        seen.update(reader="taught", kills=len(kills), why="")
    elif key and key != "valorant":
        seen["why"] = ("%s is read from a kill notice you teach it once: pause on two of your kills in the review "
                       "desk and press This frame shows my kill." % games.name_of(key))
    weights = wanted(settings)
    picks = detect.select(moments, first, weights)          # the best, with a mix of kinds: captioned now
    rest = [m for m in detect.select(moments, ALL_MOMENTS, weights)
            if not any(detect.overlaps(m, p) for p in picks)]   # every other moment: captioned in the background
    library.update_session(sid, chat_lag=parts["lag"], game=games.name_of(key), report=json.dumps(seen))
    extra = {k: v.astype(np.float16) for k, v in (lanes or {}).items() if k in ("laugh", "gun")}
    np.savez_compressed(signals_file(sid), curve=parts["curve"].astype(np.float16), loud=loud.astype(np.float16),
                        events=json.dumps(game["events"] if game else []), **extra)

    report("Loading speech model", 0.0)
    mode = settings.get("caption_mode")
    if model is None and picks:
        from .transcribe import load_model, model_for
        model = load_model(model_for(settings.get("model"), mode))
    language = settings.get("language") or None
    if model is not False and picks and not language:
        report("Finding the language", 0.0)
        from .transcribe import stream_language
        language = stream_language(source, picks)
    done = []
    for i, pick in enumerate(picks):
        report("Writing captions", i / max(len(picks), 1))
        done.append(caption(model, source, pick, settings, language, games.name_of(key))
                    if model is not False else pick)
    done += [dict(m, title=m.get("title") or placeholder(m), captioned=False) for m in rest]
    done.sort(key=lambda p: p["score"], reverse=True)
    library.replace_clips(sid, done)
    make_previews(source, sid, done, report)
    library.update_session(sid, status="ready", language=language or "")
    library.purge_old_chat()
    report("Done", 1.0)
    return done
