import os

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication

from clipstudio import updater
from clipstudio.db import Library
from clipstudio.settings import Settings
from clipstudio.ui.app import MainWindow
from clipstudio.ui.fx import MOTION

BASE = "https://github.com/Deba-dev/clip-studio/releases/download/"


def release(tag, prerelease=True, draft=False, asset=True, url=None):
    assets = [{"name": "ClipStudio-Setup.exe", "browser_download_url": url or BASE + tag + "/ClipStudio-Setup.exe",
               "digest": "sha256:abc"}] if asset else []
    return {"tag_name": tag, "prerelease": prerelease, "draft": draft, "assets": assets, "html_url": "page",
            "body": "## Title\n\n**Faster** clips now.\n\nMore."}


def test_version_order_is_numeric():
    assert updater.parse_version("v0.10.0") > updater.parse_version("v0.9.9")
    assert updater.parse_version("v0.3.1") == (0, 3, 1, 0)


def test_newest_prerelease_is_found():
    info = updater.pick_release([release("v0.3.2"), release("v0.4.0"), release("v0.3.1")], "0.3.1")
    assert info["version"] == "0.4.0" and info["notes"] == "Faster clips now." and info["digest"] == "sha256:abc"


def test_same_or_older_means_no_update():
    assert updater.pick_release([release("v0.3.1"), release("v0.2.0")], "0.3.1") is None


def test_a_release_still_building_is_skipped():
    info = updater.pick_release([release("v0.5.0", asset=False), release("v0.4.0")], "0.3.1")
    assert info["version"] == "0.4.0"


def test_drafts_are_skipped():
    assert updater.pick_release([release("v0.5.0", draft=True)], "0.3.1") is None


@pytest.mark.parametrize("url", ["https://evil.example/Deba-dev/clip-studio/releases/download/v1/Setup.exe",
                                 "http://github.com/Deba-dev/clip-studio/releases/download/v1/Setup.exe",
                                 "https://github.com/someone/clip-studio/releases/download/v1/Setup.exe",
                                 "https://github.com/Deba-dev/clip-studio/releases/download/../../../x/Setup.exe",
                                 "https://user@github.com/Deba-dev/clip-studio/releases/download/v1/Setup.exe"])
def test_only_this_repos_installer_is_accepted(url):
    assert not updater.is_release_asset(url)
    assert updater.pick_release([release("v9.0.0", url=url)], "0.3.1") is None


def test_a_bad_link_is_refused_before_any_download():
    with pytest.raises(ValueError, match="not downloaded"):
        updater.download({"version": "9", "asset": "https://evil.example/Setup.exe"})


def test_the_new_app_does_not_inherit_the_old_apps_environment(monkeypatch):
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", "x")
    monkeypatch.setenv("QT_PLUGIN_PATH", "x")
    env = updater.clean_env()
    assert "_PYI_APPLICATION_HOME_DIR" not in env and "QT_PLUGIN_PATH" not in env
    assert env["PYINSTALLER_RESET_ENVIRONMENT"] == "1"


@pytest.fixture
def window(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPSTUDIO_DATA", str(tmp_path))
    monkeypatch.setattr(updater.tempfile, "gettempdir", lambda: str(tmp_path))
    app = QApplication.instance() or QApplication([])
    library = Library(str(tmp_path / "lib.db"))
    w = MainWindow(library=library, settings=Settings(str(tmp_path / "s.json")), use_obs=False)
    launched = []
    w.updater.launch = launched.append
    monkeypatch.setattr(QApplication, "quit", staticmethod(lambda: None))
    w.launched = launched
    yield w
    MOTION.set(live=False)
    w.close()
    library.close()
    app.processEvents()


def test_a_finished_download_installs_when_nothing_is_happening(window):
    window.update_ready("setup.exe")
    assert window.launched == ["setup.exe"]


def test_no_install_during_a_stream_then_it_goes_when_the_stream_ends(window):
    MOTION.set(live=True)
    window.update_ready("setup.exe")
    assert window.launched == []
    MOTION.set(live=False)
    assert window.launched == ["setup.exe"]


def test_no_install_during_a_job(window):
    window.jobs.queue.append(("analyze", 1))
    window.update_ready("setup.exe")
    assert window.launched == []
    window.jobs.queue.clear()
    window.install_when_free()
    assert window.launched == ["setup.exe"]


def test_a_copy_run_from_source_opens_the_page_instead(window, monkeypatch):
    opened = []
    monkeypatch.setattr("clipstudio.ui.app.QDesktopServices.openUrl", lambda url: opened.append(url.toString()))
    window.update_found({"version": "9.0", "notes": "n", "page": "https://example.com/r", "asset": ""})
    window.start_update()
    assert opened == ["https://example.com/r"]


def test_an_unfinished_update_is_reported_and_old_installers_removed(window, tmp_path):
    window.settings.set("update_pending", "99.0.0")
    old = tmp_path / "ClipStudio-Setup-1.0.exe"
    old.write_bytes(b"x")
    assert "did not finish" in window.updater.after_start()
    assert not old.exists() and window.settings.get("update_pending") == ""
    assert window.updater.after_start() == ""
