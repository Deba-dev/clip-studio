"""Small JSON settings file. The OBS password is stored with Windows DPAPI, never as plain text."""
import base64
import ctypes
import json
import os
import sys

from .paths import data_dir

DEFAULTS = {
    "obs_host": "127.0.0.1", "obs_port": 4455, "obs_password": "",
    "twitch_channel": "", "kick_channel": "", "youtube_video": "",
    "model": "large-v3-turbo", "language": "", "roman_script": True, "caption_mode": "spoken",
    "want_funny": 100, "want_kills": 100, "want_deaths": 100, "want_hype": 100,
    "review_split": [],
    "max_clips": 12, "clip_length": 45, "reduce_motion": False,
    "downloads_folder": "", "exports_folder": "", "update_pending": "",
}
SECRET = {"obs_password"}


class _Blob(ctypes.Structure):
    _fields_ = [("size", ctypes.c_ulong), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(data, encrypt):
    crypt = ctypes.windll.crypt32
    buffer = ctypes.create_string_buffer(data, len(data))
    src = _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    out = _Blob()
    fn = crypt.CryptProtectData if encrypt else crypt.CryptUnprotectData
    if not fn(ctypes.byref(src), None, None, None, None, 0, ctypes.byref(out)):
        raise OSError("Windows could not protect this value")
    try:
        return ctypes.string_at(out.data, out.size)
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.c_void_p(ctypes.cast(out.data, ctypes.c_void_p).value))


def protect(text):
    raw = text.encode("utf-8")
    return base64.b64encode(_dpapi(raw, True) if sys.platform == "win32" else raw).decode("ascii")


def unprotect(text):
    raw = base64.b64decode(text)
    return (_dpapi(raw, False) if sys.platform == "win32" else raw).decode("utf-8")


class Settings:
    def __init__(self, path=None):
        self.path = path or os.path.join(data_dir(), "settings.json")
        try:
            with open(self.path, encoding="utf-8") as f:
                self.values = json.load(f)
        except (OSError, ValueError):
            self.values = {}

    def get(self, key):
        value = self.values.get(key, DEFAULTS.get(key))
        if key in SECRET and value:
            try:
                return unprotect(value)
            except (OSError, ValueError):
                return ""
        return value

    def set(self, key, value):
        self.values[key] = protect(value) if key in SECRET and value else value
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.values, f, indent=1)
        os.replace(tmp, self.path)
