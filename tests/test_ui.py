"""Opens the real window and the real card menu, so a menu can never ship without having been opened once."""
import os

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from clipstudio.db import Library
from clipstudio.settings import Settings
from clipstudio.ui.app import MainWindow


@pytest.fixture
def window(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPSTUDIO_DATA", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    library = Library(str(tmp_path / "lib.db"))
    w = MainWindow(library=library, settings=Settings(str(tmp_path / "s.json")), use_obs=False)
    w.jobs.add = lambda job, target: None       # these tests look at menus, not real jobs
    yield w
    w.close()
    library.close()
    app.processEvents()


def open_menu(window, sid, monkeypatch):
    seen = []
    window.streams.show_menu = lambda menu, pos: seen.extend((a.text(), a.isEnabled()) for a in menu.actions())
    window.streams.refresh()
    window.streams.cards[sid].menu.emit(QPoint(0, 0))
    return dict(seen)


def test_menu_opens_on_a_failed_stream(window, monkeypatch):
    sid = window.library.add_session("s", "", url="https://x")
    window.library.update_session(sid, status="failed", error="no")
    assert open_menu(window, sid, monkeypatch) == {"Try again": True, "Add chat file": True, "Remove from list": True}


def test_menu_says_analyze_again_once_clips_exist(window, monkeypatch):
    sid = window.library.add_session("s", "v.mp4")
    window.library.update_session(sid, status="ready")
    window.library.replace_clips(sid, [{"start": 0.0, "end": 5.0, "peak": 2.0, "score": 1.0, "reasons": ["r"]}])
    assert "Analyze again" in open_menu(window, sid, monkeypatch)


@pytest.mark.parametrize("status", ["analyzing", "fetching"])
def test_a_busy_stream_cannot_be_started_twice_or_removed(window, monkeypatch, status):
    sid = window.library.add_session("s", "v.mp4")
    window.library.update_session(sid, status=status)
    assert not any(open_menu(window, sid, monkeypatch).values())


def test_a_second_job_on_the_same_stream_leaves_it_alone(window):
    sid = window.library.add_session("s", "v.mp4")
    window.library.update_session(sid, status="analyzing")
    window.on_job_done("analyze", sid, {"busy": True})
    assert window.library.session(sid)["status"] == "analyzing"
