"""Removes what the app leaves behind, so it never slowly fills the user's drive.

Only files the app made itself are touched. Finished streams, exported clips, the library and settings are never
removed by cleanup. Light cleanup runs at every start; the full one runs once after each update. The one exception is
at the end: when the user removes a stream or a clip from the list, its files go too (to the Recycle Bin).
"""
import glob
import os
import re
import shutil
import tempfile
import time

from . import upscale
from .paths import data_dir, downloads_dir, exports_dir
from .transcribe import LANGUAGE_MODEL, REPOS, adopt, cache_name, model_for, models_dir

STALE = 6 * 3600                # a leftover this old belongs to no running export or download
# yt-dlp's unfinished pieces: "Title [id].f299.mp4.part", "[id].mp4.ytdl", "[id].temp.mp4", "...part-Frag12"
PARTIAL = re.compile(r"\[([\w-]+)\][^\[\]]*\.(part|ytdl)(-Frag\d+)?$|\[([\w-]+)\]\.temp\.", re.I)


def size_of(path):
    if os.path.isfile(path):
        return os.path.getsize(path)
    total = 0
    for root, _, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def remove(path):
    """Returns the bytes freed, or 0 when the file is in use or already gone."""
    size = size_of(path)
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
    except OSError:
        return 0
    return size


def old(path, now):
    try:
        return now - os.path.getmtime(path) > STALE
    except OSError:
        return False


def light(settings, now=None):
    """Leftovers of exports that crashed or were stopped, and old installers. Cheap enough for every start."""
    now = now or time.time()
    freed = 0
    temp = glob.escape(tempfile.gettempdir())
    for path in glob.glob(os.path.join(temp, "clipstudio*")) + glob.glob(os.path.join(temp, "ClipStudio-Setup-*.exe")):
        if old(path, now):
            freed += remove(path)
    folder = settings.get("exports_folder") or exports_dir()
    for path in glob.glob(os.path.join(glob.escape(folder), "*.part.mp4")):
        if old(path, now):
            freed += remove(path)
    return freed


def needed_models(settings):
    chosen = settings.get("model")
    mode = "english" if settings.get("caption_mode") == "english" else "spoken"
    return {chosen, model_for(chosen, mode), LANGUAGE_MODEL}


def models(settings):
    """Speech models are up to 1.6 GB each. Only the ones the current settings use stay; others download if chosen."""
    for name in REPOS:
        try:
            adopt(name)             # take over models that older versions left in the shared folder
        except OSError:
            pass
    keep = {cache_name(n) for n in needed_models(settings) if n in REPOS}
    return sum(remove(os.path.join(models_dir(), entry)) for entry in os.listdir(models_dir())
               if entry.startswith("models--") and entry not in keep)


def old_tools():
    tools = os.path.join(data_dir(), "tools")
    if not os.path.isdir(tools):
        return 0
    return sum(remove(os.path.join(tools, n)) for n in os.listdir(tools)
               if n.startswith("realesrgan") and n != upscale.NAME)


def orphans(library):
    """Thumbnails, signals and locks of streams that were removed from the library."""
    alive = {row["id"] for row in library.sessions()}
    freed = 0
    patterns = ((os.path.join(data_dir(), "thumbs"), re.compile(r"^s(\d+)[_.]")),
                (os.path.join(data_dir(), "signals"), re.compile(r"^s(\d+)\.")),
                (data_dir(), re.compile(r"^session-(\d+)\.lock$")))
    for folder, pattern in patterns:
        if not os.path.isdir(folder):
            continue
        for name in os.listdir(folder):
            found = pattern.match(name)
            if found and int(found.group(1)) not in alive:
                freed += remove(os.path.join(folder, name))     # a lock still held is in use and stays
    return freed


def download_folders(library, settings):
    from .fetch import fixed_drives
    folders = {settings.get("downloads_folder") or "", downloads_dir()}
    folders |= {row["folder"] for row in library.sessions() if row["folder"]}
    folders |= {os.path.join(d, "Clip Studio", "Past streams") for d in fixed_drives()}
    return [f for f in folders if f and os.path.isdir(f)]


