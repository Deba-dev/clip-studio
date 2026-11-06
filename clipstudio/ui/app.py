"""The main window: stream library, OBS link, chat logging and settings."""
import ctypes
import ctypes.wintypes
import os
import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QEasingCurve, QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QLinearGradient, QBrush, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMainWindow, QMenu, QMessageBox, QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from .. import chat, fetch
from ..db import Library
from ..obs import ObsClient, RecordingTracker
from ..paths import exports_dir, session_thumb, tool
from ..settings import Settings
from ..version import PRODUCT_NAME, VERSION
from . import theme as T
from .cards import WORKING, StreamCard, clock
from .fx import (MOTION, Aurora, Button, Confetti, Pages, Toast, Toggle, alpha, draw_icon, draw_ring, font, glow, mix,
                 panel, tween)
from .jobs import Jobs
from .review import ReviewPage

HOTKEY_ID = 7301
VK_F9 = 0x78
WM_HOTKEY = 0x0312
VIDEO_FILTER = "Recordings (*.mp4 *.mkv *.mov *.flv *.ts *.webm)"
STEPS = (("Download", "down"), ("Listen", "wave"), ("Rank", "spark"), ("Caption", "caption"), ("Preview", "film"))
STAGE_STEP = {"Downloading": 0, "Getting chat replay": 0, "Reading audio": 1, "Finding moments": 2,
              "Loading speech model": 3, "Writing captions": 3, "Making previews": 4, "Done": 4}


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


