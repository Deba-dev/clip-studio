"""The main window: stream library, OBS link, chat logging and settings."""
import ctypes
import ctypes.wintypes
import os
import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressBar,
                               QPushButton, QSpinBox, QStackedWidget, QVBoxLayout, QWidget)

from .. import chat, media
from ..db import Library
from ..obs import ObsClient, RecordingTracker
from ..paths import data_dir, exports_dir, tool
from ..settings import Settings
from ..version import PRODUCT_NAME, VERSION
from .jobs import Jobs
from .review import ReviewPage, clock
from .theme import QSS

HOTKEY_ID = 7301
VK_F9 = 0x78
WM_HOTKEY = 0x0312
VIDEO_FILTER = "Recordings (*.mp4 *.mkv *.mov *.flv *.ts *.webm)"
STATUS = {"new": "Waiting", "recording": "Recording", "analyzing": "Analyzing", "ready": "Ready", "failed": "Failed"}


class Bridge(QObject):
    """OBS and chat run on their own threads. Everything they report crosses to the UI thread here."""
    event = Signal(str, dict)
    status = Signal(str, bool)
    chat_status = Signal(str, str)


class HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, on_press):
        super().__init__()
        self.on_press = on_press

    def nativeEventFilter(self, kind, message):
        if kind == b"windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self.on_press()
        return False, 0


class StreamsPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.w = window
        title = QLabel("Your streams")
        title.setObjectName("h1")
        self.link = QLabel("Waiting for OBS...")
        self.link.setObjectName("mute")
        self.live = QLabel("Stream normally. When OBS stops recording, your shortlist builds itself. "
                           "Press F9 during a stream to mark a moment.")
        self.live.setObjectName("mute")
        self.live.setWordWrap(True)
        self.list = QListWidget()
        self.list.setSpacing(3)
        self.list.itemDoubleClicked.connect(lambda _: self.open_selected())
        self.list.currentRowChanged.connect(lambda _: self.update_buttons())
        self.open_button = QPushButton("Review clips")
        self.open_button.setObjectName("primary")
        self.open_button.clicked.connect(self.open_selected)
        add = QPushButton("Add a recording")
        add.clicked.connect(self.import_video)
        self.chat_button = QPushButton("Add chat file")
        self.chat_button.setToolTip("Twitch chat JSON from TwitchDownloader, or a CSV of seconds,author,text")
        self.chat_button.clicked.connect(self.import_chat)
        self.again = QPushButton("Analyze again")
        self.again.setToolTip("Clips you kept or exported stay as they are")
        self.again.clicked.connect(self.reanalyze)
        self.remove = QPushButton("Remove")
        self.remove.clicked.connect(self.remove_selected)
        row = QHBoxLayout()
        for button in (self.open_button, add, self.chat_button, self.again, self.remove):
            row.addWidget(button)
        row.addStretch()
        page = QVBoxLayout(self)
        page.setContentsMargins(24, 20, 24, 20)
        page.addWidget(title)
        page.addWidget(self.link)
        page.addWidget(self.live)
        page.addLayout(row)
        page.addWidget(self.list, 1)

    def refresh(self):
        current = self.selected()
        self.list.clear()
        for s in self.w.library.sessions():
            line = "%s\n%s  ·  %s  ·  %d clips" % (s["name"], STATUS.get(s["status"], s["status"]),
                                                  clock(s["duration"] or 0), s["clip_count"])
            if s["error"]:
                line += "  ·  " + s["error"]
            item = QListWidgetItem(line)
            item.setData(Qt.ItemDataRole.UserRole, s["id"])
            self.list.addItem(item)
            if s["id"] == current:
                self.list.setCurrentItem(item)
        if self.list.currentRow() < 0 and self.list.count():
            self.list.setCurrentRow(0)
        self.update_buttons()

    def selected(self):
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def update_buttons(self):
        sid = self.selected()
        session = self.w.library.session(sid) if sid else None
        for button in (self.chat_button, self.again, self.remove):
            button.setEnabled(bool(session))
        self.open_button.setEnabled(bool(session) and session["status"] == "ready")

    def open_selected(self):
        if self.open_button.isEnabled():
            self.w.open_review(self.selected())

    def import_video(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a recording", "", VIDEO_FILTER)
        if path:
            sid = self.w.library.add_session(os.path.splitext(os.path.basename(path))[0], path)
            self.w.analyze(sid)

    def import_chat(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a chat file", "", "Chat files (*.json *.csv *.txt)")
        if path:
            try:
                rows = chat.parse_chat_file(path)
            except (OSError, ValueError) as e:
                return QMessageBox.warning(self, PRODUCT_NAME, "Could not read that chat file: %s" % e)
            self.w.library.add_chat(self.selected(), rows)
            self.w.library.update_session(self.selected(), chat_lag=None)
            QMessageBox.information(self, PRODUCT_NAME, "Added %d messages. Press Analyze again to use them." % len(rows))

    def reanalyze(self):
        self.w.analyze(self.selected())

    def remove_selected(self):
        sid = self.selected()
        answer = QMessageBox.question(self, PRODUCT_NAME, "Remove this stream from the list?\n\n"
                                      "Your recording and exported clips stay on disk.")
        if answer == QMessageBox.StandardButton.Yes:
            self.w.library.delete_session(sid)
            self.refresh()


class SettingsPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.w = window
        s = window.settings
        title = QLabel("Settings")
        title.setObjectName("h1")
        self.host = QLineEdit(s.get("obs_host"))
        self.port = QSpinBox(maximum=65535, value=int(s.get("obs_port")))
        self.password = QLineEdit(s.get("obs_password"), echoMode=QLineEdit.EchoMode.Password)
        self.twitch = QLineEdit(s.get("twitch_channel"), placeholderText="your channel name")
        self.kick = QLineEdit(s.get("kick_channel"), placeholderText="your channel name or chatroom ID")
        self.youtube = QLineEdit(s.get("youtube_video"), placeholderText="this stream's live link")
        self.model = QComboBox()
        for label, value in (("Fast (small)", "small"), ("Balanced (medium)", "medium"),
                             ("Best (large-v3-turbo, needs a good GPU)", "large-v3-turbo")):
            self.model.addItem(label, value)
        self.model.setCurrentIndex(max(self.model.findData(s.get("model")), 0))
        self.language = QComboBox()
        for label, value in (("Detect by itself", ""), ("Hindi / Hinglish", "hi"), ("English", "en")):
            self.language.addItem(label, value)
        self.language.setCurrentIndex(max(self.language.findData(s.get("language")), 0))
        self.roman = QCheckBox("Write Hindi captions in Roman letters (bhai, kya)", checked=bool(s.get("roman_script")))
        self.clips = QSpinBox(minimum=1, maximum=40, value=int(s.get("max_clips")))
        self.length = QSpinBox(minimum=15, maximum=59, value=int(s.get("clip_length")), suffix=" s")
        form = QFormLayout()
        form.addRow("OBS address", self.host)
        form.addRow("OBS port", self.port)
        form.addRow("OBS WebSocket password", self.password)
        form.addRow("Twitch chat", self.twitch)
        form.addRow("Kick chat", self.kick)
        form.addRow("YouTube chat", self.youtube)
        form.addRow("Caption quality", self.model)
        form.addRow("Stream language", self.language)
        form.addRow("", self.roman)
        form.addRow("Clips per stream", self.clips)
        form.addRow("Usual clip length", self.length)
        save = QPushButton("Save")
        save.setObjectName("primary")
        save.clicked.connect(self.save)
        where = QLabel("Clips are saved to " + exports_dir() + ". Nothing leaves this PC.")
        where.setObjectName("mute")
        page = QVBoxLayout(self)
        page.setContentsMargins(24, 20, 24, 20)
        page.addWidget(title)
        page.addLayout(form)
        page.addWidget(save, 0, Qt.AlignmentFlag.AlignLeft)
        page.addWidget(where)
        page.addStretch()

    def save(self):
        for key, value in (("obs_host", self.host.text().strip()), ("obs_port", self.port.value()),
                           ("obs_password", self.password.text()), ("twitch_channel", self.twitch.text().strip()),
                           ("kick_channel", self.kick.text().strip()), ("youtube_video", self.youtube.text().strip()),
                           ("model", self.model.currentData()), ("language", self.language.currentData()),
                           ("roman_script", self.roman.isChecked()), ("max_clips", self.clips.value()),
                           ("clip_length", self.length.value())):
            self.w.settings.set(key, value)
        self.w.connect_obs()


class MainWindow(QMainWindow):
    def __init__(self, library=None, settings=None, use_obs=True):
        super().__init__()
        self.setWindowTitle("%s %s" % (PRODUCT_NAME, VERSION))
        self.resize(1240, 800)
        self.library = library or Library()
        self.settings = settings or Settings()
        self.jobs = Jobs(self.library.path)
        self.jobs.progress.connect(self.on_progress)
        self.jobs.finished.connect(self.on_job_done)
        self.jobs.idle.connect(lambda: self.bar_row.setVisible(False))
        self.bridge = Bridge()
        self.bridge.event.connect(self.on_obs_event)
        self.bridge.status.connect(self.on_obs_status)
        self.bridge.chat_status.connect(self.on_chat_status)
        self.tracker = RecordingTracker(self.library, self.recording_finished)
        self.logger = chat.ChatLogger(self.library, self.settings,
                                      lambda platform, text: self.bridge.chat_status.emit(platform, text))
        self.obs = None
        self.streaming = False
        self.held = []
        self.flush = QTimer(self, interval=5000, timeout=self.logger.flush)
        self.flush.start()

        self.streams = StreamsPage(self)
        self.review = ReviewPage(self.library)
        self.review.back.connect(lambda: self.goto(0))
        self.review.export.connect(lambda cid: self.jobs.add("export", cid))
        self.settings_page = SettingsPage(self)
        self.stack = QStackedWidget()
        for page in (self.streams, self.settings_page, self.review):
            self.stack.addWidget(page)

        side = QFrame(objectName="side")
        side.setFixedWidth(190)
        logo = QLabel(PRODUCT_NAME, objectName="logo")
        tag = QLabel("by ZunimiLabs", objectName="tag")
        self.nav = []
        col = QVBoxLayout(side)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(logo)
        col.addWidget(tag)
        for i, label in enumerate(("Streams", "Settings")):
            button = QPushButton(label, objectName="nav", checkable=True)
            button.clicked.connect(lambda _, i=i: self.goto(i))
            self.nav.append(button)
            col.addWidget(button)
        col.addStretch()

        self.bar_text = QLabel("")
        self.bar = QProgressBar(maximum=1000)
        self.bar_row = QWidget()
        bar = QHBoxLayout(self.bar_row)
        bar.setContentsMargins(20, 6, 20, 8)
        bar.addWidget(self.bar_text)
        bar.addWidget(self.bar, 1)
        self.bar_row.hide()
        main = QVBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.addWidget(self.stack, 1)
        main.addWidget(self.bar_row)
        root = QWidget(objectName="root")
        rows = QHBoxLayout(root)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(0)
        rows.addWidget(side)
        rows.addLayout(main, 1)
        self.setCentralWidget(root)
        self.goto(0)
        self.streams.refresh()
        self.recover_interrupted()
        if use_obs:
            self.connect_obs()
            self.register_hotkey()

    def recover_interrupted(self):
        """A session left 'analyzing' means the app or PC went down mid-job, so the job simply runs again."""
        for s in self.library.sessions():
            if s["status"] == "analyzing":
                self.analyze(s["id"])

    def goto(self, index):
        self.stack.setCurrentIndex(index)
        for i, button in enumerate(self.nav):
            button.setChecked(i == index)
        if index == 0:
            self.streams.refresh()

    def open_review(self, sid):
        self.goto(0)
        self.stack.setCurrentWidget(self.review)
        self.review.open(sid)

    # ---- OBS
    def connect_obs(self):
        if self.obs:
            self.obs.stop()
        s = self.settings
        self.obs = ObsClient(s.get("obs_host"), s.get("obs_port"), s.get("obs_password"),
                             self.bridge.event.emit, self.bridge.status.emit)
        self.obs.start()

    def on_obs_status(self, text, connected):
        self.streams.link.setText(text)

    def on_chat_status(self, platform, text):
        self.streams.link.setText("%s chat: %s" % (platform.title(), text))

    def on_obs_event(self, name, data):
        was_recording = self.tracker.sid
        self.tracker.handle(name, data)
        if self.tracker.sid and not was_recording:
            self.logger.start(self.tracker.sid, self.tracker.started)
            self.library.update_session(self.tracker.sid, status="recording")
            self.streams.refresh()
        if name == "StreamStateChanged":
            self.streaming = bool(data.get("outputActive"))
            if not self.streaming:
                for sid in self.held:
                    self.analyze(sid)
                self.held = []

    def recording_finished(self, sid):
        """Nothing heavy starts while the stream is still live. Stream quality comes first."""
        self.logger.stop()
        if self.streaming:
            self.held.append(sid)
            self.library.update_session(sid, status="new")
            self.streams.refresh()
        else:
            self.analyze(sid)

    def register_hotkey(self):
        if sys.platform != "win32":
            return
        self.hotkey = HotkeyFilter(self.mark_moment)
        QApplication.instance().installNativeEventFilter(self.hotkey)
        if not ctypes.windll.user32.RegisterHotKey(None, HOTKEY_ID, 0x4000, VK_F9):   # MOD_NOREPEAT
            self.streams.live.setText("F9 is taken by another app. Save a replay in OBS to mark moments instead.")

    def mark_moment(self):
        t = self.tracker.mark()
        if t is not None:
            self.streams.link.setText("Marked a moment at " + clock(t))

    # ---- jobs
    def analyze(self, sid):
        self.library.update_session(sid, status="analyzing", error="")
        self.streams.refresh()
        self.jobs.add("analyze", sid)

    def on_progress(self, stage, value):
        self.bar_row.show()
        self.bar_text.setText(stage)
        self.bar.setValue(int(value * 1000))

    def on_job_done(self, job, target, result):
        if job == "analyze":
            if "error" in result:
                self.library.update_session(target, status="failed", error=result["error"][:200])
            self.streams.refresh()
        elif "error" in result:
            QMessageBox.warning(self, PRODUCT_NAME, result["error"])
        if self.stack.currentWidget() is self.review and self.review.sid:
            self.review.reload()

    def closeEvent(self, event):
        self.review.save_words()
        self.logger.stop()
        self.jobs.stop()
        if self.obs:
            self.obs.stop()
        super().closeEvent(event)


def check_tools():
    from shutil import which
    return os.path.isfile(tool("ffmpeg")) or which(tool("ffmpeg")) is not None


def run(args):
    app = QApplication(sys.argv)
    app.setApplicationName(PRODUCT_NAME)
    app.setStyleSheet(QSS)
    if not check_tools():
        QMessageBox.critical(None, PRODUCT_NAME, "FFmpeg is missing, so recordings cannot be read.")
        return 1
    window = MainWindow()
    if "--selftest" in args:
        for i in range(window.stack.count()):
            window.stack.setCurrentIndex(i)
        app.processEvents()
        return 0
    window.show()
    return app.exec()
