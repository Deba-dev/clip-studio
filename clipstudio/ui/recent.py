"""Clip your recent streams: type the channel once, tick streams, and they are downloaded and clipped in turn."""
import urllib.request

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QScrollArea, QVBoxLayout, QWidget)

from .. import fetch
from ..account import run_in_thread
from .cards import clock
from .fx import Button

THUMB = (160, 90)


class Relay(QObject):
    """Carries results from download threads back to the UI thread."""
    listed = Signal(object, object)
    thumb = Signal(str, bytes)


class StreamRow(QWidget):
    def __init__(self, stream, clipped):
        super().__init__()
        self.stream = stream
        self.check = QCheckBox()
        self.check.setChecked(not clipped)
        self.picture = QLabel()
        self.picture.setFixedSize(*THUMB)
        self.picture.setStyleSheet("background:#140f35;border-radius:8px")
        title = QLabel(stream["title"])
        title.setWordWrap(True)
        meta = QLabel(clock(stream["duration"]) + ("  ·  Clipped already" if clipped else ""))
        meta.setObjectName("mute")
        text = QVBoxLayout()
        text.addWidget(title)
        text.addWidget(meta)
        text.addStretch()
        row = QHBoxLayout(self)
        row.setContentsMargins(4, 4, 4, 4)
        row.addWidget(self.check)
        row.addWidget(self.picture)
        row.addLayout(text, 1)

    def mousePressEvent(self, event):
        self.check.toggle()

    def set_thumb(self, data):
        image = QImage.fromData(data)
        if not image.isNull():
            self.picture.setPixmap(QPixmap.fromImage(image).scaled(
                *THUMB, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))


class RecentDialog(QDialog):
    chosen = Signal(list)       # stream links, oldest first so they finish in stream order

    def __init__(self, parent, settings, library):
        super().__init__(parent)
        self.settings, self.library = settings, library
        self.setWindowTitle("Your recent streams")
        self.setMinimumSize(640, 560)
        self.relay = Relay()
        self.relay.listed.connect(self.show_list)
        self.relay.thumb.connect(self.show_thumb)
        title = QLabel("Your recent streams")
        title.setObjectName("h1")
        tip = QLabel("Your YouTube channel (@name), or a Twitch or Kick channel link. Finished streams appear below.")
        tip.setObjectName("mute")
        tip.setWordWrap(True)
        self.channel = QLineEdit(settings.get("my_channel") or "", placeholderText="@yourchannel")
        self.channel.returnPressed.connect(self.load)
        show = Button("Show streams", "check")
        show.clicked.connect(self.load)
        top = QHBoxLayout()
        top.addWidget(self.channel, 1)
        top.addWidget(show)
        self.status = QLabel("")
        self.status.setObjectName("mute")
        self.status.setWordWrap(True)
        self.body = QWidget()
        self.rows_box = QVBoxLayout(self.body)
        self.rows_box.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll = QScrollArea()
        scroll.setWidget(self.body)
        scroll.setWidgetResizable(True)
        self.go = Button("Clip the ticked streams", "check", primary=True)
        self.go.clicked.connect(self.submit)
        self.go.setEnabled(False)
        rights = QLabel("Only clip streams you own or have permission to use.")
        rights.setObjectName("mute")
        bottom = QHBoxLayout()
        bottom.addWidget(rights, 1)
        bottom.addWidget(self.go)
        col = QVBoxLayout(self)
        col.setContentsMargins(22, 18, 22, 18)
        col.setSpacing(10)
        col.addWidget(title)
        col.addWidget(tip)
        col.addLayout(top)
        col.addWidget(self.status)
        col.addWidget(scroll, 1)
        col.addLayout(bottom)
        self.rows = []
        if self.channel.text():
            self.load()

    def load(self):
        channel = self.channel.text().strip()
        if not channel:
            return
        self.settings.set("my_channel", channel)
        self.status.setText("Looking for your streams...")
        self.go.setEnabled(False)
        run_in_thread(lambda: fetch.recent_streams(channel), lambda result, error: self.relay.listed.emit(result, error))

    def clipped_ids(self):
        return {s["url"] for s in self.library.sessions() if s["url"]}

    def show_list(self, streams, error):
        for row in self.rows:
            row.deleteLater()
        self.rows = []
        if error:
            self.status.setText(error)
            return
        if not streams:
            self.status.setText("No finished streams found on that channel.")
            return
        done = self.clipped_ids()
        for stream in streams:
            row = StreamRow(stream, any(stream["id"] and stream["id"] in url for url in done))
            row.check.toggled.connect(self.update_button)
            self.rows_box.addWidget(row)
            self.rows.append(row)
            if stream["thumbnail"]:
                url = stream["thumbnail"]
                run_in_thread(lambda url=url: urllib.request.urlopen(url, timeout=15).read(),
                              lambda data, error, url=url: data and self.relay.thumb.emit(url, data))
        self.status.setText("%d finished streams. Newest first." % len(streams))
        self.update_button()

    def show_thumb(self, url, data):
        for row in self.rows:
            if row.stream["thumbnail"] == url:
                row.set_thumb(data)

    def update_button(self):
        count = sum(r.check.isChecked() for r in self.rows)
        self.go.setEnabled(count > 0)
        self.go.setText("Clip %d stream%s" % (count, "" if count == 1 else "s") if count else "Clip the ticked streams")

    def submit(self):
        links = [r.stream["url"] for r in reversed(self.rows) if r.check.isChecked() and r.stream["url"]]
        if links:
            self.chosen.emit(links)
            self.accept()