def partial_downloads(library, settings, now=None):
    """Half-downloaded streams stay only while that stream still waits to finish, because they let it resume."""
    now = now or time.time()
    waiting = [row["url"] for row in library.sessions() if row["url"] and not row["source"]]
    freed = 0
    for folder in download_folders(library, settings):
        for name in os.listdir(folder):
            found = PARTIAL.search(name)
            if not found:
                continue
            video_id = found.group(1) or found.group(4)
            if any(video_id in url for url in waiting):
                continue
            path = os.path.join(folder, name)
            if old(path, now):
                freed += remove(path)
    return freed


def full(library, settings):
    freed = 0
    for step in (lambda: light(settings), lambda: models(settings), old_tools, lambda: orphans(library),
                 lambda: partial_downloads(library, settings)):
        try:
            freed += step()
        except OSError:
            pass                    # one stuck folder must not stop the rest
    return freed


# ---- removing a stream or a clip the user took off the list
def concat_parts(path):
    """The recordings an OBS split-recording list joins."""
    parts = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("file '") and line.endswith("'"):
                    parts.append(os.path.normpath(line[6:-1].replace("'\''", "'")))
    except OSError:
        pass
    return parts


def _same(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def export_files(path):
    """An exported clip and the title-and-hashtags note saved next to it."""
    return [p for p in (path, os.path.splitext(path)[0] + ".txt") if path and os.path.isfile(p)]


def clip_files(library, clip):
    """What removing this clip deletes: its export (with its note) and its preview picture.

    A file another clip still uses stays: a split clip shares its preview, and two clips can never share an export,
    but a stale path must not take someone else's video with it.
    """
    from .paths import clip_thumb
    others = [c for c in library.clips(clip["session"]) if c["id"] != clip["id"]]
    files = []
    if clip["exported"] and not any(c["exported"] and _same(c["exported"], clip["exported"]) for c in others):
        files += export_files(clip["exported"])
    thumb = clip_thumb(clip["session"], clip["peak"])
    if os.path.isfile(thumb) and not any(int(c["peak"]) == int(clip["peak"]) for c in others):
        files.append(thumb)
    return files


def stream_files(library, sid):
    """What removing this stream deletes, as (recordings, exported clips with their notes, the app's own files).

    A recording another stream in the list also points at stays, so removing a duplicate never breaks the other.
    """
    from .paths import signals_file, words_file
    session = library.session(sid)
    if session is None:
        return [], [], []
    in_use = []
    for row in library.sessions():
        if row["id"] != sid and row["source"]:
            in_use.append(row["source"])
            if row["source"].endswith(".ffconcat"):
                in_use += concat_parts(row["source"])
    source = session["source"] or ""
    recordings = concat_parts(source) if source.endswith(".ffconcat") else [source]
    recordings = [p for p in recordings if p and os.path.isfile(p) and not any(_same(p, u) for u in in_use)]
    exports = []
    for clip in library.clips(sid):
        if clip["exported"]:
            exports += [p for p in export_files(clip["exported"]) if not any(_same(p, e) for e in exports)]
    own = []
    if source.endswith(".ffconcat") and os.path.isfile(source):
        own.append(source)
    thumbs = os.path.join(data_dir(), "thumbs")
    if os.path.isdir(thumbs):
        own += [os.path.join(thumbs, n) for n in os.listdir(thumbs) if re.match(r"^s%d[_.]" % sid, n)]
    for path in (signals_file(sid), words_file(sid), os.path.join(data_dir(), "compile-%d.json" % sid),
                 os.path.join(data_dir(), "session-%d.lock" % sid)):
        if os.path.isfile(path):
            own.append(path)
    return recordings, exports, own


def discard(paths, trash=None):
    """Deletes files, through `trash` (the Recycle Bin) when given. Returns the ones that could not be deleted."""
    stuck = []
    for path in paths:
        if not os.path.exists(path):
            continue
        try:
            if trash and trash(path):
                continue
            remove_or_raise(path)
        except OSError:
            stuck.append(path)      # open in a player, or on a drive that went away
    return stuck


def remove_or_raise(path):
    if os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)


def size_text(size):
    return "%.1f GB" % (size / 1e9) if size >= 1e9 else "%d MB" % max(round(size / 1e6), 1 if size else 0)
