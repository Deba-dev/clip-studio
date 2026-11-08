"""The main window: stream library, OBS link, chat logging and settings."""
import ctypes
import ctypes.wintypes
import os
import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QEasingCurve, QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QBrush, QColor, QDesktopServices, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                               QMenu, QMessageBox, QScrollArea, QVBoxLayout, QWidget)

from .. import chat, cleanup, fetch
from ..db import Library
from ..obs import ObsClient, RecordingTracker
from ..paths import session_thumb, tool
from ..settings import Settings
from ..updater import Updater
from ..version import PRODUCT_NAME, VERSION
from . import theme as T
from .cards import WORKING, StreamCard, clock
from .fx import (MOTION, Aurora, Button, Confetti, Pages, Toast, Toggle, alpha, draw_icon, draw_ring, font, glow, mix,
                 panel, tween)
from .jobs import Jobs
from .premium import AccountHub, UpgradeDialog
from .recent import RecentDialog
from .review import ReviewPage
from .settings_page import FolderRow, SettingsPage

HOTKEY_ID = 7301
VK_F9 = 0x78
WM_HOTKEY = 0x0312
VIDEO_FILTER = "Recordings (*.mp4 *.mkv *.mov *.flv *.ts *.webm)"
STEPS = (("Download", "down"), ("Listen", "wave"), ("Rank", "spark"), ("Caption", "caption"), ("Preview", "film"))
STOPPED_ON_CLOSE = "Stopped because Clip Studio was closed. Use the card menu to analyze it again."
STOPPED = "Stopped. Use the card menu to analyze it again."
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


class UpdateBanner(QWidget):
    """Slides open when a new version is ready. It never installs anything by itself."""
    update_now = Signal()
    HEIGHT = 84

    def __init__(self):
        super().__init__()
        self.t = 0.0
        self.value = 0.0
        self.title = ""
        self.note = ""
        self.setFixedHeight(0)
        self.go = Button("Update now", "down", primary=True)
        self.go.setParent(self)
        self.go.clicked.connect(self.update_now)
        self.later = Button("Later", flat=True)
        self.later.setParent(self)
        self.later.clicked.connect(self.close_banner)

    def resizeEvent(self, event):
        self.later.setGeometry(self.width() - 108, 18, 90, 44)
        self.go.setGeometry(self.width() - 248, 18, 140, 44)

    def present(self, version, notes):
        self.title, self.note = "Version %s is ready" % version, notes
        self.set_buttons(True)
        tween(self, "t", 1, 320, on_step=self.grow)

    def close_banner(self):
        tween(self, "t", 0, 240, on_step=self.grow)

    def grow(self):
        self.setFixedHeight(int(self.HEIGHT * self.t))

    def set_buttons(self, shown):
        self.go.setVisible(shown)
        self.later.setVisible(shown)

    def show_progress(self, value, title="Downloading the update"):
        self.set_buttons(False)
        self.title = title
        self.note = "%d%%" % (value * 100)
        self.value = value
        self.update()

    def waiting(self):
        self.show_progress(1.0, "The update will install when your stream or job finishes")
        self.note = "It is downloaded and checked"
        self.update()

    def paintEvent(self, event):
        if self.height() < 6:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self.t)
        r = QRectF(self.rect()).adjusted(7, 2, -7, -6)
        panel(p, r, 14, T.PANEL_HI, alpha(T.A3, 170))
        draw_icon(p, "down", QRectF(r.x() + 18, r.center().y() - 12, 24, 24), T.TEXT, 2)
        width = r.width() - (330 if self.go.isVisible() else 80)
        p.setPen(T.TEXT)
        p.setFont(font(14, QFont.Weight.DemiBold))
        p.drawText(QRectF(r.x() + 56, r.y() + 12, width, 24), Qt.AlignmentFlag.AlignVCenter, self.title)
        p.setPen(T.MUTE)
        p.setFont(font(12))
        note = p.fontMetrics().elidedText(self.note, Qt.TextElideMode.ElideRight, int(width))
        p.drawText(QRectF(r.x() + 56, r.y() + 37, width, 20), Qt.AlignmentFlag.AlignVCenter, note)
        if not self.go.isVisible():
            bar = QRectF(r.x() + 56, r.bottom() - 12, r.width() - 80, 4)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha(T.MUTE, 50))
            p.drawRoundedRect(bar, 2, 2)
            p.setBrush(T.A3)
            p.drawRoundedRect(QRectF(bar.x(), bar.y(), bar.width() * self.value, 4), 2, 2)


