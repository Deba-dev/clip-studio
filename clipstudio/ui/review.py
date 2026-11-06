"""The review desk: this is the product. Scan the shortlist, fix a trim, fix a word, export."""
import os
import tempfile

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from .. import media
from ..captions import apply_text
from .facecam import FacecamDialog

LAYOUTS = [("Auto", "auto"), ("Webcam above gameplay", "stack"), ("Full frame, blurred bars", "blur"),
           ("Centre crop", "crop")]
MARK = {"new": "", "kept": "✓ ", "skipped": "✕ ", "exported": "⬆ "}


def clock(t):
    t = int(t)
    return "%d:%02d:%02d" % (t // 3600, t // 60 % 60, t % 60)


class ReviewPage(QWidget):
    back = Signal()
    export = Signal(int)

    def __init__(self, library):
        super().__init__()
        self.library = library
        self.sid = None
        self.clip = None
        self.undo_stack = []
        self.loading = False

        self.title = QLabel("Review")
        self.title.setObjectName("h1")
        back = QPushButton("← Streams")
        back.clicked.connect(self.back)
        self.camera = QPushButton("Mark webcam")
        self.camera.clicked.connect(self.pick_facecam)
        self.export_kept = QPushButton("Export kept clips")
        self.export_kept.setObjectName("primary")
        self.export_kept.clicked.connect(self.export_all)
        head = QHBoxLayout()
        head.addWidget(back)
        head.addWidget(self.title, 1)
        head.addWidget(self.camera)
        head.addWidget(self.export_kept)

        self.list = QListWidget()
        self.list.setFixedWidth(330)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.currentRowChanged.connect(self.select_row)

        self.video = QVideoWidget()
        self.video.setMinimumHeight(300)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.player.positionChanged.connect(self.loop_preview)
        self.player.mediaStatusChanged.connect(self.media_ready)
        self.no_preview = QLabel("")
        self.no_preview.setObjectName("mute")

        self.why = QLabel("")
        self.why.setObjectName("why")
        self.why.setWordWrap(True)
        self.video.setMinimumWidth(320)

        self.start = self._time_box()
        self.end = self._time_box()
        self.length = QLabel("")
        self.length.setObjectName("mute")
        self.length.setWordWrap(True)
        lead = QPushButton("Add 5s of setup")
        lead.setToolTip("Most clips fail because the setup is cut off")
        lead.clicked.connect(lambda: self.change(start=max(self.clip["start"] - 5, 0)))
        tail = QPushButton("Add 3s after")
        tail.clicked.connect(lambda: self.change(end=self.clip["end"] + 3))
        self.undo_button = QPushButton("Undo")
        self.undo_button.clicked.connect(self.undo)
        trim = QHBoxLayout()
        for widget in (QLabel("Start"), self.start, QLabel("End"), self.end, lead, tail, self.undo_button):
            trim.addWidget(widget)
        trim.addStretch()

        self.layout_box = QComboBox()
        for label, value in LAYOUTS:
            self.layout_box.addItem(label, value)
        self.layout_box.currentIndexChanged.connect(self.layout_changed)
        self.keep = QPushButton("Keep  (K)")
        self.keep.clicked.connect(lambda: self.set_state("kept"))
        self.skip = QPushButton("Skip  (X)")
        self.skip.clicked.connect(lambda: self.set_state("skipped"))
        self.export_one = QPushButton("Export this clip")
        self.export_one.clicked.connect(lambda: self.clip and self.export.emit(self.clip["id"]))
        self.open_file = QPushButton("Show file")
        self.open_file.clicked.connect(self.show_file)
        actions = QHBoxLayout()
        for widget in (QLabel("Layout"), self.layout_box, self.keep, self.skip, self.export_one, self.open_file):
            actions.addWidget(widget)
        actions.addStretch()

        self.words = QPlainTextEdit()
        self.words.setPlaceholderText("No speech found in this clip. It will export without captions.")
        self.words.setFixedHeight(84)
        self.save_timer = QTimer(self, singleShot=True, interval=500, timeout=self.save_words)
        self.words.textChanged.connect(lambda: None if self.loading else self.save_timer.start())

        right = QVBoxLayout()
        right.addWidget(self.video, 1)
        right.addWidget(self.no_preview)
        right.addWidget(self.why)
        right.addLayout(trim)
        right.addWidget(self.length)
        right.addLayout(actions)
        right.addWidget(self.words)
        body = QHBoxLayout()
        body.addWidget(self.list)
        body.addLayout(right, 1)
        page = QVBoxLayout(self)
        page.setContentsMargins(20, 16, 20, 16)
        page.addLayout(head)
        page.addLayout(body, 1)

        for key, action in (("K", lambda: self.set_state("kept")), ("X", lambda: self.set_state("skipped")),
                            ("Space", self.toggle), ("Ctrl+Z", self.undo), ("Down", lambda: self.step(1)),
                            ("Up", lambda: self.step(-1))):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(action)

    def _time_box(self):
        box = QDoubleSpinBox()
        box.setDecimals(1)
        box.setSingleStep(0.5)
        box.setMaximum(10 ** 6)
        box.setSuffix(" s")
        box.editingFinished.connect(self.trim_changed)
        return box

    # ---- loading
    def open(self, sid):
        self.save_words()
        self.sid = sid
        self.undo_stack = []
        session = self.library.session(sid)
        self.title.setText(session["name"])
        source = session["source"]
        split = source.endswith(".ffconcat")
        self.no_preview.setText("Preview is not available yet for recordings OBS split into parts. Exports still work."
                                if split else "")
        self.player.setSource(QUrl() if split else QUrl.fromLocalFile(source))
        self.clip = None
        self.list.clear()
        self.reload()
        self.select_row(0)

    def reload(self):
        row = max(self.list.currentRow(), 0)
        clips = self.library.clips(self.sid)
        self.list.blockSignals(True)
        self.list.clear()
        for c in clips:
            item = QListWidgetItem("%s%s\n%s  ·  %ds  ·  %s" % (
                MARK.get(c["state"], ""), c["title"] or "Moment at " + clock(c["peak"]), clock(c["start"]),
                c["end"] - c["start"], c["reasons"][0]))
            item.setData(Qt.ItemDataRole.UserRole, c["id"])
            self.list.addItem(item)
        if clips:
            self.list.setCurrentRow(min(row, len(clips) - 1))
        self.list.blockSignals(False)       # a refresh must not count as picking a clip: that would re-save old text
        if self.clip:
            self.clip = self.library.clip(self.clip["id"])
        self.export_kept.setEnabled(any(c["state"] == "kept" for c in clips))

    def select_row(self, row):
        self.save_words()
        item = self.list.item(row)
        self.clip = self.library.clip(item.data(Qt.ItemDataRole.UserRole)) if item else None
        self.show_clip()
        if self.clip:
            self.player.setPosition(int(self.clip["start"] * 1000))
            self.player.play()

    def show_clip(self):
        c = self.clip
        self.loading = True
        if c:
            self.why.setText("Why this clip: " + "; ".join(c["reasons"]))
            self.start.setValue(c["start"])
            self.end.setValue(c["end"])
            seconds = c["end"] - c["start"]
            warn = "  ·  over 60s: a copyright claim can block a Short worldwide" if seconds > 60 else ""
            self.length.setText("%.1fs%s" % (seconds, warn))
            self.layout_box.setCurrentIndex(max(self.layout_box.findData(c["layout"]), 0))
            self.words.setPlainText(" ".join(w["w"] for w in c["words"]))
            self.open_file.setEnabled(bool(c["exported"]))
        self.undo_button.setEnabled(bool(self.undo_stack))
        self.loading = False

    # ---- editing
    def change(self, **fields):
        """Every edit goes through here, so everything can be undone."""
        if not self.clip:
            return
        before = {k: self.clip[k] for k in fields}
        self.undo_stack.append((self.clip["id"], before))
        self.library.update_clip(self.clip["id"], **fields)
        self.clip = self.library.clip(self.clip["id"])
        self.refresh_row()
        self.show_clip()

    def refresh_row(self):
        self.reload()

    def undo(self):
        if not self.undo_stack:
            return
        cid, before = self.undo_stack.pop()
        self.library.update_clip(cid, **before)
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.ItemDataRole.UserRole) == cid:
                self.list.blockSignals(True)
                self.list.setCurrentRow(i)
                self.list.blockSignals(False)
        self.clip = self.library.clip(cid)
        self.refresh_row()
        self.show_clip()

    def trim_changed(self):
        if self.loading or not self.clip:
            return
        start, end = self.start.value(), self.end.value()
        if end - start < 1:
            return self.show_clip()
        if abs(start - self.clip["start"]) > 0.04 or abs(end - self.clip["end"]) > 0.04:
            self.change(start=start, end=end)
            self.player.setPosition(int(start * 1000))

    def layout_changed(self):
        value = self.layout_box.currentData()
        if not self.loading and self.clip and value != self.clip["layout"]:
            self.change(layout=value)

    def save_words(self):
        self.save_timer.stop()
        if self.loading or not self.clip:
            return
        text = self.words.toPlainText()
        if text.split() != [w["w"] for w in self.clip["words"]]:
            self.undo_stack.append((self.clip["id"], {"words": self.clip["words"]}))
            self.library.update_clip(self.clip["id"], words=apply_text(self.clip["words"], text))
            self.clip = self.library.clip(self.clip["id"])
            self.undo_button.setEnabled(True)

    def set_state(self, state):
        if self.clip:
            self.change(state="new" if self.clip["state"] == state else state)
            if self.clip["state"] != "new":
                self.step(1)

    def step(self, delta):
        row = self.list.currentRow() + delta
        if 0 <= row < self.list.count():
            self.list.setCurrentRow(row)

    # ---- preview
    def media_ready(self, status):
        """A seek before the file has loaded is ignored, so the first clip is positioned here."""
        if status == QMediaPlayer.MediaStatus.LoadedMedia and self.clip:
            self.player.setPosition(int(self.clip["start"] * 1000))
            self.player.play()

    def loop_preview(self, position):
        if self.clip and position >= self.clip["end"] * 1000:
            self.player.setPosition(int(self.clip["start"] * 1000))

    def toggle(self):
        playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self.player.pause() if playing else self.player.play()

    def hideEvent(self, event):
        self.player.pause()
        super().hideEvent(event)

    # ---- export
    def export_all(self):
        self.save_words()
        for c in self.library.clips(self.sid):
            if c["state"] == "kept":
                self.export.emit(c["id"])

    def show_file(self):
        if self.clip and self.clip["exported"]:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self.clip["exported"])))

    def pick_facecam(self):
        session = self.library.session(self.sid)
        try:
            info = media.probe(session["source"])
        except RuntimeError as e:
            return QMessageBox.warning(self, "Clip Studio", str(e))
        with tempfile.TemporaryDirectory(prefix="clipstudio") as tmp:
            image = os.path.join(tmp, "frame.png")
            at = self.clip["peak"] if self.clip else 1
            if not media.frame_png(session["source"], at, image):
                return QMessageBox.warning(self, "Clip Studio", "Could not read a frame from this recording.")
            dialog = FacecamDialog(image, (info["width"], info["height"]), self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.library.update_session(self.sid, facecam=dialog.value())
