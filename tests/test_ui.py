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


@pytest.mark.parametrize("status", ["analyzing", "fetching"])
def test_an_analysis_cut_short_by_closing_is_cancelled_not_resumed(window, status):
    """The app was closed or the PC shut down mid-analysis: the next launch must not start it again by itself."""
    sid = window.library.add_session("s", "v.mp4")
    window.library.update_session(sid, status=status)
    started = []
    window.jobs.add = lambda job, target: started.append((job, target))
    window.recover_interrupted()
    assert started == []
    assert window.library.session(sid)["status"] == "stopped"
    assert "closed" in window.library.session(sid)["error"]


def test_closing_mid_analysis_says_why_it_stopped(window):
    sid = window.library.add_session("s", "v.mp4")
    window.library.update_session(sid, status="analyzing")
    window.closing = True
    window.on_job_done("analyze", sid, {"cancelled": True})
    assert window.library.session(sid)["status"] == "stopped"
    assert "closed" in window.library.session(sid)["error"]


def test_the_pause_button_turns_into_resume(window):
    pipe = window.streams.pipeline
    pipe.set_paused(True)
    assert pipe.pause_button.text() == "Resume" and pipe.paused
    pipe.set_paused(False)
    assert pipe.pause_button.text() == "Pause" and not pipe.paused


def test_the_preview_scales_each_frame_once_not_on_every_repaint(window):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage
    phone = window.review.phone
    phone.frame = QImage(1920, 1080, QImage.Format.Format_RGB32)
    phone.serial += 1
    phone.source_size = (1920, 1080)
    phone.facecam = (1440, 0, 480, 270)
    s = QRectF(0, 0, 270, 480)
    phone.prepare(s)
    tiny, cam = phone.tiny, phone.cam_image
    assert tiny.size().width() == 48 and not cam.isNull()
    phone.prepare(s)
    assert phone.tiny is tiny and phone.cam_image is cam      # same frame, same size: nothing is scaled again
    phone.serial += 1
    phone.prepare(s)
    assert phone.tiny is not tiny                                # a new frame is


def test_review_shows_zooms_hook_and_search(window):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter
    sid = window.library.add_session("s", "missing.mp4")
    window.library.update_session(sid, status="ready")
    words = [{"w": "अरे", "s": 3.0, "e": 3.3}, {"w": "भाई", "s": 3.4, "e": 3.8}]
    window.library.replace_clips(sid, [
        {"start": 0.0, "end": 10.0, "peak": 4.0, "score": 5.0, "reasons": ["r"], "title": "Double kill",
         "words": words, "events": [{"t": 4.0, "kind": "kill"}, {"t": 5.0, "kind": "kill"}, {"t": 6.0, "kind": "laugh"}]},
        {"start": 20.0, "end": 30.0, "peak": 24.0, "score": 4.0, "reasons": ["r"], "title": "Quiet", "words": []}])
    review = window.review
    review.open(sid)
    review.select(0)
    assert "2 kills" in review.zoom_note.text() and review.zoom.isChecked()
    assert list(review.phone.zooms) == ["game"]             # no webcam marked, so the laugh does not zoom

    review.hook_box.setText("Bhai ye kya tha")
    review.hook_done()
    first = review.clip["id"]
    assert window.library.clip(first)["edit"]["hook"] == "Bhai ye kya tha"
    assert review.phone.hook == ["Bhai ye kya tha"]
    review.hook_box.setText("typed but not saved")
    review.select(1)                                         # leaving a clip keeps what was typed, on that clip
    assert window.library.clip(first)["edit"]["hook"] == "typed but not saved"
    assert review.hook_box.text() == "" and review.clip["id"] != first

    review.zoom.setChecked(False)
    assert window.library.clip(review.clip["id"])["edit"]["zoom"] is False

    review.search.setText("bhai")
    assert [c.isVisibleTo(review) for c in review.cards] == [True, False]
    review.search.setText("")
    assert all(c.isVisibleTo(review) for c in review.cards)

    review.select(0)
    phone = review.phone
    phone.frame = QImage(1920, 1080, QImage.Format.Format_RGB32)
    phone.serial += 1
    phone.source_size = (1920, 1080)
    image = QImage(270, 480, QImage.Format.Format_ARGB32)
    for layout in ("blur", "crop", "stack"):
        phone.layout_name = layout
        phone.facecam = (1440, 0, 480, 270) if layout == "stack" else None
        phone.zooms = {"game": [(3.0, 5.0)], "cam": [(3.0, 5.0)]}
        phone.set_time(4.0, 1.0)                              # zoomed, and inside the hook's seconds
        p = QPainter(image)
        phone.draw_video(p, QRectF(0, 0, 270, 480))
        phone.draw_hook(p, QRectF(0, 0, 270, 480))
        p.end()


