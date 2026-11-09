"""Settings, laid out so a setting is easy to find and hard to lose.

A side menu follows the page as it scrolls and glides to a section when clicked. A search box narrows the page to the
settings that match. Each setting is one row: what it is and what it does on the left, the control on the right.
Changes wait in a bar that slides up from the bottom (Save or Discard, Ctrl+S), so nothing is saved by accident and
nothing is lost by leaving the page. Folders are the exception: picking one saves it at once, as a file dialog should.
"""
import os

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QKeySequence, QLinearGradient, QPainter, QPen, QShortcut, QFont
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QScrollArea,
                               QSlider, QSpinBox, QVBoxLayout, QWidget)

from .gamepicker import GamePicker
from ..paths import exports_dir
from ..version import VERSION
from . import theme as T
from .fx import MOTION, Button, Toggle, alpha, draw_icon, font, glow, mix, panel, tween
from .premium import PremiumSection

CONTROL_W = 330         # every control lines up on the right at this width


def choose(box, value, fallback=0):
    found = box.findData(value)
    box.setCurrentIndex(found if found >= 0 else fallback)


def level_text(value):
    """What a "what to look for" slider means, in words."""
    if value <= 0:
        return "Never"
    if value < 75:
        return "Less"
    if value <= 125:
        return "Normal"
    return "Most" if value >= 200 else "More"


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


class Row(QWidget):
    """One setting: its name and what it does on the left, its control on the right."""

    def __init__(self, title, hint, control, wide=False):
        super().__init__()
        self.words = (title + " " + hint).lower()
        self.hot = 0.0
        name = QLabel(title)
        name.setObjectName("h2")
        about = QLabel(hint)
        about.setObjectName("mute")
        about.setWordWrap(True)
        about.setVisible(bool(hint))
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(name)
        texts.addWidget(about)
        if wide:
            col = QVBoxLayout(self)
            col.setContentsMargins(14, 12, 14, 12)
            col.setSpacing(10)
            col.addLayout(texts)
            col.addWidget(control)
        else:
            row = QHBoxLayout(self)
            row.setContentsMargins(14, 10, 14, 10)
            row.setSpacing(18)
            row.addLayout(texts, 1)
            if not isinstance(control, Toggle):
                control.setFixedWidth(CONTROL_W)
            row.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)

    def enterEvent(self, event):
        tween(self, "hot", 1, 140)

    def leaveEvent(self, event):
        tween(self, "hot", 0, 260)

    def paintEvent(self, event):
        if self.hot > .01:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha(T.A1, 26 * self.hot))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(4, 2, -4, -2), 9, 9)


class Card(QWidget):
    """A section: an icon, a title, a line about it, and its rows with hairlines between them."""

    def __init__(self, title, icon, intro=""):
        super().__init__()
        self.title, self.icon = title, icon
        self.pulse = 0.0
        self.rows = []
        head = QLabel(title)
        head.setStyleSheet("font-size: 17px; font-weight: 700;")
        about = QLabel(intro)
        about.setObjectName("mute")
        about.setWordWrap(True)
        about.setVisible(bool(intro))
        top = QVBoxLayout()
        top.setContentsMargins(52, 0, 0, 0)
        top.setSpacing(2)
        top.addWidget(head)
        top.addWidget(about)
        self.body = QVBoxLayout()
        self.body.setSpacing(0)
        col = QVBoxLayout(self)
        col.setContentsMargins(14, 16, 14, 12)
        col.setSpacing(8)
        col.addLayout(top)
        col.addLayout(self.body)

    def add(self, title, hint, control, wide=False):
        row = Row(title, hint, control, wide)
        self.rows.append(row)
        self.body.addWidget(row)
        return row

    def filter(self, query):
        """Shows the rows that match, or all of them for an empty search. Returns whether anything shows."""
        q = query.strip().lower()
        shown = False
        for row in self.rows:
            on = not q or q in row.words or q in self.title.lower()
            row.setVisible(on)
            shown = shown or on
        self.setVisible(shown)
        return shown

    def flash(self):
        """A brief glow, so the eye lands on the section the side menu jumped to."""
        self.pulse = 1.0
        tween(self, "pulse", 0, 900, QEasingCurve.Type.OutCubic)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(7, 7, -7, -7)
        if self.pulse > .01:
            glow(p, r, 14, T.A2, self.pulse * 1.6, 8)
        panel(p, r, 14)
        badge = QRectF(r.x() + 14, r.y() + 12, 34, 34)
        g = QLinearGradient(badge.topLeft(), badge.bottomRight())
        g.setColorAt(0, T.A1)
        g.setColorAt(1, T.A2)
        p.setBrush(QBrush(g))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(badge, 10, 10)
        draw_icon(p, self.icon, badge.adjusted(8, 8, -8, -8), T.TEXT)
        p.setPen(QPen(alpha(T.LINE, 120), 1))
        shown = [row for row in self.rows if row.isVisible()]
        for row in shown[1:]:
            y = row.geometry().top() + .5
            p.drawLine(QPointF(r.x() + 18, y), QPointF(r.right() - 18, y))