class Pipeline(QWidget):
    """Shows exactly where a stream is in the process, so waiting never feels like a hung app."""
    cancel = Signal()
    pause = Signal(bool)        # True to pause, False to resume
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
        self.paused = False
        self.pause_button = Button("Pause", "pause", flat=True)
        self.pause_button.setParent(self)
        self.pause_button.setToolTip("Frees your PC for now. Resume carries on from exactly here.\n"
                                     "Closing Clip Studio stops the analysis instead; it does not resume later.")
        self.pause_button.clicked.connect(lambda: self.pause.emit(not self.paused))
        self.timer = QTimer(self, interval=40, timeout=self.beat)
        self.timer.start()

    def beat(self):
        if self.t > .5 and MOTION.on and not self.paused:
            self.pulse = (self.pulse + .025) % 1
            self.update()

    def resizeEvent(self, event):
        self.button.setGeometry(self.width() - 100, 14, 86, 44)
        self.pause_button.setGeometry(self.width() - 210, 14, 106, 44)

    def set_paused(self, paused, allowed=True):
        self.paused = paused
        self.pause_button.setVisible(allowed)
        self.pause_button.setText("Resume" if paused else "Pause")
        self.pause_button.icon_name = "play" if paused else "pause"
        self.pause_button.update()
        self.update()

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
        line = ("Paused  ·  " if self.paused else "") + self.stage + ("  ·  " + self.note if self.note else "")
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
        recent = ActionTile("film", "Clip your recent streams", "Pick finished streams from your channel")
        recent.clicked.connect(self.pick_recent)
        tiles = QHBoxLayout()
        tiles.setSpacing(0)
        tiles.addWidget(recent)
        tiles.addWidget(link)
        tiles.addWidget(file)
        self.pipeline = Pipeline()
        self.banner = UpdateBanner()
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
        page.addWidget(self.banner)
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

    def pick_recent(self):
        dialog = RecentDialog(self.w, self.w.settings, self.w.library)
        dialog.chosen.connect(self.add_recent)
        dialog.exec()

    def add_recent(self, links):
        folder = self.w.settings.get("downloads_folder")
        for url in links:
            self.w.add_link(url, folder)
        self.w.toast("%d stream%s queued. Each downloads, then gets clipped." % (len(links), "" if len(links) == 1 else "s"))

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


