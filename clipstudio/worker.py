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


class PlanLimit(Exception):
    """The free plan does not cover this stream. Carries the reason, so the app can offer Premium."""
    def __init__(self, reason, message):
        super().__init__(message)
        self.reason = reason


def check_plan(sid, duration):
    from .plans import Gate
    gate = Gate(Settings())
    reason = gate.stream_check(duration, sid)
    if reason:
        raise PlanLimit(reason, gate.stream_message(reason, duration))


def do_analyze(library, sid):
    try:
        from .media import probe
        check_plan(sid, probe(library.session(sid)["source"])["duration"])
    except PlanLimit as e:
        library.update_session(sid, status="failed", error=str(e)[:300])
        say(error=str(e)[:300], upgrade=e.reason)
        return 1
    except Exception:
        pass                    # an unreadable file fails properly inside the analysis, with its own message
    try:
        analyze.run(library, sid, report=lambda stage, value: say(stage=stage, value=round(value, 3)))
        say(done=True)
    except Exception as e:
        library.update_session(sid, status="failed", error=str(e)[:300])
        say(error=str(e)[:300])
        return 1
    return 0


def do_captions(library, sid):
    """Captions the clips analysis saved without a transcript. Stopped for exports, then started again."""
    try:
        analyze.caption_rest(library, sid,
                             report=lambda stage, value, note="": say(stage=stage, value=round(value, 3), note=note))
        say(done=True)
    except Exception as e:
        say(error=str(e)[:300])         # the clips stay; they simply keep waiting for captions
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
        check_plan(sid, float(info.get("duration") or 0))       # before a multi-GB download, not after
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
    except PlanLimit as e:
        library.update_session(sid, status="failed", error=str(e)[:300])
        say(error=str(e)[:300], upgrade=e.reason)
        return 1
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


def compile_request(sid):
    return os.path.join(data_dir(), "compile-%d.json" % sid)


def do_compile(library, sid):
    """One video from several clips, in stream order: each is rendered exactly as it exports, then joined.

    The clips share one encoder, size and frame rate, so they join without a second encode or any loss.
    """
    import shutil
    import subprocess
    import tempfile
    from .media import HIDE, probe
    from .paths import tool
    from .plans import Gate
    try:
        with open(compile_request(sid), encoding="utf-8") as f:
            request = json.load(f)
        session = library.session(sid)
        clips = [c for c in (library.clip(i) for i in request["clips"]) if c]
        clips.sort(key=lambda c: c["start"])
        if len(clips) < 2:
            raise ValueError("A compilation needs at least two clips.")
        settings = Settings()
        info = probe(session["source"])
        size, fps_choice, enhance = Gate(settings).export_options(
            str(settings.get("export_size")), 120 if settings.get("export_fps") == "source" else int(settings.get("export_fps")),
            settings.get("enhance"))
        out = render.SIZES.get(size, render.SIZES["1080"])
        fps = render.frame_rate("source" if fps_choice == 120 else fps_choice, info["fps"])
        folder = settings.get("exports_folder") or exports_dir()
        os.makedirs(folder, exist_ok=True)
        name = render.clean_name(request.get("title") or "Best of " + session["name"])
        final = os.path.join(folder, name + ".mp4")
        n = 2
        while os.path.exists(final):
            final = os.path.join(folder, "%s (%d).mp4" % (name, n))
            n += 1
        with tempfile.TemporaryDirectory(prefix="clipstudio") as tmp:
            parts = []
            for i, clip in enumerate(clips):
                part_dir = os.path.join(tmp, str(i))
                os.makedirs(part_dir)
                share = (i, len(clips))
                parts.append(render.export_clip(
                    session["source"], dict(clip, title="part"), (info["width"], info["height"]), part_dir,
                    parse_facecam(session["facecam"]),
                    lambda v, note="", share=share: say(stage="Making the compilation", value=round((share[0] + v) / share[1], 3),
                                                        note="Clip %d of %d" % (share[0] + 1, share[1])),
                    info["audio_tracks"] > 0, out=out, fps=fps, enhance=enhance,
                    caption_default=settings.get("caption_style_default")))
            listing = render_list = os.path.join(tmp, "parts.txt")
            with open(render_list, "w", encoding="utf-8") as f:
                for path in parts:
                    f.write("file '%s'\n" % path.replace("\\", "/").replace("'", "'\\''"))
            partial = final + ".part.mp4"
            done = subprocess.run([tool("ffmpeg"), "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", listing,
                                   "-c", "copy", "-movflags", "+faststart", partial],
                                  capture_output=True, text=True, errors="replace", creationflags=HIDE)
            if done.returncode:
                raise RuntimeError("Joining the clips failed: " + done.stderr.strip()[-200:])
            shutil.move(partial, final)
        os.remove(compile_request(sid))
        say(done=True, path=final)
    except Exception as e:
        say(error=str(e)[-300:])
        return 1
    return 0


def do_export(library, cid):
    from .media import probe
    clip = library.clip(cid)
    session = library.session(clip["session"])
    try:
        settings = Settings()
        if clip["captioned"] == "0":    # never export a clip without its captions
            from .transcribe import load_model, model_for
            say(stage="Exporting", value=0.0, note="Writing captions first")
            model = load_model(model_for(settings.get("model"), settings.get("caption_mode")))
            analyze.caption_stored(library, clip["session"], cid, model, settings)
            clip = library.clip(cid)
        info = probe(session["source"])
        folder = settings.get("exports_folder") or exports_dir()
        os.makedirs(folder, exist_ok=True)
        from .plans import Gate
        size, fps_choice, enhance = Gate(settings).export_options(str(settings.get("export_size")),
                                                                 120 if settings.get("export_fps") == "source"
                                                                 else int(settings.get("export_fps")),
                                                                 settings.get("enhance"))
        out = render.SIZES.get(size, render.SIZES["1080"])
        fps = render.frame_rate("source" if fps_choice == 120 else fps_choice, info["fps"])
        path = render.export_clip(session["source"], clip, (info["width"], info["height"]), folder,
                                  parse_facecam(session["facecam"]),
                                  lambda v, note="": say(stage="Exporting", value=round(v, 3), note=note),
                                  info["audio_tracks"] > 0,
                                  out=out, fps=fps, enhance=enhance,
                                  caption_default=settings.get("caption_style_default"))
        library.update_clip(cid, state="exported", exported=path)
        if Gate(settings).allowed("titles"):        # a ready-to-paste title and hashtags next to the video
            from . import insights
            try:
                with open(os.path.splitext(path)[0] + ".txt", "w", encoding="utf-8") as f:
                    f.write(insights.post_text(library.clip(cid), session["game"] or "", session["language"] or ""))
            except OSError:
                pass
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
    lock = hold_session(target) if job in ("analyze", "fetch", "captions") else True
    if not lock:
        say(busy=True)
        return 0
    return {"analyze": do_analyze, "fetch": do_fetch, "export": do_export, "captions": do_captions,
            "compile": do_compile}[job](library, target)