class SideNav(QWidget):
    """The settings' own menu. A pill glides to the section in view; clicking glides the page there."""
    picked = Signal(int)

    def __init__(self, items):
        super().__init__()
        self.items = items                  # [(title, icon)]
        self.index = 0
        self.pill = 0.0
        self.hover = -1
        self.hidden = set()
        self.setFixedWidth(196)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(font(13, QFont.Weight.Medium))
        self.setMinimumHeight(len(items) * 42 + 8)

    def set_index(self, i):
        if i != self.index:
            self.index = i
            tween(self, "pill", i, 260, QEasingCurve.Type.OutCubic)

    def row_at(self, y):
        i = int((y - 4) // 42)
        return i if 0 <= i < len(self.items) else -1

    def mouseMoveEvent(self, event):
        i = self.row_at(event.position().y())
        if i != self.hover:
            self.hover = i
            self.update()

    def leaveEvent(self, event):
        self.hover = -1
        self.update()

    def mousePressEvent(self, event):
        i = self.row_at(event.position().y())
        if i >= 0 and i not in self.hidden:
            self.set_index(i)
            self.picked.emit(i)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pill = QRectF(4, 4 + self.pill * 42, self.width() - 12, 38)
        g = QLinearGradient(pill.topLeft(), pill.topRight())
        g.setColorAt(0, alpha(T.A1, 200))
        g.setColorAt(1, alpha(T.A2, 120))
        p.setBrush(QBrush(g))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(pill, 10, 10)
        p.setBrush(T.CAPTION)
        p.drawRoundedRect(QRectF(pill.x() + 2, pill.y() + 10, 3, 18), 1.5, 1.5)
        p.setFont(self.font())
        for i, (title, icon) in enumerate(self.items):
            r = QRectF(4, 4 + i * 42, self.width() - 12, 38)
            gone = i in self.hidden
            near = max(0.0, 1 - abs(self.pill - i))
            if i == self.hover and not gone and near < .5:
                p.setBrush(alpha(T.TEXT, 14))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(r, 10, 10)
            color = T.FAINT if gone else mix(T.MUTE, T.TEXT, max(near, .4 if i == self.hover else 0))
            shift = 3 if i == self.hover and not gone else 0
            draw_icon(p, icon, QRectF(r.x() + 14 + shift, r.center().y() - 8, 16, 16), color)
            p.setPen(color)
            p.drawText(QRectF(r.x() + 40 + shift, r.y(), r.width() - 44, r.height()), Qt.AlignmentFlag.AlignVCenter,
                       title)


class SaveBar(QWidget):
    """Slides up from the bottom while there are unsaved changes."""
    save = Signal()
    discard = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.shown = 0.0
        self.beat = 0.0
        self.note = QLabel("You have unsaved changes")
        self.note.setStyleSheet("font-weight: 600;")
        self.undo = Button("Discard", "undo", flat=True)
        self.undo.clicked.connect(self.discard)
        self.keep = Button("Save changes", "check", primary=True)
        self.keep.setToolTip("Ctrl+S")
        self.keep.clicked.connect(self.save)
        row = QHBoxLayout(self)
        row.setContentsMargins(42, 8, 10, 8)
        row.setSpacing(4)
        row.addWidget(self.note, 1)
        row.addWidget(self.undo)
        row.addWidget(self.keep)
        self.setFixedSize(560, 64)
        self.hide()
        self.pulse = QTimer(self, interval=40, timeout=self.breathe)

    def breathe(self):
        self.beat = (self.beat + .05) % 2
        self.update()

    def present(self, on):
        if on and not self.isVisible():
            self.show()
            self.raise_()
            if MOTION.on:
                self.pulse.start()
        if not on:
            self.pulse.stop()
        tween(self, "shown", 1.0 if on else 0.0, 320 if on else 240,
              QEasingCurve.Type.OutBack if on else QEasingCurve.Type.InCubic, on_step=self.place)
        self.place()

    def place(self):
        parent = self.parent()
        x = (parent.width() - self.width()) / 2
        y = parent.height() - (self.height() + 18) * self.shown
        self.move(int(x), int(y))
        if self.shown <= .001 and self.isVisible():
            self.hide()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(6, 6, -6, -6)
        glow(p, r, 14, T.A2, 1.3, 6)
        panel(p, r, 14, T.surf(250), alpha(T.A2, 160))
        level = abs(1 - self.beat)            # a dot that breathes: something is waiting to be saved
        p.setBrush(mix(T.WARN, T.CAPTION, level))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(r.x() + 20, r.center().y()), 4 + level * 1.5, 4 + level * 1.5)


class SettingsPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.w = window
        self.loading = False
        self.jumping = False
        self.build_controls()
        title = QLabel("Settings")
        title.setObjectName("h1")
        subtitle = QLabel("Changes wait in the bar at the bottom until you save them. Folders save as soon as you "
                          "pick one.")
        subtitle.setObjectName("mute")
        self.search = QLineEdit(placeholderText="Search settings: game, captions, OBS...")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(300)
        self.search.textChanged.connect(self.filter)
        head = QHBoxLayout()
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(title)
        texts.addWidget(subtitle)
        head.addLayout(texts, 1)
        head.addWidget(self.search, 0, Qt.AlignmentFlag.AlignBottom)

        self.cards = self.build_cards()
        body = QWidget()
        col = QVBoxLayout(body)
        col.setContentsMargins(0, 0, 8, 90)       # room under the last card for the save bar
        col.setSpacing(4)
        for card in self.cards:
            col.addWidget(card)
        self.nothing = QLabel("No setting matches that search.")
        self.nothing.setObjectName("mute")
        self.nothing.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.nothing.hide()
        col.addWidget(self.nothing)
        col.addStretch()
        self.scroll = QScrollArea()
        self.scroll.setWidget(body)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.verticalScrollBar().valueChanged.connect(self.spy)
        self.scroll_pos = 0.0
        self.nav = SideNav([(c.title, c.icon) for c in self.cards])
        self.nav.picked.connect(self.jump)
        side = QVBoxLayout()
        side.addWidget(self.nav)
        side.addStretch()
        main = QHBoxLayout()
        main.setSpacing(14)
        main.addLayout(side)
        main.addWidget(self.scroll, 1)
        page = QVBoxLayout(self)
        page.setContentsMargins(24, 20, 24, 0)
        page.setSpacing(14)
        page.addLayout(head)
        page.addLayout(main, 1)

        self.bar = SaveBar(self)
        self.bar.save.connect(self.save)
        self.bar.discard.connect(self.discard)
        shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.activated.connect(lambda: self.dirty() and self.save())
        self.load()

    # ---- controls
    def build_controls(self):
        self.host = QLineEdit()
        self.port = QSpinBox(maximum=65535)
        self.password = QLineEdit(echoMode=QLineEdit.EchoMode.Password)
        self.twitch = QLineEdit(placeholderText="your channel name")
        self.kick = QLineEdit(placeholderText="your channel name or chatroom ID")
        self.youtube = QLineEdit(placeholderText="this stream's live link")
        self.model = QComboBox()
        for label, value in (("Best (1.6 GB download)", "large-v3-turbo"), ("Balanced (medium)", "medium"),
                             ("Fast (small, weak on Hinglish)", "small")):
            self.model.addItem(label, value)
        self.language = QComboBox()
        for label, value in (("Detect by itself", ""), ("Hindi / Hinglish", "hi"), ("English", "en"),
                             ("Bengali", "bn"), ("Assamese", "as"), ("Tamil", "ta"), ("Telugu", "te"),
                             ("Marathi", "mr")):
            self.language.addItem(label, value)
        self.caption_mode = QComboBox()
        self.caption_mode.addItem("Same language as spoken", "spoken")
        self.caption_mode.addItem("Translate to English", "english")
        self.game = GamePicker("Find it by itself")
        self.wants, self.want_labels = {}, {}
        for key in ("funny", "kills", "deaths", "hype"):
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 200)
            slider.setSingleStep(25)
            slider.setPageStep(25)
            label = QLabel("Normal")
            label.setFixedWidth(64)
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            label.setStyleSheet("color: %s; font-weight: 600;" % T.A1.name())
            slider.valueChanged.connect(lambda v, label=label: label.setText(level_text(v)))
            self.wants[key], self.want_labels[key] = slider, label
        self.roman = Toggle("")
        self.clips = QSpinBox(minimum=1, maximum=40)
        self.length = QSpinBox(minimum=15, maximum=59, suffix=" s")
        self.size = QComboBox()
        for label, value in (("720 x 1280 (smaller files)", "720"), ("1080 x 1920 (standard)", "1080"),
                             ("1440 x 2560 (sharpest after upload)", "1440")):
            self.size.addItem(label, value)
        self.fps = QComboBox()
        for label, value in (("Match the stream (up to 60)", "source"), ("60 fps", "60"),
                             ("30 fps (faster export)", "30"), ("24 fps", "24")):
            self.fps.addItem(label, value)
        self.enhance = QComboBox()
        for label, value in (("Leave it as it is", "off"), ("Clean up and sharpen (fast)", "auto"),
                             ("AI upscale (best, a few minutes per clip)", "ai")):
            self.enhance.addItem(label, value)
        self.motion = Toggle("")
        self.look = QComboBox()
        for key, look in T.LOOKS.items():
            self.look.addItem(look["label"], key)
        self.look.setCurrentIndex(max(self.look.findData(self.w.settings.get("look")), 0))
        self.look.currentIndexChanged.connect(lambda _: self.look_changed())
        self.check = Button("Check for updates", "down")
        self.check.clicked.connect(self.check_updates)
        self.w.updater.nothing.connect(lambda: self.check.busy and self.check.done("You're up to date"))
        self.w.updater.found.connect(lambda _: self.check.set_busy(False))
        self.w.updater.failed.connect(lambda _: self.check.set_busy(False))
        self.premium = PremiumSection(self.w.hub)
        self.premium.upgrade.connect(lambda: self.w.upgrade())
        self.downloads = FolderRow("Save past streams to", "Automatic: a drive with enough space")
        self.downloads.load(self.w.settings.get("downloads_folder"))
        self.downloads.changed.connect(lambda path: self.folder_changed("downloads_folder", path))
        self.exports = FolderRow("Save clips to", exports_dir())
        self.exports.load(self.w.settings.get("exports_folder"))
        self.exports.changed.connect(lambda path: self.folder_changed("exports_folder", path))
        for box in (self.host, self.password, self.twitch, self.kick, self.youtube):
            box.textChanged.connect(self.changed)
        for box in (self.model, self.language, self.caption_mode, self.size, self.fps, self.enhance):
            box.currentIndexChanged.connect(self.changed)
        for box in (self.port, self.clips, self.length):
            box.valueChanged.connect(self.changed)
        for widget in (self.roman, self.motion):
            widget.toggled.connect(self.changed)
        for slider in self.wants.values():
            slider.valueChanged.connect(self.changed)
        self.game.changed.connect(self.changed)

    def build_cards(self):
        def slider_row(key):
            box = QWidget()
            row = QHBoxLayout(box)
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(self.wants[key], 1)
            row.addWidget(self.want_labels[key])
            return box

        game = Card("Game", "target", "Valorant is read straight from its HUD. Shooters, MOBAs, football and "
                                      "fighting games learn your kill, goal or K.O. notice once: mark two in the "
                                      "review desk. Story games, old classics, podcasts, Just Chatting and IRL "
                                      "streams are clipped from your voice, laughter and chat.")
        game.add("Main game", "Used when a stream's title does not name its game or kind of stream. Each stream can "
                              "still be changed in the review desk.", self.game, wide=True)
        clips = Card("Clips", "film", "What gets clipped, and how much of it is ready the moment analysis finishes.")
        for key, title, hint in (("kills", "Kills and clutches", "Every round with your kills, named Kill to Ace"),
                                 ("deaths", "Deaths", "Every death; the ones you react to rank first"),
                                 ("funny", "Funny moments", "When you laugh"),
                                 ("hype", "Loud or busy-chat moments", "Your voice jumping, or chat going off")):
            clips.add(title, hint, slider_row(key))
        clips.add("Captioned right away", "Every moment becomes a clip. This many get captions at once; the rest "
                                          "are captioned in the background.", self.clips)
        clips.add("Usual clip length", "For moments the game did not mark. Kill clips fit their kills.", self.length)
        captions = Card("Captions", "caption", "Speech recognition runs on your PC, never in the cloud.")
        captions.add("Stream language", "Mixed streams caption best when you pick the main language.", self.language)
        captions.add("Captions", "Translation uses the medium speech model, a separate download.", self.caption_mode)
        captions.add("Hindi in Roman letters", "Writes bhai and kya instead of Devanagari script.", self.roman)
        captions.add("Caption quality", "Better quality is slower on a PC without an NVIDIA card.", self.model)
        export = Card("Export", "export", "How finished clips are rendered.")
        export.add("Resolution", "YouTube gives 1440p uploads a better encode, so they stay sharper on phones.",
                   self.size)
        export.add("Frame rate", "A clip never gets more frames than its stream has.", self.fps)
        export.add("Low-quality video", "Clean up sharpens enlarged pictures. AI upscale redraws streams below "
                                        "1080p on your graphics card.", self.enhance)
        streaming = Card("OBS and live chat", "wave", "Clip Studio listens to OBS so analysis starts when you stop "
                                                     "recording, and logs chat while you are live.")
        streaming.add("OBS address", "Usually this PC: 127.0.0.1", self.host)
        streaming.add("OBS port", "Tools > WebSocket Server Settings in OBS", self.port)
        streaming.add("WebSocket password", "Stored encrypted by Windows", self.password)
        streaming.add("Twitch chat", "Your channel name", self.twitch)
        streaming.add("Kick chat", "Your channel name or chatroom ID", self.kick)
        streaming.add("YouTube chat", "This stream's live link", self.youtube)
        folders = Card("Folders", "folder", "Picking a folder saves it at once.")
        folders.add("Past stream downloads", "Big files: a 2-hour stream can need 15 GB", self.downloads, wide=True)
        folders.add("Exported clips", "Where finished clips and their title files go", self.exports, wide=True)
        premium = Card("Premium", "star")
        premium.add("Your plan", "", self.premium, wide=True)
        app = Card("App", "gear")
        app.add("Look", "Film suite is warm tangerine on graphite; Midnight gold is gold on deep blue. Changes "
                        "at once.", self.look)
        app.add("Reduce motion", "Animations already pause by themselves while OBS records or streams.",
                self.motion)
        app.add("Version " + VERSION, "Updates install only when no stream, recording or job is running.",
                self.check)
        return [game, clips, captions, export, streaming, folders, premium, app]

    # ---- values
    def values(self):
        return {"obs_host": self.host.text().strip(), "obs_port": self.port.value(),
                "obs_password": self.password.text(), "twitch_channel": self.twitch.text().strip(),
                "kick_channel": self.kick.text().strip(), "youtube_video": self.youtube.text().strip(),
                "model": self.model.currentData(), "language": self.language.currentData(),
                "roman_script": self.roman.isChecked(), "max_clips": self.clips.value(),
                "clip_length": self.length.value(), "reduce_motion": self.motion.isChecked(),
                "caption_mode": self.caption_mode.currentData(), "export_size": self.size.currentData(),
                "export_fps": self.fps.currentData(), "enhance": self.enhance.currentData(),
                "game": self.game.value(), **{"want_" + k: v.value() for k, v in self.wants.items()}}

    def saved(self):
        s = self.w.settings
        return {k: s.get(k) for k in self.values()}

    def load(self):
        """Puts the saved settings into the controls, without counting that as a change."""
        s = self.w.settings
        self.loading = True
        self.host.setText(s.get("obs_host"))
        self.port.setValue(int(s.get("obs_port")))
        self.password.setText(s.get("obs_password"))
        self.twitch.setText(s.get("twitch_channel"))
        self.kick.setText(s.get("kick_channel"))
        self.youtube.setText(s.get("youtube_video"))
        choose(self.model, s.get("model"))
        choose(self.language, s.get("language"))
        choose(self.caption_mode, s.get("caption_mode"))
        choose(self.size, str(s.get("export_size")), 1)
        choose(self.fps, str(s.get("export_fps")))
        choose(self.enhance, s.get("enhance"), 1)
        self.roman.setChecked(bool(s.get("roman_script")))
        self.motion.setChecked(bool(s.get("reduce_motion")))
        self.clips.setValue(int(s.get("max_clips")))
        self.length.setValue(int(s.get("clip_length")))
        self.game.set(s.get("game") or "")
        for k, v in self.wants.items():
            v.setValue(int(s.get("want_" + k)))
        self.loading = False
        self.changed()

    def dirty(self):
        now, before = self.values(), self.saved()
        return any(str(now[k]) != str(before[k]) for k in now)

    def changed(self, *_):
        if not self.loading:
            self.bar.present(self.dirty())

    def discard(self):
        self.load()
        self.w.toast("Changes discarded", "info")

    # ---- saving
    def look_changed(self):
        """A look is saved and shown at once, like a folder: there is nothing to undo with Save or Discard."""
        key = self.look.currentData()
        self.w.settings.set("look", key)
        QApplication.instance().setStyleSheet(T.use(key))
        for label in self.want_labels.values():
            label.setStyleSheet("color: %s; font-weight: 600;" % T.A1.name())
        for widget in QApplication.allWidgets():
            widget.update()
        self.w.toast(T.LOOKS[key]["label"] + " look on")

    def folder_changed(self, key, path):
        self.w.settings.set(key, path)
        self.w.toast("Folder saved" if path else "Back to automatic")

    def premium_choices(self):
        """Premium-only choices fall back to their free versions, with one upgrade prompt naming the first."""
        gate, blocked = self.w.gate, None
        for feature, box, free in (("english", self.caption_mode, "spoken"), ("1440", self.size, "1080"),
                                   ("60fps", self.fps, "30"), ("upscale", self.enhance, "auto")):
            chosen = box.currentData()
            premium_pick = {"english": chosen == "english", "1440": chosen == "1440",
                            "60fps": chosen in ("60", "source"), "upscale": chosen == "ai"}[feature]
            if premium_pick and not gate.allowed(feature):
                box.setCurrentIndex(max(box.findData(free), 0))
                blocked = blocked or feature
        changed = any(v.value() != int(self.w.settings.get("want_" + k)) for k, v in self.wants.items())
        if changed and not gate.allowed("weights"):
            for k, v in self.wants.items():
                v.setValue(int(self.w.settings.get("want_" + k)))
            blocked = blocked or "weights"
        elif changed:
            gate.use("weights")
        return blocked

    def save(self):
        self.loading = True                 # the fall-backs below are part of saving, not new changes
        blocked = self.premium_choices()
        self.loading = False
        for key, value in self.values().items():
            self.w.settings.set(key, value)
        MOTION.set(reduced=self.motion.isChecked())
        self.w.connect_obs()
        self.bar.keep.done("Saved", 700)
        QTimer.singleShot(650, lambda: self.bar.present(self.dirty()))
        self.w.toast("Settings saved" if not blocked else
                     "Settings saved. Some choices need Premium, so the free versions are set.")
        if blocked:
            self.w.upgrade(blocked)

    def check_updates(self):
        self.check.set_busy(True)
        self.w.updater.check(manual=True)
        QTimer.singleShot(20000, lambda: self.check.busy and self.check.set_busy(False))    # never spin forever

    # ---- finding things
    def filter(self, text):
        shown = [card.filter(text) for card in self.cards]
        self.nav.hidden = {i for i, on in enumerate(shown) if not on}
        self.nav.update()
        self.nothing.setVisible(not any(shown))
        self.scroll.verticalScrollBar().setValue(0)

    def jump(self, i):
        """Glides the page to a section, then makes it glow."""
        card = self.cards[i]
        self.nav.set_index(i)
        bar = self.scroll.verticalScrollBar()
        target = min(card.y(), bar.maximum())
        self.jumping = True
        self.scroll_pos = float(bar.value())
        tween(self, "scroll_pos", target, 420, QEasingCurve.Type.OutCubic,
              on_step=lambda: bar.setValue(int(self.scroll_pos)))
        QTimer.singleShot(460 if MOTION.on else 0, lambda: setattr(self, "jumping", False))
        card.flash()

    def spy(self, value):
        """Moves the side menu's pill to the section being read."""
        if self.jumping:
            return
        bar = self.scroll.verticalScrollBar()
        visible = [i for i, c in enumerate(self.cards) if c.isVisible()]
        if not visible:
            return
        if value >= bar.maximum() - 2 and bar.maximum() > 0:
            self.nav.set_index(visible[-1])
            return
        current = visible[0]
        for i in visible:
            if self.cards[i].y() <= value + 80:
                current = i
        self.nav.set_index(current)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.bar.place()
