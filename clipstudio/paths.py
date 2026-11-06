"""Where the app keeps its data, and how it finds FFmpeg."""
import os
import shutil
import sys


def data_dir():
    base = os.environ.get("CLIPSTUDIO_DATA") or os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "ClipStudio")
    os.makedirs(base, exist_ok=True)
    return base


def app_dir():
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def tool(name):
    """A bundled copy in tools/ wins over one on PATH, so a release never depends on the user's setup."""
    exe = name + (".exe" if sys.platform == "win32" else "")
    bundled = os.path.join(app_dir(), "tools", exe)
    return bundled if os.path.isfile(bundled) else (shutil.which(name) or name)


def exports_dir():
    path = os.environ.get("CLIPSTUDIO_EXPORTS") or os.path.join(os.path.expanduser("~"), "Videos", "Clip Studio")
    os.makedirs(path, exist_ok=True)
    return path


def downloads_dir():
    path = os.path.join(exports_dir(), "Past streams")
    os.makedirs(path, exist_ok=True)
    return path


def _sub(name):
    path = os.path.join(data_dir(), name)
    os.makedirs(path, exist_ok=True)
    return path


def session_thumb(sid):
    return os.path.join(_sub("thumbs"), "s%d.jpg" % sid)


def clip_thumb(sid, peak):
    return os.path.join(_sub("thumbs"), "s%d_%d.jpg" % (sid, int(peak)))


def signals_file(sid):
    return os.path.join(_sub("signals"), "s%d.npz" % sid)
