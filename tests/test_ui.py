"""Opens the real window and the real card menu, so a menu can never ship without having been opened once."""
import os

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QMessageBox

from clipstudio.db import Library
from clipstudio.settings import Settings
from clipstudio.ui.app import MainWindow


@pytest.fixture
def window(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPSTUDIO_DATA", str(tmp_path))
    monkeypatch.setattr("clipstudio.ui.app.fx_trash", lambda path: False)       # tests never fill the Recycle Bin
    monkeypatch.setattr("clipstudio.ui.review.to_trash", lambda path: False)
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
    assert shown == ["OBS or Zunimi Studio, and live chat"]
    assert page.nav.hidden == {i for i, c in enumerate(page.cards) if c.title != "OBS or Zunimi Studio, and live chat"}
    page.search.setText("zunimi")
    assert [c.title for c in page.cards if not c.isHidden()] == ["OBS or Zunimi Studio, and live chat"]
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


def ready_stream(window, tmp_path, clips=3):
    source = tmp_path / "rec.mp4"
    source.write_bytes(b"x" * 10)
    sid = window.library.add_session("s", str(source))
    window.library.update_session(sid, status="ready")
    window.library.replace_clips(sid, [{"start": i * 20.0, "end": i * 20.0 + 10, "peak": i * 20.0 + 4, "score": 5.0 - i,
                                        "reasons": ["r"]} for i in range(clips)])
    return sid, source


def test_background_captions_never_look_like_the_analysis_starting_again(window, tmp_path):
    sid, _ = ready_stream(window, tmp_path)
    pipe = window.streams.pipeline
    window.jobs.current = ("analyze", sid)
    window.on_progress("Making previews", .5, "")
    window.library.update_clip(window.library.clips(sid)[0]["id"], captioned="0")
    window.on_job_done("analyze", sid, {"done": True})
    assert pipe.complete and pipe.stage == "Analysis complete" and pipe.button.isHidden()
    window.jobs.current = ("captions", sid)
    window.on_progress("Captioning more clips", .1, "1 of 3")
    assert pipe.complete and pipe.stage == "Analysis complete"      # the panel is untouched
    window.jobs.current = ("analyze", sid)
    window.on_progress("Reading the game", .2, "")                 # a stage mid-analysis never resets to Download
    assert not pipe.complete and pipe.stage == "Reading the game" and not pipe.button.isHidden()


def test_all_clips_changes_every_clip_and_undoes_in_one_step(window, tmp_path):
    sid, _ = ready_stream(window, tmp_path)
    review = window.review
    review.open(sid)
    review.scope.set("all")
    review.set_edit(gain_db=4.0, zoom=False)
    review.layout_changed("crop")
    assert all(c["edit"]["gain_db"] == 4.0 and not c["edit"]["zoom"] and c["layout"] == "crop"
               for c in window.library.clips(sid))
    review.set_edit(cuts=[[1.0, 2.0]])          # cuts are each clip's own, even in All clips
    assert sum(bool(c["edit"].get("cuts")) for c in window.library.clips(sid)) == 1
    review.undo()
    review.undo()
    assert all(c["layout"] != "crop" for c in window.library.clips(sid))
    review.scope.set("one")
    review.set_edit(fade_in=1.0)
    assert sum(c["edit"].get("fade_in") == 1.0 for c in window.library.clips(sid)) == 1


def test_removing_a_clip_deletes_its_export(window, tmp_path):
    sid, _ = ready_stream(window, tmp_path)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"v")
    (tmp_path / "clip.txt").write_text("title")
    first = window.library.clips(sid)[0]
    window.library.update_clip(first["id"], state="exported", exported=str(video))
    review = window.review
    review.open(sid)
    review.ask = lambda text: QMessageBox.StandardButton.Yes
    review.select(next(i for i, c in enumerate(review.cards) if c.clip["id"] == first["id"]))
    review.remove_clip()
    assert window.library.clip(first["id"]) is None and len(review.cards) == 2
    assert not video.exists() and not (tmp_path / "clip.txt").exists()
    assert [c["rank"] for c in window.library.clips(sid)] == [1, 2]


