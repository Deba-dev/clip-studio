"""Removes what the app leaves behind, so it never slowly fills the user's drive.

Only files the app made itself are touched. Finished streams, exported clips, the library and settings are never
removed. Light cleanup runs at every start; the full one runs once after each update.
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
