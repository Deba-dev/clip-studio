"""The review desk: this is the product. Scan the shortlist, fix a trim, fix a word, export."""
import os
import tempfile

import numpy as np
from PySide6.QtCore import QPointF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QImage, QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QScrollArea, QVBoxLayout,
                               QWidget)

from .. import media
from ..captions import apply_text
from ..paths import clip_thumb, signals_file
from ..worker import parse_facecam
from .cards import ClipCard
from .facecam import FacecamDialog
from .fx import Button, Segmented
from .phone import Phone
from .timeline import StreamMap, TrimBar

LAYOUTS = [("Auto", "auto"), ("Webcam + game", "stack"), ("Full frame", "blur"), ("Centre crop", "crop")]


class ReviewPage(QWidget):
    back = Signal()
    export = Signal(int)
    say = Signal(str, str)

    def __init__(self, library):
        super().__init__()
        self.library = library
        self.sid = None
        self.clip = None
        self.cards = []
        self.row = -1
        self.undo_stack = []
        self.loading = False
        self.loud = np.zeros(1)
        self.duration = 1.0
        self.size_info = None

        self.title = QLabel("Review")
        self.title.setObjectName("h1")
        back = Button("Streams", "back")
        back.clicked.connect(self.back)
        self.camera = Button("Mark webcam", "cam")
        self.camera.clicked.connect(self.pick_facecam)
        self.export_kept = Button("Export kept clips", "export", primary=True)
        self.export_kept.clicked.connect(self.export_all)
        head = QHBoxLayout()
        head.addWidget(back)
        head.addWidget(self.title, 1)
        head.addWidget(self.camera)
        head.addWidget(self.export_kept)

        self.list_body = QWidget()
        self.list_col = QVBoxLayout(self.list_body)
        self.list_col.setContentsMargins(0, 0, 6, 0)
        self.list_col.setSpacing(4)
        self.list_col.addStretch()
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.list_body)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFixedWidth(350)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.phone = Phone()
        self.phone.tapped.connect(self.toggle)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoSink(self.phone.sink)
        self.player.positionChanged.connect(self.on_position)
        self.player.mediaStatusChanged.connect(self.media_ready)
        self.player.playbackStateChanged.connect(self.on_playing)

        why_title = QLabel("Why this clip")
        why_title.setObjectName("h2")
        self.why = QLabel("")
        self.why.setObjectName("why")
        self.why.setWordWrap(True)
        layout_title = QLabel("Layout")
        layout_title.setObjectName("h2")
        self.layout_box = Segmented(LAYOUTS)
        self.layout_box.changed.connect(self.layout_changed)
        words_title = QLabel("Captions")
        words_title.setObjectName("h2")
        self.words = QPlainTextEdit()
        self.words.setPlaceholderText("No speech found in this clip. It will export without captions.")
        self.save_timer = QTimer(self, singleShot=True, interval=500, timeout=self.save_words)
        self.words.textChanged.connect(self.words_typed)

        lead = Button("5s setup", "plus")
        lead.setToolTip("Most clips fail because the setup is cut off")
        lead.clicked.connect(lambda: self.clip and self.change(start=max(self.clip["start"] - 5, 0)))
        tail = Button("3s after", "plus")
        tail.clicked.connect(lambda: self.clip and self.change(end=min(self.clip["end"] + 3, self.duration)))
        self.undo_button = Button("Undo", "undo")
        self.undo_button.clicked.connect(self.undo)
        edits = QHBoxLayout()
        edits.setSpacing(0)
        for w in (lead, tail, self.undo_button):
            edits.addWidget(w)
        edits.addStretch()
        self.keep = Button("Keep  K", "check")
        self.keep.clicked.connect(lambda: self.set_state("kept"))
        self.skip = Button("Skip  X", "x")
        self.skip.clicked.connect(lambda: self.set_state("skipped"))
        self.export_one = Button("Export", "export", primary=True)
        self.export_one.clicked.connect(self.export_current)
        self.open_file = Button("", "folder")
        self.open_file.setToolTip("Show the exported file")
        self.open_file.clicked.connect(self.show_file)
        acts = QHBoxLayout()
        acts.setSpacing(0)
        for w in (self.keep, self.skip, self.export_one, self.open_file):
            acts.addWidget(w)
        acts.addStretch()

        side = QVBoxLayout()
        side.setSpacing(5)
        side.addWidget(why_title)
        side.addWidget(self.why)
        side.addSpacing(4)
        side.addWidget(layout_title)
        side.addWidget(self.layout_box)
        side.addSpacing(4)
        side.addWidget(words_title)
        side.addWidget(self.words, 1)
        side.addLayout(edits)
        side.addLayout(acts)

        body = QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self.scroll)
        body.addWidget(self.phone, 2)
        body.addLayout(side, 3)

        self.map = StreamMap()
        self.map.picked.connect(self.map_clicked)
        self.trim = TrimBar()
        self.trim.trimmed.connect(self.trim_done)
        self.trim.scrub.connect(self.seek)

        page = QVBoxLayout(self)
        page.setContentsMargins(20, 12, 20, 12)
        page.setSpacing(8)
        page.addLayout(head)
        page.addLayout(body, 1)
        page.addWidget(self.trim)
        page.addWidget(self.map)

        for key, action in (("K", lambda: self.set_state("kept")), ("X", lambda: self.set_state("skipped")),
                            ("Space", self.toggle), ("Ctrl+Z", self.undo), ("Down", lambda: self.step(1)),
                            ("Up", lambda: self.step(-1))):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(action)

    # ---- loading
    def open(self, sid):
        self.save_words()
        self.sid = sid
        self.undo_stack = []
        session = self.library.session(sid)
        self.title.setText(self.title.fontMetrics().elidedText(session["name"], Qt.TextElideMode.ElideRight, 520))
        source = session["source"]
        self.duration = session["duration"] or 1.0
        try:
            self.size_info = media.probe(source)
        except RuntimeError:
            self.size_info = None
        self.phone.source_size = (self.size_info["width"], self.size_info["height"]) if self.size_info else None
        split = source.endswith(".ffconcat")
        self.phone.frame = QImage()
        self.phone.note = "Preview is not available yet for recordings OBS split into parts. Exports still work." if split else ""
        self.player.setSource(QUrl() if split else QUrl.fromLocalFile(source))
        curve = np.zeros(1)
        self.loud = np.zeros(1)
        try:
            with np.load(signals_file(sid)) as data:
                curve = data["curve"].astype(np.float32)
                self.loud = data["loud"].astype(np.float32)
        except (OSError, KeyError, ValueError):
            pass            # streams analyzed by 0.1.0 have no saved signals until they are analyzed again
        self.clip = None
        self.row = -1
        self.build_cards()
        self.map.load(curve, self.duration, self.library.clips(sid))
        self.select(0)

    def build_cards(self):
        for card in self.cards:
            card.deleteLater()
        self.cards = []
        clips = self.library.clips(self.sid)
        scores = [c["score"] for c in clips if c["score"] < 100]
        best = max(scores) if scores else 1.0
        for i, c in enumerate(clips):
            card = ClipCard(c, clip_thumb(self.sid, c["peak"]), best)
            card.clicked.connect(lambda i=i: self.select(i))
            self.list_col.insertWidget(i, card)
            self.cards.append(card)
            card.enter(i)
        self.update_kept()

    def reload(self):
        """Refreshes in place, so finishing a job never restarts the page or loses the selection."""
        clips = self.library.clips(self.sid)
        if len(clips) != len(self.cards):
            self.build_cards()
        else:
            for card, c in zip(self.cards, clips):
                card.set_clip(c)
        self.map.clips = clips
        self.map.update()
        if self.clip:
            self.clip = self.library.clip(self.clip["id"])
        self.update_kept()

    def update_kept(self):
        self.export_kept.setEnabled(any(c.clip["state"] == "kept" for c in self.cards))

    def select(self, row):
        self.save_words()
        if not 0 <= row < len(self.cards):
            return
        if 0 <= self.row < len(self.cards):
            self.cards[self.row].select(False)
        self.row = row
        card = self.cards[row]
        card.select(True)
        self.scroll.ensureWidgetVisible(card, 0, 12)
        self.clip = self.library.clip(card.clip["id"])
        self.show_clip()
        self.seek(self.clip["start"])
        self.player.play()

    def facecam(self):
        return parse_facecam(self.library.session(self.sid)["facecam"])

    def show_clip(self):
        c = self.clip
        if not c:
            return
        self.loading = True
        reasons = "\n".join("•  " + r for r in c["reasons"])
        if c["end"] - c["start"] > 60:
            reasons += "\n•  Over 60s: a copyright claim can block a Short worldwide"
        self.why.setText(reasons)
        self.layout_box.set(c["layout"])
        self.words.setPlainText(" ".join(w["w"] for w in c["words"]))
        self.open_file.setEnabled(bool(c["exported"]))
        self.undo_button.setEnabled(bool(self.undo_stack))
        self.phone.set_clip(c["words"], c["layout"], self.facecam())
        self.trim.load(self.loud, self.duration, c)
        self.map.set_active(c["id"])
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
        self.reload()
        self.show_clip()

    def undo(self):
        if not self.undo_stack:
            return
        cid, before = self.undo_stack.pop()
        self.library.update_clip(cid, **before)
        for i, card in enumerate(self.cards):
            if card.clip["id"] == cid and i != self.row:
                self.cards[self.row].select(False)
                self.row = i
                card.select(True)
        self.clip = self.library.clip(cid)
        self.reload()
        self.show_clip()

    def trim_done(self, start, end):
        if self.clip and (abs(start - self.clip["start"]) > .02 or abs(end - self.clip["end"]) > .02):
            self.change(start=start, end=end)

    def layout_changed(self, value):
        self.phone.set_layout(value)
        if not self.loading and self.clip and value != self.clip["layout"]:
            self.change(layout=value)

    def words_typed(self):
        if not self.loading:
            self.save_timer.start()

    def save_words(self):
        self.save_timer.stop()
        if self.loading or not self.clip:
            return
        text = self.words.toPlainText()
        if text.split() != [w["w"] for w in self.clip["words"]]:
            self.undo_stack.append((self.clip["id"], {"words": self.clip["words"]}))
            self.library.update_clip(self.clip["id"], words=apply_text(self.clip["words"], text))
            self.clip = self.library.clip(self.clip["id"])
            self.phone.set_clip(self.clip["words"], self.clip["layout"], self.facecam())
            self.undo_button.setEnabled(True)

    def set_state(self, state):
        if self.clip:
            self.change(state="new" if self.clip["state"] == state else state)
            if self.clip["state"] != "new":
                self.step(1)

    def step(self, delta):
        row = self.row + delta
        if 0 <= row < len(self.cards):
            self.select(row)

    # ---- preview
    def media_ready(self, status):
        """A seek before the file has loaded is ignored, so the first clip is positioned here."""
        if status == QMediaPlayer.MediaStatus.LoadedMedia and self.clip:
            self.seek(self.clip["start"])
            self.player.play()

    def seek(self, t):
        self.player.setPosition(int(t * 1000))

    def on_position(self, position):
        t = position / 1000
        if self.clip and self.trim.drag is None and t >= self.clip["end"]:
            self.seek(self.clip["start"])
            return
        self.phone.set_time(t)
        self.trim.set_play(t)
        self.map.set_play(t)

    def on_playing(self, state):
        self.phone.set_paused(state != QMediaPlayer.PlaybackState.PlayingState)

    def toggle(self):
        playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self.player.pause() if playing else self.player.play()

    def map_clicked(self, t):
        """Clicking inside a clip opens it. Clicking anywhere else just looks at that part of the stream."""
        for i, card in enumerate(self.cards):
            if card.clip["start"] <= t <= card.clip["end"]:
                return self.select(i)
        self.seek(t)

    def hideEvent(self, event):
        self.player.pause()
        super().hideEvent(event)

    # ---- export
    def export_current(self):
        self.save_words()
        if self.clip:
            self.export.emit(self.clip["id"])

    def export_all(self):
        self.save_words()
        for c in self.library.clips(self.sid):
            if c["state"] == "kept":
                self.export.emit(c["id"])

    def export_progress(self, cid, value):
        for card in self.cards:
            if card.clip["id"] == cid:
                card.export = value
                card.update()

    def burst_origin(self, root):
        return self.phone.mapTo(root, QPointF(self.phone.width() / 2, self.phone.height() * .55).toPoint())

    def show_file(self):
        if self.clip and self.clip["exported"]:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self.clip["exported"])))

    def pick_facecam(self):
        session = self.library.session(self.sid)
        if not self.size_info:
            return QMessageBox.warning(self, "Clip Studio", "Could not read this recording.")
        with tempfile.TemporaryDirectory(prefix="clipstudio") as tmp:
            image = os.path.join(tmp, "frame.png")
            at = self.clip["peak"] if self.clip else 1
            if not media.frame_png(session["source"], at, image):
                return QMessageBox.warning(self, "Clip Studio", "Could not read a frame from this recording.")
            dialog = FacecamDialog(image, (self.size_info["width"], self.size_info["height"]), self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.library.update_session(self.sid, facecam=dialog.value())
                self.show_clip()
                self.say.emit("Webcam saved for every clip in this stream", "good")