def test_review_picks_a_game_and_teaches_kills(window, tmp_path):
    from clipstudio import teach
    sid = window.library.add_session("BGMI rush", "missing.mp4")
    window.library.update_session(sid, status="ready", report='{"reader": "", "why": "Top bar not found", '
                                                              '"layout": "vertical"}')
    window.library.replace_clips(sid, [{"start": 0.0, "end": 10.0, "peak": 4.0, "score": 5.0, "reasons": ["r"],
                                        "events": [{"t": 3.0, "kind": "kill"}, {"t": 5.0, "kind": "kill"}]}])
    review = window.review
    review.open(sid)
    assert "Top bar not found" in review.reader_line.text() and "vertical" in review.reader_line.text()
    assert not review.find_button.isEnabled()                       # no game chosen yet
    review.game_box.setCurrentIndex(review.game_box.findData("bgmi"))
    assert window.library.session(sid)["game"] == "BGMI"
    review.mark_kill()
    review.player.position = lambda: 9000
    review.mark_kill()
    assert len(teach.examples("bgmi")) == 2 and review.find_button.isEnabled()
    asked = []
    review.find_kills.connect(asked.append)
    review.find_every_kill()
    assert asked == [sid]
    assert [label for _, label in review.phone.tally] == ["KILL", "DOUBLE KILL"]


def test_settings_wait_in_the_save_bar_until_saved(window):
    page = window.settings_page
    assert not page.dirty() and page.bar.shown == 0
    page.game.set("bgmi")
    page.game.changed.emit("bgmi")
    page.length.setValue(30)
    assert page.dirty()
    page.discard()
    assert not page.dirty() and page.game.value() == "" and page.length.value() == 45
    page.game.set("valorant")
    page.game.changed.emit("valorant")
    page.save()
    assert window.settings.get("game") == "valorant" and not page.dirty()


def test_settings_search_and_side_menu(window):
    page = window.settings_page
    page.search.setText("webSocket")
    shown = [c.title for c in page.cards if not c.isHidden()]
    assert shown == ["OBS and live chat"]
    assert page.nav.hidden == {i for i, c in enumerate(page.cards) if c.title != "OBS and live chat"}
    page.search.setText("zzzz nothing")
    assert not page.nothing.isHidden()
    page.search.setText("")
    assert all(not c.isHidden() for c in page.cards)
    page.jump(3)
    assert page.nav.index == 3


def test_buttons_spin_while_busy_and_confirm_when_done(window):
    from clipstudio.ui.fx import Button
    b = Button("Save", "check", primary=True)
    clicked = []
    b.clicked.connect(lambda: clicked.append(1))
    b.set_busy(True)
    b.click()                       # a programmatic click still works; mouse clicks are what busy blocks
    assert b.busy
    b.done("Saved", 10)
    assert not b.busy and b.text() == "Saved" and b.icon_name == "check"
    b.undone()
    assert b.text() == "Save" and b.icon_name == "check"
    assert level_words() == ["Never", "Less", "Normal", "More", "Most"]


def level_words():
    from clipstudio.ui.settings_page import level_text
    return [level_text(v) for v in (0, 50, 100, 150, 200)]
