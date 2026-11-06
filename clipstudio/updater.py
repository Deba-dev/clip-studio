"""Update check and one-click update through GitHub Releases. Ported from ChatDoom's updater.

The list of releases is read instead of "latest", because GitHub's "latest" skips pre-releases.
"""
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.parse
import urllib.request

from PySide6.QtCore import QObject, Signal

from .paths import data_dir
from .version import VERSION

REPO = "Deba-dev/clip-studio"
API = "https://api.github.com/repos/%s/releases?per_page=20" % REPO
AGENT = "ClipStudio-updater"


def parse_version(text):
    """v1.2.3 -> (1, 2, 3, 0). Only the leading numbers count, so a suffix is never read as a version."""
    match = re.match(r"\s*[vV]?(\d+(?:\.\d+){0,3})", text or "")
    numbers = [int(x) for x in match.group(1).split(".")] if match else []
    return tuple(numbers + [0] * (4 - len(numbers)))


def is_release_asset(url):
    """Only a file from this repo's own releases may ever be downloaded and run."""
    parsed = urllib.parse.urlparse(url or "")
    path = urllib.parse.unquote(parsed.path)
    return (parsed.scheme == "https" and parsed.hostname == "github.com" and parsed.username is None
            and parsed.password is None and path.casefold().startswith(("/%s/releases/download/" % REPO).casefold())
            and all(part not in (".", "..") for part in path.split("/")))


def summary(notes):
    """The first real sentence of the release notes, for the banner."""
    for line in (notes or "").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return re.sub(r"[*`_]", "", line)[:140]
    return ""


def pick_release(releases, current=VERSION):
    """The newest published release with an installer that is newer than this app, or None."""
    best = None
    for release in releases:
        if release.get("draft"):
            continue
        version = parse_version(release.get("tag_name"))
        if version <= parse_version(current) or (best and version <= parse_version(best["version"])):
            continue
        asset = next((a for a in release.get("assets", []) if a.get("name", "").lower().endswith("setup.exe")), None)
        if asset and is_release_asset(asset.get("browser_download_url")):
            best = {"version": release["tag_name"].lstrip("vV"), "page": release.get("html_url", ""),
                    "asset": asset["browser_download_url"], "digest": asset.get("digest") or "",
                    "notes": summary(release.get("body"))}
    return best


def clean_env():
    """A frozen app passes on PyInstaller's own settings, which would make the new app load files as if it were the old one."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("_PYI", "_MEI", "QT_", "QML", "PYSIDE"))}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    bundle = getattr(sys, "_MEIPASS", "")
    if bundle:
        env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep) if not p.startswith(bundle))
    return env


def update_log():
    return os.path.join(data_dir(), "update.log")


def installer_path(version):
    return os.path.join(tempfile.gettempdir(), "ClipStudio-Setup-%s.exe" % version)


def download(info, on_progress=lambda value: None):
    """Returns the path of a fully checked installer. Raises ValueError with a plain reason otherwise."""
    if not is_release_asset(info.get("asset")):
        raise ValueError("That update did not come from Clip Studio's releases, so it was not downloaded.")
    path = installer_path(info["version"])
    request = urllib.request.Request(info["asset"], headers={"User-Agent": AGENT})
    sha, done = hashlib.sha256(), 0
    with urllib.request.urlopen(request, timeout=30) as response, open(path, "wb") as f:
        total = int(response.headers.get("Content-Length") or 0)
        while True:
            chunk = response.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            sha.update(chunk)
            done += len(chunk)
            if total:
                on_progress(done / total)
    want = (info.get("digest") or "").lower()
    if (total and done != total) or (want.startswith("sha256:") and want[7:] != sha.hexdigest()):
        os.remove(path)
        raise ValueError("The update did not download correctly, so it was thrown away. Please try again.")
    return path


class Updater(QObject):
    found = Signal(dict)
    nothing = Signal()              # a manual check found no newer version
    failed = Signal(str)
    progress = Signal(float)
    ready = Signal(str)             # path of a checked installer
    _event = Signal(str, object)    # from worker threads

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.frozen = bool(getattr(sys, "frozen", False))       # only the installed app can replace itself
        self.busy = False
        self._event.connect(self._on_event)

    def check(self, manual=False):
        if not self.busy:
            self.busy = True
            threading.Thread(target=self._check, args=(manual,), daemon=True).start()

    def _check(self, manual):
        try:
            request = urllib.request.Request(API, headers={"User-Agent": AGENT, "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(request, timeout=15) as response:
                info = pick_release(json.loads(response.read()))
            if info:
                self._event.emit("found", info)
            elif manual:
                self._event.emit("nothing", None)
        except Exception as e:
            if manual:      # a failed background check must never bother anyone
                self._event.emit("failed", "Could not check for updates (%s)" % str(e)[:60])
        finally:
            self._event.emit("idle", None)

    def install(self, info):
        if not self.busy:
            self.busy = True
            threading.Thread(target=self._download, args=(info,), daemon=True).start()

    def _download(self, info):
        try:
            path = download(info, lambda value: self._event.emit("progress", value))
            self.settings.set("update_pending", info["version"])
            self._event.emit("ready", path)
        except ValueError as e:
            self._event.emit("failed", str(e))
        except Exception as e:
            self._event.emit("failed", "The update download failed (%s)" % str(e)[:60])
        finally:
            self._event.emit("idle", None)

    def launch(self, path):
        flags = 0x00000008 if sys.platform == "win32" else 0        # DETACHED_PROCESS
        subprocess.Popen([path, "/SILENT", "/SP-", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS",
                          "/LOG=" + update_log()], close_fds=True, creationflags=flags, env=clean_env())

    def after_start(self):
        """Says if the last update did not finish, and removes old installers, which are over 200 MB each."""
        pending = self.settings.get("update_pending")
        message = ""
        if pending:
            self.settings.set("update_pending", "")
            if parse_version(VERSION) < parse_version(pending):
                message = "The update to %s did not finish, so you are still on %s." % (pending, VERSION)
        for path in glob.glob(os.path.join(glob.escape(tempfile.gettempdir()), "ClipStudio-Setup-*.exe")):
            try:
                os.remove(path)
            except OSError:
                pass
        return message

    def _on_event(self, kind, data):
        if kind == "idle":
            self.busy = False
        elif kind == "found":
            self.found.emit(data)
        elif kind == "nothing":
            self.nothing.emit()
        elif kind == "failed":
            self.failed.emit(data)
        elif kind == "progress":
            self.progress.emit(data)
        elif kind == "ready":
            self.ready.emit(data)
