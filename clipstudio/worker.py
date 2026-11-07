"""Heavy work runs here, in its own low-priority process, so a native crash cannot take the app down.

The app starts `main.py --worker analyze <session>` or `--worker export <clip>` and reads JSON lines from stdout.
"""
import json
import os
import sys

from . import analyze, fetch, render
from .db import Library
from .paths import data_dir, downloads_dir, exports_dir
from .settings import Settings


def lower_priority():
    if sys.platform == "win32":
        import ctypes
        k = ctypes.windll.kernel32
        k.SetPriorityClass(k.GetCurrentProcess(), 0x00004000)   # BELOW_NORMAL_PRIORITY_CLASS


def say(**message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def parse_facecam(text):
    try:
        values = [int(v) for v in text.split(",")]
    except (AttributeError, ValueError):
        return None
    return tuple(values) if len(values) == 4 and values[2] > 0 and values[3] > 0 else None


def do_analyze(library, sid):
    try:
        analyze.run(library, sid, report=lambda stage, value: say(stage=stage, value=round(value, 3)))
        say(done=True)
    except Exception as e:
        library.update_session(sid, status="failed", error=str(e)[:300])
        say(error=str(e)[:300])
        return 1
    return 0


def do_fetch(library, sid):
    """Download a past stream, pick up its chat replay if there is one, then analyze it as usual."""
    session = library.session(sid)
    url = session["url"]
    folder = None
    video_id = ""
    try:
        say(stage="Downloading", value=0, note="Checking the link")
        info = fetch.inspect(url)
        library.update_session(sid, name=(info.get("title") or session["name"])[:120],
                               duration=float(info.get("duration") or 0))
        video_id = info.get("id") or ""
        # A folder the user picked is a promise: it is used or the job stops. Only automatic mode may look elsewhere.
        chosen = session["folder"] or Settings().get("downloads_folder")
        folder = fetch.choose_folder(chosen or downloads_dir(), fetch.size_of(info), video_id,
                                     drives=[] if chosen else None)
        os.makedirs(folder, exist_ok=True)
        say(stage="Downloading", value=0, note="Saving to " + folder)
        path = fetch.download(url, folder, lambda v, note: say(stage="Downloading", value=round(v, 3), note=note))
        library.update_session(sid, source=path)
        if fetch.platform_of(url) == "youtube" and not library.chat(sid):
            say(stage="Getting chat replay", value=0, note="")
            try:
                rows = fetch.youtube_chat(url, folder)
                if rows:
                    library.add_chat(sid, rows)
            except Exception:
                pass            # a stream with no chat replay is still a stream
    except Exception as e:
        message = str(e) if isinstance(e, ValueError) else fetch.friendly(e)
        if folder:
            fetch.clean_temp(folder, video_id)
            if fetch.free_space(folder) < 1e9:
                message = "The drive ran out of space. Free some space, then try again."
        library.update_session(sid, status="failed", error=message[:300])
        say(error=message[:300])
        return 1
    return do_analyze(library, sid)


def do_export(library, cid):
    from .media import probe
    clip = library.clip(cid)
    session = library.session(clip["session"])
    try:
        info = probe(session["source"])
        folder = Settings().get("exports_folder") or exports_dir()
        os.makedirs(folder, exist_ok=True)
        path = render.export_clip(session["source"], clip, (info["width"], info["height"]), folder,
                                  parse_facecam(session["facecam"]),
                                  lambda v: say(stage="Exporting", value=round(v, 3)), info["audio_tracks"] > 0)
        library.update_clip(cid, state="exported", exported=path)
        say(done=True, path=path)
    except Exception as e:
        say(error=str(e)[-300:])        # FFmpeg puts the actual reason at the end
        return 1
    return 0


def hold_session(sid):
    """One job per stream, even across app restarts. Windows drops the lock by itself if this process dies."""
    if os.name != "nt":
        return True
    import msvcrt
    handle = open(os.path.join(data_dir(), "session-%d.lock" % sid), "a+b")
    try:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        handle.close()
        return None
    return handle


def attach_streams():
    """A windowed .exe starts with no sys.stdout even when the app gave it a pipe, so reconnect to that pipe."""
    if sys.stdout is None and sys.platform == "win32":
        import ctypes
        import msvcrt
        ctypes.windll.kernel32.GetStdHandle.restype = ctypes.c_void_p
        handle = ctypes.windll.kernel32.GetStdHandle(-11)
        sys.stdout = os.fdopen(msvcrt.open_osfhandle(handle, os.O_WRONLY), "w", encoding="utf-8", errors="replace")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main(args):
    lower_priority()
    attach_streams()
    library = Library(os.environ.get("CLIPSTUDIO_DB") or None)
    job, target = args[0], int(args[1])
    lock = hold_session(target) if job in ("analyze", "fetch") else True
    if not lock:
        say(busy=True)
        return 0
    return {"analyze": do_analyze, "fetch": do_fetch, "export": do_export}[job](library, target)