def test_removing_a_stream_deletes_its_recording_and_exports(window, tmp_path):
    from clipstudio.paths import session_thumb, signals_file
    sid, source = ready_stream(window, tmp_path)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"v")
    window.library.update_clip(window.library.clips(sid)[0]["id"], state="exported", exported=str(video))
    open(session_thumb(sid), "wb").close()
    open(signals_file(sid), "wb").close()
    twin = window.library.add_session("same file", str(source))    # a second entry for the same recording
    asked = []
    window.streams.ask = lambda text: asked.append(text) or QMessageBox.StandardButton.Yes
    window.streams.refresh()
    window.streams.remove(twin)
    assert source.exists()                      # still used by the other entry
    window.streams.remove(sid)
    assert "Recycle Bin" in asked[-1] and "1 exported clip" in asked[-1]
    assert window.library.session(sid) is None
    assert not source.exists() and not video.exists()
    assert not os.path.exists(session_thumb(sid)) and not os.path.exists(signals_file(sid))


def test_saying_no_keeps_the_stream_and_its_files(window, tmp_path):
    sid, source = ready_stream(window, tmp_path)
    window.streams.ask = lambda text: QMessageBox.StandardButton.No
    window.streams.remove(sid)
    assert window.library.session(sid) is not None and source.exists()


# ---- window modes, F11, Esc and the tray
def key(code):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    return QKeyEvent(QEvent.Type.KeyPress, code, Qt.KeyboardModifier.NoModifier)


def test_window_modes_switch_and_are_saved(window):
    from PySide6.QtCore import Qt
    window.modes.show()
    assert window.modes.current == "windowed"
    window.modes.set_mode("borderless")
    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint and window.settings.get("window_mode") == "borderless"
    assert window.settings_page.window_mode.currentData() == "borderless"
    window.modes.set_mode("fullscreen")
    assert window.isFullScreen()
    window.modes.set_mode("windowed")
    assert not window.isFullScreen() and not window.windowFlags() & Qt.WindowType.FramelessWindowHint
    window.modes.set_mode("nonsense")
    assert window.settings.get("window_mode") == "windowed"


def test_f11_and_esc_leave_fullscreen_without_saving_it(window):
    from PySide6.QtCore import Qt
    window.modes.show()
    window.keyPressEvent(key(Qt.Key.Key_F11))
    assert window.modes.current == "fullscreen" and window.settings.get("window_mode") == "windowed"
    window.keyPressEvent(key(Qt.Key.Key_Escape))
    assert window.modes.current == "windowed" and window.isVisible()


def test_close_and_esc_go_to_the_tray_when_there_is_one(window, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QCloseEvent
    window.modes.show()
    monkeypatch.setattr(window.modes, "tray_ready", lambda: True)
    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted() and not window.isVisible() and not window.closing
    assert window.settings.get("tray_hint_shown")
    window.modes.show_again()
    # Esc asks first; closing the question (Cancel, the default) keeps the window
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    window.keyPressEvent(key(Qt.Key.Key_Escape))
    assert window.isVisible()
    window.settings.set("esc_ask", False)
    window.keyPressEvent(key(Qt.Key.Key_Escape))
    assert not window.isVisible()
    window.settings.set("esc_to_tray", False)
    window.modes.show_again()
    window.keyPressEvent(key(Qt.Key.Key_Escape))
    assert window.isVisible()


def test_quitting_while_busy_asks_first(window, monkeypatch):
    from PySide6.QtGui import QCloseEvent
    window.settings.set("close_to_tray", False)
    monkeypatch.setattr(window.jobs, "busy", lambda: True)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted() and not window.closing
    monkeypatch.setattr(window.jobs, "busy", lambda: False)


def test_window_size_is_remembered(window):
    window.modes.show()
    window.resize(900, 640)
    window.modes.remember()
    assert window.settings.get("window_geometry")