class MainWindow(QMainWindow):
    def __init__(self, library=None, settings=None, use_obs=True):
        super().__init__()
        self.setWindowTitle("%s %s" % (PRODUCT_NAME, VERSION))
        self.resize(1280, 820)
        self.library = library or Library()
        self.settings = settings or Settings()
        MOTION.set(reduced=bool(self.settings.get("reduce_motion")))
        self.jobs = Jobs(self.library.path)
        self.closing = False
        self.jobs.progress.connect(self.on_progress)
        self.jobs.finished.connect(self.on_job_done)
        self.jobs.idle.connect(lambda: self.streams.pipeline.close_panel())
        self.jobs.idle.connect(self.install_when_free)
        MOTION.changed.connect(self.install_when_free)
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
        self.updater = Updater(self.settings)
        self.updater.found.connect(self.update_found)
        self.updater.nothing.connect(lambda: self.toast("You have the latest version"))
        self.updater.failed.connect(self.update_failed)
        self.updater.progress.connect(lambda value: self.streams.banner.show_progress(value))
        self.updater.ready.connect(self.update_ready)
        self.update_info = None
        self.update_path = ""
        self.hub = AccountHub(self.settings)
        self.gate = self.hub.gate

        root = Aurora()
        self.setCentralWidget(root)
        self.nav = Nav()
        self.nav.picked.connect(self.goto)
        self.stack = Pages()
        self.streams = StreamsPage(self)
        self.streams.pipeline.cancel.connect(self.cancel_job)
        self.streams.pipeline.pause.connect(self.pause_job)
        self.streams.pipeline.set_paused(False, self.jobs.can_pause())
        self.jobs.finished.connect(lambda *_: self.streams.pipeline.set_paused(False, self.jobs.can_pause()))
        self.streams.banner.update_now.connect(self.start_update)
        self.review = ReviewPage(self.library, self.settings)
        self.review.back.connect(lambda: self.goto(0))
        self.review.export.connect(self.export_clip)
        self.review.gate = self.gate
        self.review.upgrade.connect(self.upgrade)
        self.review.compile.connect(self.compile_clips)
        self.review.find_kills.connect(lambda sid: self.jobs.add("kills", sid))
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
        freed = self.clean_up() if use_obs else 0
        if use_obs:
            self.hub.refresh_quietly()
        self.recover_interrupted()
        if use_obs:
            self.connect_obs()
            self.register_hotkey()
            problem = self.updater.after_start()
            if problem:
                QTimer.singleShot(1500, self, lambda: self.toast(problem, "bad"))
            elif freed >= 50e6:
                QTimer.singleShot(1500, self, lambda: self.toast("Cleared %.1f GB of old files" % (freed / 1e9)))
            QTimer.singleShot(8000, self, self.background_check)
            self.update_timer = QTimer(self, interval=6 * 3600 * 1000, timeout=self.background_check)
            self.update_timer.start()

    def clean_up(self):
        """Old installers and crashed exports go at every start. After an update, so do unused models and leftovers."""
        try:
            if self.settings.get("cleaned_version") == VERSION:
                return cleanup.light(self.settings)
            freed = cleanup.full(self.library, self.settings)
            self.settings.set("cleaned_version", VERSION)
            return freed
        except Exception:
            return 0                # cleaning up must never stop the app from opening

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
        """A session left mid-job means the app was closed or the PC went down. That job is cancelled, not re-run:
        starting heavy work by itself on the next launch is a surprise. The card offers to analyze it again."""
        for s in self.library.sessions():
            if s["status"] in ("analyzing", "fetching"):
                self.library.update_session(s["id"], status="stopped", error=STOPPED_ON_CLOSE)
            elif s["status"] == "ready" and self.library.uncaptioned(s["id"]):
                self.jobs.add("captions", s["id"])      # background captions carry on where they stopped

    def goto(self, index):
        if index != 1 and self.stack.currentWidget() is self.settings_page and self.settings_page.dirty():
            self.toast("Your settings are not saved yet. They wait in Settings until you save or discard them.",
                       "info")
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

    # ---- updates
    def is_free(self):
        """Updating closes the app, so it only happens with no stream, recording or job in progress."""
        return not self.jobs.busy() and not self.jobs.queue and not MOTION.live

    def background_check(self):
        if not MOTION.live and not self.update_path:
            self.updater.check()

    def update_found(self, info):
        self.update_info = info
        self.streams.banner.present(info["version"], info["notes"])
        if self.stack.currentWidget() is self.settings_page:
            self.goto(0)

    def start_update(self):
        if not self.update_info:
            return
        if not self.updater.frozen:     # a copy run from source has nothing to replace
            QDesktopServices.openUrl(QUrl(self.update_info["page"]))
            return
        self.streams.banner.show_progress(0.0)
        self.updater.install(self.update_info)

    def update_failed(self, message):
        self.toast(message, "bad")
        if self.update_info:
            self.streams.banner.present(self.update_info["version"], self.update_info["notes"])

    def update_ready(self, path):
        self.update_path = path
        self.install_when_free()

    def install_when_free(self):
        if not self.update_path:
            return
        if not self.is_free():
            self.streams.banner.waiting()
            return
        path, self.update_path = self.update_path, ""
        self.updater.launch(path)
        self.close()
        QApplication.quit()

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

    def upgrade(self, feature=None, text=""):
        UpgradeDialog(self, self.hub, feature, text).exec()

    def export_options(self):
        s = self.settings
        fps = 120 if s.get("export_fps") == "source" else int(s.get("export_fps"))
        return self.gate.export_options(str(s.get("export_size")), fps, s.get("enhance"))

    def compile_clips(self, sid, clip_ids, title):
        import json
        from ..worker import compile_request
        with open(compile_request(sid), "w", encoding="utf-8") as f:
            json.dump({"clips": clip_ids, "title": title}, f)
        self.jobs.add("compile", sid)

    def export_clip(self, cid):
        """Every export goes through the plan first, so the free plan's caps hold in one place."""
        clip = self.library.clip(cid)
        if clip is None:
            return
        blocked = self.gate.export_check(clip, self.export_options()[2], self.settings.get("caption_style_default"))
        if blocked:
            self.upgrade(blocked)
            return
        if self.jobs.paused and self.jobs.current and self.jobs.current[0] != "captions":
            self.toast("The export starts after the paused job. Press Resume on the Streams page.", "info")
        self.jobs.add("export", cid)

    def analyze(self, sid):
        session = self.library.session(sid)
        if self.gate.free_limits() and not self.gate.allowed("streams", sid):
            message = self.gate.why_not("streams")
            self.library.update_session(sid, status="failed", error=message)
            self.streams.refresh()
            if self.isVisible():
                self.upgrade("streams")
            return
        needs_download = bool(session["url"]) and not session["source"]
        self.library.update_session(sid, status="fetching" if needs_download else "analyzing", error="")
        self.streams.refresh()
        self.jobs.add("fetch" if needs_download else "analyze", sid)

    def on_progress(self, stage, value, note):
        job, target = self.jobs.current or ("", 0)
        if job == "export":
            self.review.export_progress(target, value)
            phase = note[:12]            # one message per phase, not one per percent
            if phase != getattr(self, "export_phase", "") and note.startswith(("AI", "Getting the AI")):
                self.toast("Getting the AI upscaler, a one-time 45 MB download" if note.startswith("Getting")
                           else "AI upscaling this clip. It takes a couple of minutes.")
            self.export_phase = phase
            return
        session = self.library.session(target)
        if session is None:
            return
        if job == "captions" and note != getattr(self, "caption_note", "") and self.review.sid == target:
            self.caption_note = note        # one more clip has its captions: show them without a full reload
            if self.stack.currentWidget() is self.review:
                self.review.reload()
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

    def pause_job(self, on):
        if not self.jobs.busy():
            return
        paused = self.jobs.pause(on)
        self.streams.pipeline.set_paused(paused, self.jobs.can_pause())
        if on and not paused:
            self.toast("This job could not be paused", "bad")
        elif paused:
            self.toast("Paused. Your PC is free until you press Resume.", "info")

    def on_job_done(self, job, target, result):
        if job == "export":
            self.review.export_progress(target, 0)
            self.review.export_finished(target, "path" in result)
            if "path" in result:
                clip = self.library.clip(target)
                if clip:
                    self.gate.record_export(clip, self.export_options()[2], self.settings.get("caption_style_default"))
            if "error" in result:
                self.toast(result["error"], "bad")
            elif "path" in result:
                self.toast("Clip saved: " + os.path.basename(result["path"]))
                if MOTION.on and self.stack.currentWidget() is self.review:
                    root = self.centralWidget()
                    Confetti(root, self.review.burst_origin(root))
        elif job == "compile":
            if "path" in result:
                self.toast("Compilation saved: " + os.path.basename(result["path"]))
            elif "error" in result:
                self.toast(result["error"], "bad")
        elif job == "kills":
            self.review.kills_finished(result.get("kills") if "error" not in result else None)
            if "error" in result:
                self.toast(result["error"], "info")
            else:
                self.toast("Found %d kills, %d new clips. %s." % (result.get("kills", 0), result.get("added", 0),
                                                                    result.get("note", "")))
                if self.library.uncaptioned(target):
                    self.jobs.add("captions", target)
            self.streams.refresh()
        elif job == "captions":
            if "error" in result:           # quiet: the clips are fine, they just wait for the next try
                print("captions:", result["error"])
        elif "busy" in result:
            self.toast("This stream is already being processed", "info")
        else:
            if "cancelled" in result:
                self.library.update_session(target, status="stopped",
                                            error=STOPPED_ON_CLOSE if self.closing else STOPPED)
            elif "error" in result:
                self.library.update_session(target, status="failed", error=result["error"][:200])
                if result.get("upgrade") and result["upgrade"] != "too_long":
                    self.upgrade(result["upgrade"], result["error"])
                else:
                    self.toast(result["error"], "bad")
            else:
                session = self.library.session(target)
                self.gate.record_stream(session["duration"] or 0, target)
                count = len(self.library.clips(target))
                waiting = len(self.library.uncaptioned(target))
                self.toast("%d clips ready from %s" % (count, session["name"][:40]) +
                           (". Captions for %d more are being written." % waiting if waiting else ""))
                if waiting:
                    self.jobs.add("captions", target)
            self.streams.refresh()
        if self.stack.currentWidget() is self.review and self.review.sid:
            self.review.reload()

    def closeEvent(self, event):
        self.closing = True                 # an analysis running now is cancelled, and never resumed on next launch
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