class Nav(QWidget):
    """The sidebar. A glowing marker slides between pages; OBS status pulses at the bottom."""
    picked = Signal(int)
    ITEMS = (("Streams", "film"), ("Settings", "gear"))
    TOP = 96
    ROW = 46

    def __init__(self):
        super().__init__()
        self.setFixedWidth(196)
        self.index = 0
        self.marker = 0.0
        self.hover = -1
        self.pulse = 0.0
        self.link = "Waiting for OBS"
        self.linked = False
        self.setMouseTracking(True)
        self.timer = QTimer(self, interval=50, timeout=self.beat)
        self.timer.start()

    def beat(self):
        if self.linked and MOTION.on:
            self.pulse = (self.pulse + .03) % 1
            self.update(0, self.height() - 60, self.width(), 60)

    def set_index(self, i):
        self.index = i
        tween(self, "marker", i, 300, QEasingCurve.Type.OutBack)

    def set_link(self, text, on):
        self.link, self.linked = text, on
        self.update()

    def row_at(self, y):
        i = int((y - self.TOP) // self.ROW)
        return i if 0 <= i < len(self.ITEMS) and y >= self.TOP else -1

    def mouseMoveEvent(self, event):
        i = self.row_at(event.position().y())
        if i != self.hover:
            self.hover = i
            self.setCursor(Qt.CursorShape.PointingHandCursor if i >= 0 else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, event):
        self.hover = -1
        self.update()

    def mousePressEvent(self, event):
        i = self.row_at(event.position().y())
        if i >= 0:
            self.picked.emit(i)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(9, 6, 30, 165))
        p.setPen(QPen(T.LINE, 1))
        p.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        mark = QRectF(18, 22, 34, 34)
        g = QLinearGradient(mark.topLeft(), mark.bottomRight())
        g.setColorAt(0, T.A1)
        g.setColorAt(1, T.A2)
        p.setBrush(QBrush(g))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(mark, 10, 10)
        draw_icon(p, "play", mark.adjusted(9, 9, -9, -9), T.TEXT, 1.5, fill=True)
        p.setPen(T.TEXT)
        p.setFont(font(16, QFont.Weight.Bold))
        p.drawText(QRectF(60, 20, 130, 22), Qt.AlignmentFlag.AlignVCenter, PRODUCT_NAME)
        p.setPen(T.MUTE)
        p.setFont(font(11))
        p.drawText(QRectF(60, 41, 130, 16), Qt.AlignmentFlag.AlignVCenter, "by ZunimiLabs")

        y = self.TOP + self.marker * self.ROW
        pill = QRectF(10, y + 3, self.width() - 20, self.ROW - 6)
        glow(p, pill, 10, T.A2, .8, 6)
        g = QLinearGradient(pill.topLeft(), pill.topRight())
        g.setColorAt(0, alpha(T.A1, 200))
        g.setColorAt(1, alpha(T.A2, 110))
        p.setBrush(QBrush(g))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(pill, 10, 10)
        for i, (label, icon) in enumerate(self.ITEMS):
            top = self.TOP + i * self.ROW
            on = i == self.index
            if i == self.hover and not on:
                p.setBrush(alpha(T.TEXT, 16))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(QRectF(10, top + 3, self.width() - 20, self.ROW - 6), 10, 10)
            draw_icon(p, icon, QRectF(24, top + 14, 18, 18), T.TEXT if on else T.MUTE)
            p.setPen(T.TEXT if on else T.MUTE)
            p.setFont(font(13, QFont.Weight.DemiBold if on else QFont.Weight.Normal))
            p.drawText(QRectF(52, top, 130, self.ROW), Qt.AlignmentFlag.AlignVCenter, label)

        c = QPointF(26, self.height() - 30)
        color = T.GOOD if self.linked else T.WARN
        if self.linked:
            p.setBrush(alpha(color, 110 * (1 - self.pulse)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(c, 5 + 9 * self.pulse, 5 + 9 * self.pulse)
        p.setBrush(color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(c, 4.5, 4.5)
        p.setPen(T.MUTE)
        p.setFont(font(11))
        text = p.fontMetrics().elidedText(self.link, Qt.TextElideMode.ElideRight, self.width() - 56)
        p.drawText(QRectF(42, self.height() - 42, self.width() - 50, 24), Qt.AlignmentFlag.AlignVCenter, text)


class ActionTile(QWidget):
    clicked = Signal()

    def __init__(self, icon, title, text):
        super().__init__()
        self.icon, self.title, self.text = icon, title, text
        self.hover = 0.0
        self.setFixedHeight(92)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def enterEvent(self, event):
        tween(self, "hover", 1, 170)

    def leaveEvent(self, event):
        tween(self, "hover", 0, 260)

    def mouseReleaseEvent(self, event):
        if self.rect().contains(event.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(7, 7, -7, -7).translated(0, -2 * self.hover)
        if self.hover > .01:
            glow(p, r, 14, T.A2, self.hover * 1.4, 7)
        panel(p, r, 14, mix(T.PANEL, T.PANEL_HI, self.hover), mix(T.LINE, alpha(T.A2, 220), self.hover))
        box = QRectF(r.x() + 14, r.center().y() - 22, 44, 44)
        g = QLinearGradient(box.topLeft(), box.bottomRight())
        g.setColorAt(0, T.A1)
        g.setColorAt(1, T.A2)
        p.setBrush(QBrush(g))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(box, 12, 12)
        draw_icon(p, self.icon, box.adjusted(11, 11, -11, -11), T.TEXT, 2)
        p.setPen(T.TEXT)
        p.setFont(font(15, QFont.Weight.DemiBold))
        p.drawText(QRectF(box.right() + 14, r.y() + 12, r.width() - 86, 24), Qt.AlignmentFlag.AlignVCenter, self.title)
        p.setPen(T.MUTE)
        p.setFont(font(12))
        text = p.fontMetrics().elidedText(self.text, Qt.TextElideMode.ElideRight, int(r.width() - 90))
        p.drawText(QRectF(box.right() + 14, r.y() + 37, r.width() - 86, 22), Qt.AlignmentFlag.AlignVCenter, text)


class Pipeline(QWidget):
    """Shows exactly where a stream is in the process, so waiting never feels like a hung app."""
    cancel = Signal()
    HEIGHT = 112

    def __init__(self):
        super().__init__()
        self.t = 0.0
        self.step_index = 0.0
        self.value = 0.0
        self.stage = ""
        self.note = ""
        self.title = ""
        self.pulse = 0.0
        self.setFixedHeight(0)
        self.button = Button("Stop", "x", flat=True)
        self.button.setParent(self)
        self.button.clicked.connect(self.cancel)
        self.timer = QTimer(self, interval=40, timeout=self.beat)
        self.timer.start()

    def beat(self):
        if self.t > .5 and MOTION.on:
            self.pulse = (self.pulse + .025) % 1
            self.update()

    def resizeEvent(self, event):
        self.button.setGeometry(self.width() - 100, 14, 86, 44)

    def open(self, title):
        self.title = title
        tween(self, "t", 1, 320, on_step=self.grow)

    def close_panel(self):
        tween(self, "t", 0, 260, on_step=self.grow)

    def grow(self):
        self.setFixedHeight(int(self.HEIGHT * self.t))

    def report(self, stage, value, note):
        step = STAGE_STEP.get(stage, 0)
        if step != round(self.step_index):
            tween(self, "step_index", step, 420)
        self.stage, self.note = stage, note
        tween(self, "value", value, 200)

    def paintEvent(self, event):
        if self.height() < 6:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self.t)
        r = QRectF(self.rect()).adjusted(7, 2, -7, -6)
        panel(p, r, 14, T.PANEL_HI, alpha(T.A2, 130))
        p.setPen(T.TEXT)
        p.setFont(font(14, QFont.Weight.DemiBold))
        title = p.fontMetrics().elidedText(self.title, Qt.TextElideMode.ElideRight, int(r.width() * .5))
        p.drawText(QRectF(r.x() + 18, r.y() + 8, r.width() * .55, 22), Qt.AlignmentFlag.AlignVCenter, title)
        p.setPen(T.MUTE)
        p.setFont(font(12))
        line = self.stage + ("  ·  " + self.note if self.note else "")
        p.drawText(QRectF(r.x() + 18, r.y() + 30, r.width() * .6, 20), Qt.AlignmentFlag.AlignVCenter, line)
        left, right = r.x() + 34, r.right() - 34
        y = r.bottom() - 30
        gap = (right - left) / (len(STEPS) - 1)
        p.setPen(QPen(alpha(T.MUTE, 50), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(left, y), QPointF(right, y))
        g = QLinearGradient(left, 0, right, 0)
        g.setColorAt(0, T.A1)
        g.setColorAt(1, T.A2)
        reach = left + gap * (self.step_index + min(self.value, 1.0) * (1 if round(self.step_index) < len(STEPS) - 1 else 0))
        p.setPen(QPen(QBrush(g), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(left, y), QPointF(min(reach, right), y))
        current = round(self.step_index)
        for i, (label, icon) in enumerate(STEPS):
            c = QPointF(left + gap * i, y)
            done, now = i < current, i == current
            if now:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(alpha(T.A2, 120 * (1 - self.pulse)))
                p.drawEllipse(c, 12 + 9 * self.pulse, 12 + 9 * self.pulse)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(T.A2 if now else (T.A1 if done else QColor(40, 30, 84)))
            p.drawEllipse(c, 12, 12)
            draw_icon(p, "check" if done else icon, QRectF(c.x() - 7, c.y() - 7, 14, 14),
                      T.TEXT if done or now else T.MUTE, 2)
            p.setFont(font(11, QFont.Weight.DemiBold if now else QFont.Weight.Normal))
            p.setPen(T.TEXT if now or done else T.MUTE)
            p.drawText(QRectF(c.x() - 40, c.y() + 12, 80, 18), Qt.AlignmentFlag.AlignCenter, label)


class FolderRow(QWidget):
    """Shows a folder with a Choose button. An empty value means the app's automatic choice."""
    changed = Signal(str)

    def __init__(self, title, empty_text, can_reset=True):
        super().__init__()
        self.title, self.empty_text = title, empty_text
        self.path = ""
        self.text = QLineEdit(readOnly=True, placeholderText=empty_text)
        self.text.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        pick = Button("Choose", "folder")
        pick.clicked.connect(self.pick)
        self.reset = Button("Automatic", flat=True)
        self.reset.clicked.connect(lambda: self.set(""))
        self.reset.setVisible(False)
        self.can_reset = can_reset
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        row.addWidget(self.text, 1)
        row.addWidget(pick)
        row.addWidget(self.reset)

    def pick(self):
        start = self.path or os.path.expanduser("~")
        path = QFileDialog.getExistingDirectory(self, self.title, start)
        if path:
            self.set(os.path.normpath(path))

    def load(self, path):
        self.path = path
        self.text.setText(path)
        self.reset.setVisible(bool(path) and self.can_reset)

    def set(self, path):
        self.load(path)
        self.changed.emit(path)


class LinkSheet(QWidget):
    """Slides up over a dimmed window to take a past stream's link."""
    submitted = Signal(str, str)
    TAGS = {"youtube": "YouTube: video plus chat replay", "twitch": "Twitch: video. Add chat with a chat file later",
            "kick": "Kick: video. Past chat is not available"}

    def __init__(self, parent):
        super().__init__(parent)
        self.t = 0.0
        self.card = QWidget(self)
        self.card.setObjectName("sheet")
        self.card.setFixedSize(600, 348)
        self.card.paintEvent = self.paint_card
        title = QLabel("Clip a past stream")
        title.setObjectName("h1")
        tip = QLabel("Paste the link to a finished stream. It is saved to your PC, then clipped like a recording.")
        tip.setObjectName("mute")
        tip.setWordWrap(True)
        self.url = QLineEdit(placeholderText="https://www.youtube.com/watch?v=...")
        self.url.textChanged.connect(self.check)
        self.url.returnPressed.connect(self.submit)
        self.tag = QLabel("")
        self.tag.setObjectName("why")
        self.rights = Toggle("This is my own stream, or I have permission to use it")
        self.rights.toggled.connect(self.check)
        self.folder = FolderRow("Save this stream to", "Automatic: a drive with enough space")
        where = QLabel("Save to")
        where.setObjectName("h2")
        self.go = Button("Get clips", "spark", primary=True)
        self.go.clicked.connect(self.submit)
        no = Button("Cancel", flat=True)
        no.clicked.connect(self.dismiss)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(no)
        row.addWidget(self.go)
        col = QVBoxLayout(self.card)
        col.setContentsMargins(26, 22, 26, 16)
        col.setSpacing(8)
        for w in (title, tip, self.url, self.tag, self.rights, where, self.folder):
            col.addWidget(w)
        col.addStretch()
        col.addLayout(row)
        self.hide()

    def paint_card(self, event):
        p = QPainter(self.card)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        panel(p, QRectF(self.card.rect()).adjusted(1, 1, -1, -1), 18, QColor(22, 14, 54, 252), alpha(T.A2, 170))

    def present(self, folder=""):
        self.setGeometry(self.parent().rect())
        self.folder.load(folder)
        self.url.clear()
        self.rights.setChecked(False)
        self.check()
        self.show()
        self.raise_()
        self.url.setFocus()
        tween(self, "t", 1, 300, QEasingCurve.Type.OutCubic, on_step=self.place)

    def dismiss(self):
        tween(self, "t", 0, 200, QEasingCurve.Type.InCubic, on_step=self.gone)

    def gone(self):
        self.place()
        if self.t <= .01:
            self.hide()

    def place(self):
        self.card.move((self.width() - self.card.width()) // 2,
                       int((self.height() - self.card.height()) / 2 + 46 * (1 - self.t)))

    def resizeEvent(self, event):
        self.place()

    def check(self):
        name = fetch.platform_of(self.url.text())
        text = self.url.text().strip()
        self.tag.setText(self.TAGS.get(name, "That is not a past stream link yet" if text else ""))
        self.go.setEnabled(bool(name) and self.rights.isChecked())

    def submit(self):
        if self.go.isEnabled():
            self.submitted.emit(self.url.text().strip(), self.folder.path)
            self.dismiss()

    def mousePressEvent(self, event):
        if not self.card.geometry().contains(event.position().toPoint()):
            self.dismiss()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.dismiss()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(3, 2, 12, int(170 * self.t)))


class StreamsPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.w = window
        self.cards = {}
        title = QLabel("Your streams")
        title.setObjectName("h1")
        sub = QLabel("Stream normally and your shortlist builds itself when OBS stops. Press F9 live to mark a moment.")
        sub.setObjectName("mute")
        self.sub = sub
        link = ActionTile("link", "Clip a past stream", "Paste a YouTube, Twitch or Kick link")
        link.clicked.connect(lambda: self.w.sheet.present(self.w.settings.get("downloads_folder")))
        file = ActionTile("file", "Add a recording", "Use a video file already on this PC")
        file.clicked.connect(self.import_video)
        tiles = QHBoxLayout()
        tiles.setSpacing(0)
        tiles.addWidget(link)
        tiles.addWidget(file)
        self.pipeline = Pipeline()
        self.empty = QLabel("Nothing here yet. Paste a past stream link above to get your first clips.")
        self.empty.setObjectName("mute")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.grid_body = QWidget()
        self.grid = QGridLayout(self.grid_body)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(4)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.grid_body)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        page = QVBoxLayout(self)
        page.setContentsMargins(24, 20, 24, 12)
        page.setSpacing(6)
        page.addWidget(title)
        page.addWidget(sub)
        page.addLayout(tiles)
        page.addWidget(self.pipeline)
        page.addWidget(self.empty, 1)
        page.addWidget(self.scroll, 1)
        self.columns = 0

    def refresh(self):
        rows = self.w.library.sessions()
        seen = set()
        for order, s in enumerate(rows):
            sid = s["id"]
            seen.add(sid)
            if sid in self.cards:
                self.cards[sid].update_row(s)
                continue
            card = StreamCard(s, session_thumb(sid))
            card.clicked.connect(lambda sid=sid: self.open(sid))
            card.menu.connect(lambda pos, sid=sid: self.menu(sid, pos))
            self.cards[sid] = card
            card.enter(order)
        for sid in list(self.cards):
            if sid not in seen:
                self.cards.pop(sid).deleteLater()
        self.order = [s["id"] for s in rows]
        self.empty.setVisible(not rows)
        self.scroll.setVisible(bool(rows))
        self.lay_out()

    def lay_out(self):
        columns = max((self.scroll.viewport().width() - 8) // (StreamCard.WIDTH + 4), 1)
        self.columns = columns
        for i, sid in enumerate(getattr(self, "order", [])):
            self.grid.addWidget(self.cards[sid], i // columns, i % columns)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self, self.lay_out)

    def open(self, sid):
        session = self.w.library.session(sid)
        if session["status"] == "ready":
            self.w.open_review(sid)
        elif session["status"] in ("failed", "stopped"):
            self.w.toast(session["error"] or "Open the menu on this card to try again", "info")

    def menu(self, sid, pos):
        m = QMenu(self)
        busy = self.w.library.session(sid)["status"] in WORKING
        again = "Analyze again" if self.w.library.clips(sid) else "Try again"
        for label, action, enabled in ((again, lambda: self.w.analyze(sid), not busy),
                                       ("Add chat file", lambda: self.import_chat(sid), not busy),
                                       ("Remove from list", lambda: self.remove(sid), not busy)):
            item = QAction(label, m)
            item.setEnabled(enabled)        # a stream being worked on must not be started twice or removed
            item.triggered.connect(action)
            m.addAction(item)
        self.show_menu(m, pos)

    def show_menu(self, m, pos):
        m.exec(pos)

    def import_video(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a recording", "", VIDEO_FILTER)
        if path:
            sid = self.w.library.add_session(os.path.splitext(os.path.basename(path))[0], path)
            self.w.analyze(sid)

    def import_chat(self, sid):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a chat file", "", "Chat files (*.json *.csv *.txt)")
        if path:
            try:
                rows = chat.parse_chat_file(path)
            except (OSError, ValueError) as e:
                return self.w.toast("Could not read that chat file: %s" % e, "bad")
            self.w.library.add_chat(sid, rows)
            self.w.library.update_session(sid, chat_lag=None)
            self.w.toast("Added %d messages. Analyze again to use them." % len(rows))

    def remove(self, sid):
        answer = QMessageBox.question(self, PRODUCT_NAME, "Remove this stream from the list?\n\n"
                                      "Your recording and exported clips stay on disk.")
        if answer == QMessageBox.StandardButton.Yes:
            self.w.library.delete_session(sid)
            self.refresh()


class Section(QWidget):
    def __init__(self, title):
        super().__init__()
        self.form = QFormLayout()
        self.form.setSpacing(9)
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        head = QLabel(title)
        head.setObjectName("h2")
        col = QVBoxLayout(self)
        col.setContentsMargins(20, 14, 20, 16)
        col.addWidget(head)
        col.addLayout(self.form)
        col.addStretch()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        panel(p, QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 14)


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
        self.roman = Toggle("Write Hindi captions in Roman letters (bhai, kya)", bool(s.get("roman_script")))
        self.clips = QSpinBox(minimum=1, maximum=40, value=int(s.get("max_clips")))
        self.length = QSpinBox(minimum=15, maximum=59, value=int(s.get("clip_length")), suffix=" s")
        self.motion = Toggle("Reduce motion", bool(s.get("reduce_motion")))
        self.motion.setToolTip("Animations already pause by themselves while OBS records or streams")
        obs = Section("OBS")
        obs.form.addRow("Address", self.host)
        obs.form.addRow("Port", self.port)
        obs.form.addRow("WebSocket password", self.password)
        live = Section("Live chat")
        live.form.addRow("Twitch", self.twitch)
        live.form.addRow("Kick", self.kick)
        live.form.addRow("YouTube", self.youtube)
        clips = Section("Clips")
        clips.form.addRow("Caption quality", self.model)
        clips.form.addRow("Stream language", self.language)
        clips.form.addRow("", self.roman)
        clips.form.addRow("Clips per stream", self.clips)
        clips.form.addRow("Usual clip length", self.length)
        look = Section("Look")
        look.form.addRow("", self.motion)
        self.downloads = FolderRow("Save past streams to", "Automatic: a drive with enough space")
        self.downloads.load(s.get("downloads_folder"))
        self.downloads.changed.connect(lambda path: self.folder_changed("downloads_folder", path))
        self.exports = FolderRow("Save clips to", exports_dir())
        self.exports.load(s.get("exports_folder"))
        self.exports.changed.connect(lambda path: self.folder_changed("exports_folder", path))
        folders = Section("Folders")
        folders.form.addRow("Past stream downloads", self.downloads)
        folders.form.addRow("Exported clips", self.exports)
        save = Button("Save", "check", primary=True)
        save.clicked.connect(self.save)
        grid = QGridLayout()
        grid.setSpacing(12)
        grid.addWidget(obs, 0, 0)
        grid.addWidget(live, 1, 0)
        grid.addWidget(clips, 0, 1)
        grid.addWidget(look, 1, 1)
        grid.addWidget(folders, 2, 0, 1, 2)
        body = QWidget()
        col = QVBoxLayout(body)
        col.setContentsMargins(0, 0, 8, 0)
        col.setSpacing(10)
        col.addLayout(grid)
        col.addWidget(save, 0, Qt.AlignmentFlag.AlignLeft)
        col.addStretch()
        scroll = QScrollArea()
        scroll.setWidget(body)
        scroll.setWidgetResizable(True)
        page = QVBoxLayout(self)
        page.setContentsMargins(24, 20, 24, 14)
        page.addWidget(title)
        page.addWidget(scroll, 1)

    def folder_changed(self, key, path):
        self.w.settings.set(key, path)
        self.w.toast("Folder saved" if path else "Back to automatic")

    def save(self):
        for key, value in (("obs_host", self.host.text().strip()), ("obs_port", self.port.value()),
                           ("obs_password", self.password.text()), ("twitch_channel", self.twitch.text().strip()),
                           ("kick_channel", self.kick.text().strip()), ("youtube_video", self.youtube.text().strip()),
                           ("model", self.model.currentData()), ("language", self.language.currentData()),
                           ("roman_script", self.roman.isChecked()), ("max_clips", self.clips.value()),
                           ("clip_length", self.length.value()), ("reduce_motion", self.motion.isChecked())):
            self.w.settings.set(key, value)
        MOTION.set(reduced=self.motion.isChecked())
        self.w.connect_obs()
        self.w.toast("Settings saved")


class MainWindow(QMainWindow):
    def __init__(self, library=None, settings=None, use_obs=True):
        super().__init__()
        self.setWindowTitle("%s %s" % (PRODUCT_NAME, VERSION))
        self.resize(1280, 820)
        self.library = library or Library()
        self.settings = settings or Settings()
        MOTION.set(reduced=bool(self.settings.get("reduce_motion")))
        self.jobs = Jobs(self.library.path)
        self.jobs.progress.connect(self.on_progress)
        self.jobs.finished.connect(self.on_job_done)
        self.jobs.idle.connect(lambda: self.streams.pipeline.close_panel())
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

        root = Aurora()
        self.setCentralWidget(root)
        self.nav = Nav()
        self.nav.picked.connect(self.goto)
        self.stack = Pages()
        self.streams = StreamsPage(self)
        self.streams.pipeline.cancel.connect(self.cancel_job)
        self.review = ReviewPage(self.library)
        self.review.back.connect(lambda: self.goto(0))
        self.review.export.connect(lambda cid: self.jobs.add("export", cid))
        self.review.say.connect(self.toast)
        self.settings_page = SettingsPage(self)
        for page in (self.streams, self.settings_page, self.review):
            self.stack.addWidget(page)
        rows = QHBoxLayout(root)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(0)
        rows.addWidget(self.nav)
        rows.addWidget(self.stack, 1)
        self.sheet = LinkSheet(root)
        self.sheet.submitted.connect(self.add_link)
        self.streams.refresh()
        self.recover_interrupted()
        if use_obs:
            self.connect_obs()
            self.register_hotkey()

    def showEvent(self, event):
        super().showEvent(event)
        if sys.platform == "win32":
            try:        # a dark title bar, so the window frame matches the app
                value = ctypes.c_int(1)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(int(self.winId()), 20, ctypes.byref(value), 4)
            except OSError:
                pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.sheet.isVisible():
            self.sheet.setGeometry(self.centralWidget().rect())

    def toast(self, text, kind="good"):
        Toast(self.centralWidget(), text, kind)

    def recover_interrupted(self):
        """A session left mid-job means the app or PC went down, so the job simply runs again."""
        for s in self.library.sessions():
            if s["status"] in ("analyzing", "fetching"):
                self.analyze(s["id"])

    def goto(self, index):
        self.stack.go((self.streams, self.settings_page)[index])
        self.nav.set_index(index)
        self.centralWidget().calm = False
        if index == 0:
            self.streams.refresh()

    def open_review(self, sid):
        self.nav.set_index(0)
        self.centralWidget().calm = True    # the video is the star here, so the background holds still
        self.stack.go(self.review)
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
        self.nav.set_link(text, connected)

    def on_chat_status(self, platform, text):
        self.nav.set_link("%s chat: %s" % (platform.title(), text), True)

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
        MOTION.set(live=self.streaming or self.tracker.sid is not None)

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
            self.streams.sub.setText("F9 is taken by another app. Save a replay in OBS to mark moments instead.")

    def mark_moment(self):
        t = self.tracker.mark()
        if t is not None:
            self.nav.set_link("Marked a moment at " + clock(t), True)

    # ---- jobs
    def add_link(self, url, folder):
        sid = self.library.add_session("Getting stream details...", "", url=url, folder=folder)
        self.analyze(sid)

    def analyze(self, sid):
        session = self.library.session(sid)
        needs_download = bool(session["url"]) and not session["source"]
        self.library.update_session(sid, status="fetching" if needs_download else "analyzing", error="")
        self.streams.refresh()
        self.jobs.add("fetch" if needs_download else "analyze", sid)

    def on_progress(self, stage, value, note):
        job, target = self.jobs.current or ("", 0)
        if job == "export":
            self.review.export_progress(target, value)
            return
        session = self.library.session(target)
        if session is None:
            return
        if self.streams.pipeline.t < .5 or self.streams.pipeline.title != session["name"]:
            self.streams.pipeline.open(session["name"])
        self.streams.pipeline.report(stage, value, note)
        if stage != "Downloading" and session["status"] == "fetching":
            self.library.update_session(target, status="analyzing")
            self.streams.refresh()
        elif stage == "Downloading" and session["name"] != self.streams.cards[target].row["name"]:
            self.streams.refresh()

    def cancel_job(self):
        self.jobs.cancel()

    def on_job_done(self, job, target, result):
        if job == "export":
            self.review.export_progress(target, 0)
            if "error" in result:
                self.toast(result["error"], "bad")
            elif "path" in result:
                self.toast("Clip saved: " + os.path.basename(result["path"]))
                if MOTION.on and self.stack.currentWidget() is self.review:
                    root = self.centralWidget()
                    Confetti(root, self.review.burst_origin(root))
        elif "busy" in result:
            self.toast("This stream is already being processed", "info")
        else:
            if "cancelled" in result:
                self.library.update_session(target, status="stopped", error="Stopped. Use the card menu to continue.")
            elif "error" in result:
                self.library.update_session(target, status="failed", error=result["error"][:200])
                self.toast(result["error"], "bad")
            else:
                session = self.library.session(target)
                count = len(self.library.clips(target))
                self.toast("%d clips ready from %s" % (count, session["name"][:40]))
            self.streams.refresh()
        if self.stack.currentWidget() is self.review and self.review.sid:
            self.review.reload()

    def closeEvent(self, event):
        self.review.save_words()
        self.review.player.stop()
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
    app.setStyleSheet(T.QSS)
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
