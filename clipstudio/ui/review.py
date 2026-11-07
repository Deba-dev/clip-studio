"""The review desk: this is the product. Scan the shortlist, cut, fix the sound and the words, export."""
import os
import tempfile

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QImage, QKeySequence, QPainter, QShortcut
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import (QColorDialog, QComboBox, QDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QScrollArea, QSlider, QSplitter, QStackedWidget,
                               QVBoxLayout, QWidget)

from .. import edit as clip_edit
from .. import media
from .. import captions as caps
from .. import insights
from ..captions import apply_text
from ..paths import clip_thumb, signals_file
from ..worker import parse_facecam
from . import theme as T
from .audio import PreviewAudio
from .cards import ClipCard, clock
from .facecam import FacecamDialog
from .fx import Button, IconButton, Segmented, Toggle
from .phone import Phone
from .timeline import StreamMap, TrimBar

LAYOUTS = [("Auto", "auto"), ("Webcam + game", "stack"), ("Full frame", "blur"), ("Centre crop", "crop")]
FILTERS = [("All", ""), ("Funny", "funny"), ("Kills", "kills"), ("Deaths", "deaths"), ("Hype", "hype")]
TABS = [("Clip", "clip"), ("Audio", "audio"), ("Captions", "captions"), ("Look", "look")]
SPEEDS = [("0.5x", "0.5"), ("1x", "1"), ("1.5x", "1.5"), ("2x", "2")]
COLORS = ("FFE100", "FFFFFF", "34D399", "F87171", "60A5FA", "F472B6")
FRAME = 1 / 30
JUMP = 5


class Swatch(QWidget):
    """A round colour choice."""
    picked = Signal(str)

    def __init__(self, color):
        super().__init__()
        self.color = color
        self.on = False
        self.setFixedSize(30, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        self.picked.emit(self.color)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(T.TEXT if self.on else Qt.PenStyle.NoPen)
        p.setBrush(QColor("#" + self.color))
        p.drawEllipse(self.rect().adjusted(4, 4, -4, -4))


class ColorPick(QWidget):
    """A colour well with a name under it. Click to choose any colour."""
    picked = Signal(str)

    def __init__(self, title):
        super().__init__()
        self.title, self.color = title, "FFFFFF"
        self.setFixedSize(58, 50)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Choose the " + title.lower() + " colour")

    def set(self, color):
        self.color = color
        self.update()

    def mousePressEvent(self, event):
        chosen = QColorDialog.getColor(QColor("#" + self.color), self, "Choose the " + self.title.lower() + " colour")
        if chosen.isValid():
            self.set(chosen.name()[1:].upper())
            self.picked.emit(self.color)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QColor(255, 255, 255, 60))
        p.setBrush(QColor("#" + self.color))
        p.drawRoundedRect(QRectF(15, 2, 28, 28), 8, 8)
        p.setPen(T.MUTE)
        p.drawText(QRectF(0, 32, self.width(), 16), Qt.AlignmentFlag.AlignCenter, self.title)


class PresetChip(QWidget):
    """One caption preset, drawn in its own style so the choice is visual."""
    picked = Signal(str)

    def __init__(self, key):
        super().__init__()
        self.key, self.on = key, False
        self.style = caps.style_of({"caption_style": {"preset": key}})
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(caps.PRESETS[key]["name"] + (" (premium)" if key in caps.PREMIUM_PRESETS else ""))

    def mousePressEvent(self, event):
        self.picked.emit(self.key)

    def paintEvent(self, event):
        from PySide6.QtGui import QFont, QPainterPath, QPen
        st = self.style
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(T.A2 if self.on else QColor(255, 255, 255, 30), 2 if self.on else 1))
        p.setBrush(QColor(14, 10, 40))
        p.drawRoundedRect(r, 9, 9)
        f = QFont()
        f.setFamilies([st["font"], "Segoe UI"])
        f.setPixelSize(15)
        f.setBold(bool(st["bold"]))
        name = caps.PRESETS[self.key]["name"]
        text = name.upper() if st["upper"] else name
        path = QPainterPath()
        path.addText(0, 0, f, text)
        box = path.boundingRect()
        p.translate(r.center().x() - box.width() / 2 - box.x(), r.center().y() - box.height() / 2 - box.y())
        if st["outline_width"]:
            p.setPen(QPen(QColor("#" + st["outline"]), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                          Qt.PenJoinStyle.RoundJoin))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#" + (st["highlight"] if st["highlight_mode"] in ("color", "fill") else st["text"])))
        p.drawPath(path)


class Dial(QWidget):
    """A labelled slider whose value is always readable. It saves when released, so one drag is one undo."""
    moved = Signal(float)
    done = Signal(float)

    def __init__(self, title, low, high, scale=1.0, text="%g"):
        super().__init__()
        self.scale, self.text = scale, text
        self.name = QLabel(title)
        self.value_label = QLabel("")
        self.value_label.setObjectName("mute")
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(int(low / scale), int(high / scale))
        self.slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.slider.valueChanged.connect(self.changed)
        self.slider.sliderReleased.connect(lambda: self.done.emit(self.value()))
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(self.name, 1)
        top.addWidget(self.value_label)
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 2, 0, 2)
        col.setSpacing(3)
        col.addLayout(top)
        col.addWidget(self.slider)

    def value(self):
        return self.slider.value() * self.scale

    def set(self, value):
        self.slider.blockSignals(True)
        self.slider.setValue(int(round(value / self.scale)))
        self.slider.blockSignals(False)
        self.value_label.setText(self.text % self.value())

    def changed(self):
        self.value_label.setText(self.text % self.value())
        self.moved.emit(self.value())
        if not self.slider.isSliderDown():
            self.done.emit(self.value())        # a click on the groove or the keyboard has no release to wait for


class ReviewPage(QWidget):
    back = Signal()
    export = Signal(int)
    say = Signal(str, str)
    upgrade = Signal(str)       # a Premium feature or a used-up free cap
    compile = Signal(int, list, str)    # session, clip ids, title

    def __init__(self, library, settings=None):
        super().__init__()
        self.library = library
        self.settings = settings
        self.gate = None            # set by the main window
        self.sid = None
        self.clip = None
        self.cards = []
        self.row = -1
        self.undo_stack = []
        self.redo_stack = []
        self.loading = False
        self.loud = np.zeros(1)
        self.duration = 1.0
        self.size_info = None
        self.keep = []
        self.loop = True
        self.pending = None     # where a seek is heading: on a long stream it can take a second to arrive
        self.fresh = False      # a newly opened file still needs its first seek
        self.settle = QTimer(self, singleShot=True, interval=2500, timeout=self.seek_done)

        self.title = QLabel("Review")
        self.title.setObjectName("h1")
        back = Button("Streams", "back")
        back.clicked.connect(self.back)
        self.camera = Button("Mark webcam", "cam")
        self.camera.clicked.connect(self.pick_facecam)
        self.export_kept = Button("Export kept clips", "export", primary=True)
        self.export_kept.clicked.connect(self.export_all)
        self.make_compilation = Button("Make a compilation", "film")
        self.make_compilation.setToolTip("Joins the kept clips you can see (use the filter for, say, only kills) into one video")
        self.make_compilation.clicked.connect(self.compilation)
        head = QHBoxLayout()
        head.addWidget(back)
        head.addWidget(self.title, 1)
        head.addWidget(self.camera)
        head.addWidget(self.make_compilation)
        head.addWidget(self.export_kept)

        self.list_body = QWidget()
        self.list_col = QVBoxLayout(self.list_body)
        self.list_col.setContentsMargins(0, 0, 6, 0)
        self.list_col.setSpacing(4)
        self.list_col.addStretch()
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.list_body)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.filter_box = Segmented(FILTERS)
        self.filter_box.changed.connect(lambda _: self.apply_filter())
        self.sort_box = QComboBox()
        self.sort_box.addItem("Best first", "score")
        self.sort_box.addItem("Stream order", "time")
        self.sort_box.addItem("Most likely to go viral", "viral")
        self.sort_box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.sort_box.currentIndexChanged.connect(lambda _: self.sort_cards())
        self.list_side = QWidget()
        left = QVBoxLayout(self.list_side)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(6)
        left.addWidget(self.filter_box)
        left.addWidget(self.sort_box)
        left.addWidget(self.scroll, 1)
        self.list_side.setMinimumWidth(300)

        self.phone = Phone()
        self.phone.tapped.connect(self.toggle)
        self.player = QMediaPlayer(self)
        self.audio = PreviewAudio(self.player)
        self.player.setVideoSink(self.phone.sink)
        self.player.positionChanged.connect(self.on_position)
        self.player.mediaStatusChanged.connect(self.media_ready)
        self.player.playbackStateChanged.connect(self.on_playing)

        self.tabs = Segmented(TABS)
        self.tabs.changed.connect(lambda v: self.pages.setCurrentIndex([t[1] for t in TABS].index(v)))
        self.pages = QStackedWidget()
        for page in (self.build_clip_tab(), self.build_audio_tab(), self.build_caption_tab(), self.build_look_tab()):
            self.pages.addWidget(page)
        self.keep_button = Button("Keep  K", "check")
        self.keep_button.clicked.connect(lambda: self.set_state("kept"))
        self.skip = Button("Skip  X", "x")
        self.skip.clicked.connect(lambda: self.set_state("skipped"))
        self.export_one = Button("Export", "export", primary=True)
        self.export_one.clicked.connect(self.export_current)
        self.open_file = Button("", "folder")
        self.open_file.setToolTip("Show the exported file")
        self.open_file.clicked.connect(self.show_file)
        acts = QHBoxLayout()
        acts.setSpacing(0)
        for w in (self.keep_button, self.skip, self.export_one, self.open_file):
            acts.addWidget(w)
        acts.addStretch()
        self.side = QWidget()
        side = QVBoxLayout(self.side)
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(6)
        side.addWidget(self.tabs)
        side.addWidget(self.pages, 1)
        side.addLayout(acts)
        self.side.setMinimumWidth(330)

        self.split = QSplitter(Qt.Orientation.Horizontal)
        self.split.setHandleWidth(6)
        self.split.setChildrenCollapsible(True)
        for w in (self.list_side, self.phone, self.side):
            self.split.addWidget(w)
        self.split.setStretchFactor(0, 0)
        self.split.setStretchFactor(1, 2)
        self.split.setStretchFactor(2, 3)
        self.split.setSizes(self.saved_split())
        self.split.splitterMoved.connect(lambda *_: self.remember_split())

        self.map = StreamMap()
        self.map.picked.connect(self.map_clicked)
        self.map.chosen.connect(self.pin_clicked)
        self.trim = TrimBar()
        self.trim.trimmed.connect(self.trim_done)
        self.trim.scrub.connect(self.seek)

        page = QVBoxLayout(self)
        page.setContentsMargins(20, 12, 20, 12)
        page.setSpacing(6)
        page.addLayout(head)
        page.addWidget(self.split, 1)
        page.addLayout(self.build_transport())
        page.addWidget(self.trim)
        page.addWidget(self.map)

        for key, action in (("K", lambda: self.set_state("kept")), ("X", lambda: self.set_state("skipped")),
                            ("Space", self.toggle), ("Ctrl+Z", self.undo), ("Ctrl+Y", self.redo),
                            ("Ctrl+Shift+Z", self.redo), ("Down", lambda: self.step(1)), ("Up", lambda: self.step(-1)),
                            ("Left", lambda: self.jump(-1)), ("Right", lambda: self.jump(1)),
                            ("J", lambda: self.jump(-JUMP)), ("L", lambda: self.jump(JUMP)),
                            (",", lambda: self.nudge(-FRAME)), (".", lambda: self.nudge(FRAME)),
                            ("Home", self.go_start), ("End", self.go_end), ("[", self.set_start), ("]", self.set_end),
                            ("I", self.mark_in), ("O", self.mark_out), ("Delete", self.cut), ("S", self.split_here),
                            ("M", self.toggle_mute)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(action)

    # ---- building
    def build_transport(self):
        """Moving around, then shaping the clip, then listening. Every button has a key, shown in its tooltip."""
        row = QHBoxLayout()
        row.setSpacing(0)

        def add(icon, tip, action):
            b = IconButton(icon, tip)
            b.clicked.connect(action)
            row.addWidget(b)
            return b

        add("first", "Go to clip start  (Home)", self.go_start)
        add("rewind", "Back 5 seconds  (J)", lambda: self.jump(-JUMP))
        add("stepback", "Back one frame  (,)", lambda: self.nudge(-FRAME))
        self.play_button = add("play", "Play or pause  (Space)", self.toggle)
        add("stepnext", "Forward one frame  (.)", lambda: self.nudge(FRAME))
        add("forward", "Forward 5 seconds  (L)", lambda: self.jump(JUMP))
        add("last", "Go to clip end  (End)", self.go_end)
        self.clock = QLabel("0:00 / 0:00")
        self.clock.setMinimumWidth(92)
        self.clock.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.clock)
        row.addSpacing(6)
        add("setstart", "Start the clip here  ([)", self.set_start)
        add("setend", "End the clip here  (])", self.set_end)
        add("markin", "Mark the start of a part  (I)", self.mark_in)
        add("markout", "Mark the end of a part  (O)", self.mark_out)
        add("cut", "Cut out the marked part  (Delete)", self.cut)
        add("split", "Split into two clips here  (S)", self.split_here)
        self.undo_button = add("undo", "Undo  (Ctrl+Z)", self.undo)
        self.redo_button = add("redo", "Redo  (Ctrl+Y)", self.redo)
        row.addStretch()
        self.speed = Segmented(SPEEDS)
        self.speed.index = self.speed.pill = 1
        self.speed.setFixedWidth(170)
        self.speed.setToolTip("Preview speed. The export stays at normal speed.")
        self.speed.changed.connect(self.set_speed)
        row.addWidget(self.speed)
        row.addSpacing(4)
        self.loop_button = IconButton("loop", "Loop the clip", checkable=True)
        self.loop_button.setChecked(True)
        self.loop_button.toggled.connect(self.set_loop)
        row.addWidget(self.loop_button)
        self.mute_button = IconButton("sound", "Mute the preview  (M)", checkable=True)
        self.mute_button.toggled.connect(self.set_mute)
        row.addWidget(self.mute_button)
        self.monitor = QSlider(Qt.Orientation.Horizontal)
        self.monitor.setRange(0, 100)
        self.monitor.setValue(100)
        self.monitor.setFixedWidth(90)
        self.monitor.setToolTip("Preview volume. This only changes what you hear, not the clip.")
        self.monitor.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.monitor.valueChanged.connect(lambda v: self.audio.set_volume(v / 100))
        row.addWidget(self.monitor)
        return row

    @staticmethod
    def heading(text):
        label = QLabel(text)
        label.setObjectName("h2")
        return label

    def build_clip_tab(self):
        self.why = QLabel("")
        self.why.setObjectName("why")
        self.why.setWordWrap(True)
        self.name_box = QLineEdit()
        self.name_box.setPlaceholderText("Clip name, used for the exported file")
        self.name_box.editingFinished.connect(self.name_done)
        lead = Button("5s setup", "plus")
        lead.setToolTip("Most clips fail because the setup is cut off")
        lead.clicked.connect(lambda: self.clip and self.change(start=max(self.clip["start"] - 5, 0)))
        tail = Button("3s after", "plus")
        tail.clicked.connect(lambda: self.clip and self.change(end=min(self.clip["end"] + 3, self.duration)))
        clear = Button("Restore cuts", "undo")
        clear.setToolTip("Bring back everything cut out of the middle of this clip")
        clear.clicked.connect(lambda: self.set_edit(cuts=[]))
        edits = QHBoxLayout()
        edits.setSpacing(0)
        for w in (lead, tail, clear):
            edits.addWidget(w)
        edits.addStretch()
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 4, 0, 0)
        col.setSpacing(5)
        col.addWidget(self.heading("Why this clip"))
        col.addWidget(self.why)
        col.addSpacing(4)
        col.addWidget(self.heading("Name"))
        col.addWidget(self.name_box)
        col.addSpacing(4)
        col.addWidget(self.heading("Length"))
        col.addLayout(edits)
        col.addSpacing(4)
        col.addWidget(self.heading("Post it"))
        self.post_titles = QLabel("")
        self.post_titles.setWordWrap(True)
        self.post_titles.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.post_tags = QLabel("")
        self.post_tags.setWordWrap(True)
        self.post_tags.setObjectName("mute")
        self.post_tags.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.post_copy = Button("Copy title and hashtags", "check")
        self.post_copy.clicked.connect(self.copy_post)
        col.addWidget(self.post_titles)
        col.addWidget(self.post_tags)
        col.addWidget(self.post_copy, 0, Qt.AlignmentFlag.AlignLeft)
        col.addStretch()
        return page

    def allowed(self, feature):
        return self.gate is None or self.gate.allowed(feature)

    def session_info(self):
        s = self.library.session(self.sid) if self.sid else None
        return (s["game"] or "", s["language"] or "") if s else ("", "")

    def show_post(self):
        """Title ideas and hashtags for the selected clip, or a Premium invitation."""
        if not self.clip:
            return
        if not self.allowed("titles"):
            self.post_titles.setText("Title ideas and hashtags for every clip are part of Premium.")
            self.post_tags.setText("")
            self.post_copy.setText("See Premium")
            return
        game, language = self.session_info()
        self.post_titles.setText("\n".join("• " + t for t in insights.titles(self.clip, game)))
        self.post_tags.setText(" ".join(insights.hashtags(self.clip, game, language)))
        self.post_copy.setText("Copy title and hashtags")

    def copy_post(self):
        if not self.allowed("titles"):
            self.upgrade.emit("titles")
            return
        from PySide6.QtWidgets import QApplication
        game, language = self.session_info()
        QApplication.clipboard().setText(insights.post_text(self.clip, game, language))
        self.say.emit("Title and hashtags copied", "good")

    def build_audio_tab(self):
        self.auto_loud = Toggle("Automatic loudness", True)
        self.auto_loud.setToolTip("Brings the clip to -14 LUFS, the level phones play at, without clipping")
        self.auto_loud.toggled.connect(lambda on: self.loading or self.set_edit(auto_loud=on))
        self.boost_note = QLabel("")
        self.boost_note.setObjectName("mute")
        self.boost_note.setWordWrap(True)
        self.gain = Dial("Clip volume", -12, 12, .5, "%+.1f dB")
        self.gain.moved.connect(self.gain_moved)
        self.gain.done.connect(lambda v: self.set_edit(gain_db=v))
        self.fade_in = Dial("Fade in", 0, 3, .1, "%.1f s")
        self.fade_in.done.connect(lambda v: self.set_edit(fade_in=v))
        self.fade_out = Dial("Fade out", 0, 3, .1, "%.1f s")
        self.fade_out.done.connect(lambda v: self.set_edit(fade_out=v))
        mute = Button("Mute marked part", "mute")
        mute.setToolTip("Silences the part between your I and O marks, and keeps the picture")
        mute.clicked.connect(self.mute_marked)
        unmute = Button("Clear mutes", "sound")
        unmute.clicked.connect(lambda: self.set_edit(mute=[]))
        row = QHBoxLayout()
        row.setSpacing(0)
        row.addWidget(mute)
        row.addWidget(unmute)
        row.addStretch()
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 4, 0, 0)
        col.setSpacing(6)
        for w in (self.auto_loud, self.boost_note, self.gain, self.fade_in, self.fade_out):
            col.addWidget(w)
        col.addLayout(row)
        col.addStretch()
        return page

    def build_caption_tab(self):
        self.words = QPlainTextEdit()
        self.words.setPlaceholderText("No clear speech here, so nothing was guessed. Type captions yourself, or export without them.")
        self.words.setMinimumHeight(70)
        self.save_timer = QTimer(self, singleShot=True, interval=500, timeout=self.save_words)
        self.words.textChanged.connect(self.words_typed)

        self.presets = [PresetChip(k) for k in caps.PRESETS]
        grid = QGridLayout()
        grid.setSpacing(6)
        for i, chip in enumerate(self.presets):
            chip.picked.connect(self.preset_picked)
            grid.addWidget(chip, i // 2, i % 2)

        self.cap_font = QComboBox()
        for label, family in caps.FONTS:
            self.cap_font.addItem(label, family)
        self.cap_font.currentIndexChanged.connect(lambda _: self.set_style(font=self.cap_font.currentData()))
        self.cap_mode = QComboBox()
        for label, value in caps.HIGHLIGHTS:
            self.cap_mode.addItem(label, value)
        self.cap_mode.currentIndexChanged.connect(lambda _: self.set_style(highlight_mode=self.cap_mode.currentData()))
        self.cap_anim = QComboBox()
        for label, value in caps.ANIMATIONS:
            self.cap_anim.addItem(label, value)
        self.cap_anim.currentIndexChanged.connect(lambda _: self.set_style(animation=self.cap_anim.currentData()))

        self.style_dials = {}
        for title, low, high, step, text, key in (
                ("Text size", 40, 170, 2, "%d", "size"), ("Height from bottom", 120, 1500, 20, "%d", "y"),
                ("Words on screen", 1, 8, 1, "%d", "words"), ("Outline", 0, 16, 1, "%d", "outline_width"),
                ("Shadow", 0, 10, 1, "%d", "shadow"), ("Box opacity", 0, 100, 5, "%d%%", "box_opacity"),
                ("Tilt", -15, 15, 1, "%+d\u00b0", "tilt"), ("Letter spacing", -2, 12, 1, "%d", "spacing")):
            dial = Dial(title, low, high, step, text)
            dial.moved.connect(lambda _: self.style_moved())
            dial.done.connect(lambda v, key=key: self.set_style(**{key: int(v)}))
            self.style_dials[key] = dial
        self.cap_toggles = {}
        for title, key in (("UPPERCASE", "upper"), ("Bold", "bold"), ("Italic", "italic"), ("Box behind", "box")):
            toggle = Toggle(title)
            toggle.toggled.connect(lambda on, key=key: self.loading or self.set_style(**{key: on}))
            self.cap_toggles[key] = toggle
        self.cap_colors = {}
        for title, key in (("Text", "text"), ("Highlight", "highlight"), ("Outline", "outline"),
                           ("Shadow", "shadow_color"), ("Box", "box_color")):
            well = ColorPick(title)
            well.picked.connect(lambda c, key=key: self.set_style(**{key: c}))
            self.cap_colors[key] = well
        self.swatches = [Swatch(c) for c in COLORS]
        quick = QHBoxLayout()
        quick.setSpacing(2)
        quick.addWidget(QLabel("Quick highlight"))
        for sw in self.swatches:
            sw.picked.connect(lambda c: self.set_style(highlight=c))
            quick.addWidget(sw)
        quick.addStretch()
        wells = QHBoxLayout()
        wells.setSpacing(4)
        for well in self.cap_colors.values():
            wells.addWidget(well)
        wells.addStretch()
        toggles = QGridLayout()
        for i, t in enumerate(self.cap_toggles.values()):
            toggles.addWidget(t, i // 2, i % 2)
        everywhere = Button("Use on all clips", "check")
        everywhere.setToolTip("Gives every clip of this stream this caption style, and makes it the style for new clips")
        everywhere.clicked.connect(self.style_everywhere)
        reset = Button("Reset to preset", flat=True)
        reset.clicked.connect(self.style_reset)
        buttons = QHBoxLayout()
        buttons.addWidget(everywhere)
        buttons.addWidget(reset)
        buttons.addStretch()

        heading = QLabel("Style")
        heading.setObjectName("mute")
        body = QWidget()
        col = QVBoxLayout(body)
        col.setContentsMargins(0, 4, 8, 0)
        col.setSpacing(6)
        col.addWidget(self.words)
        col.addWidget(heading)
        col.addLayout(grid)
        col.addLayout(buttons)
        form = QGridLayout()
        form.setHorizontalSpacing(8)
        for row, (text, widget) in enumerate((("Font", self.cap_font), ("Highlight", self.cap_mode),
                                              ("Animation", self.cap_anim))):
            form.addWidget(QLabel(text), row, 0)
            form.addWidget(widget, row, 1)
        col.addLayout(form)
        col.addLayout(wells)
        col.addLayout(quick)
        col.addLayout(toggles)
        for dial in self.style_dials.values():
            col.addWidget(dial)
        col.addStretch()
        scroll = QScrollArea()
        scroll.setWidget(body)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        return scroll

    # ---- caption style
    def default_style(self):
        return (self.settings.get("caption_style_default") if self.settings else None) or {}

    def current_style(self):
        return caps.style_of(self.clip["edit"] if self.clip else {}, self.default_style())

    def set_style(self, **values):
        """Saves a style change on this clip only. Keys the user never touched keep following the preset."""
        if not self.clip or self.loading:
            return
        own = dict(self.clip["edit"].get("caption_style") or {})
        own.update(values)
        self.set_edit(caption_style=own)

    def preset_picked(self, key):
        if self.clip and not self.loading:
            self.set_edit(caption_style={"preset": key})

    def style_reset(self):
        if self.clip:
            self.set_edit(caption_style={"preset": self.current_style()["preset"]})

    def style_everywhere(self):
        """One look for the whole stream, and for every new clip after it."""
        if not self.clip:
            return
        if self.gate and not self.gate.allowed("style_all", self.sid):
            self.upgrade.emit("style_all")
            return
        if self.gate:
            self.gate.use("style_all", self.sid)
        style = dict(self.clip["edit"].get("caption_style") or {"preset": self.current_style()["preset"]})
        for c in self.library.clips(self.sid):
            if c["id"] != self.clip["id"]:
                self.library.update_clip(c["id"], edit={**c["edit"], "caption_style": style})
        if self.settings:
            self.settings.set("caption_style_default", style)
        self.say.emit("This caption style is now on every clip, and new clips start with it", "good")
        self.reload()

    def show_style(self, st):
        """Puts a style into the controls without saving anything."""
        for chip in self.presets:
            chip.on = chip.key == st["preset"]
            chip.update()
        for box, key in ((self.cap_font, "font"), (self.cap_mode, "highlight_mode"), (self.cap_anim, "animation")):
            box.blockSignals(True)
            box.setCurrentIndex(max(box.findData(st[key]), 0))
            box.blockSignals(False)
        for key, dial in self.style_dials.items():
            dial.set(st[key])
        for key, toggle in self.cap_toggles.items():
            toggle.blockSignals(True)
            toggle.setChecked(bool(st[key]))
            toggle.blockSignals(False)
        for key, well in self.cap_colors.items():
            well.set(st[key])
        for sw in self.swatches:
            sw.on = sw.color == st["highlight"]
            sw.update()

    def build_look_tab(self):
        self.layout_box = Segmented(LAYOUTS)
        self.layout_box.changed.connect(self.layout_changed)
        self.pan = Dial("Crop position", -1, 1, .02, "%+.2f")
        self.pan.setToolTip("Centre crop only: slide the crop towards the action")
        self.pan.moved.connect(lambda _: self.style_moved())
        self.pan.done.connect(lambda v: self.set_edit(pan=v))
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 4, 0, 0)
        col.setSpacing(6)
        col.addWidget(self.heading("Layout"))
        col.addWidget(self.layout_box)
        col.addWidget(self.pan)
        col.addStretch()
        return page

    def saved_split(self):
        saved = self.settings.get("review_split") if self.settings else None
        return saved if saved and len(saved) == 3 else [350, 340, 480]

    def remember_split(self):
        if self.settings:
            self.settings.set("review_split", self.split.sizes())

    # ---- loading
    def open(self, sid):
        self.save_words()
        self.sid = sid
        self.undo_stack = []
        self.redo_stack = []
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
        self.fresh = not split
        self.player.setSource(QUrl() if split else QUrl.fromLocalFile(source))
        curve = np.zeros(1)
        self.loud = np.zeros(1)
        laugh, events = None, []
        try:
            with np.load(signals_file(sid)) as data:
                curve = data["curve"].astype(np.float32)
                self.loud = data["loud"].astype(np.float32)
                if "laugh" in data:
                    laugh = data["laugh"].astype(np.float32)
                if "events" in data:
                    import json
                    events = json.loads(str(data["events"]))
        except (OSError, KeyError, ValueError):
            pass            # streams analyzed by older versions have fewer saved signals until analyzed again
        self.clip = None
        self.row = -1
        self.build_cards()
        self.map.load(curve, self.duration, self.library.clips(sid), laugh, events)
        self.select(0)

    def build_cards(self):
        for card in self.cards:
            card.deleteLater()
        self.cards = []
        clips = self.library.clips(self.sid)
        scores = [c["score"] for c in clips if c["score"] < 100]
        best = max(scores) if scores else 1.0
        scored = self.allowed("virality")
        for i, c in enumerate(clips):
            card = ClipCard(c, clip_thumb(self.sid, c["peak"]), best)
            if scored:
                card.virality = insights.virality(c, best)
                card.setToolTip("Virality %d: %s" % (card.virality, insights.label(card.virality)))
            card.clicked.connect(lambda card=card: self.select(self.cards.index(card)))
            self.list_col.insertWidget(i, card)
            self.cards.append(card)
            card.enter(i)
        self.sort_cards()
        self.apply_filter()
        self.update_kept()

    def sort_cards(self):
        """Reorders the list without touching the clips, so a selection survives."""
        current = self.cards[self.row] if 0 <= self.row < len(self.cards) else None
        how = self.sort_box.currentData()
        if how == "viral" and not self.allowed("virality"):
            self.sort_box.setCurrentIndex(0)
            self.upgrade.emit("virality")
            return
        self.cards.sort(key=lambda c: c.clip["start"] if how == "time" else
                        -(c.virality or 0) if how == "viral" else c.clip["rank"])
        for i, card in enumerate(self.cards):
            self.list_col.removeWidget(card)
            self.list_col.insertWidget(i, card)
        if current:
            self.row = self.cards.index(current)

    def apply_filter(self):
        tag = self.filter_box.value()
        for card in self.cards:
            card.setVisible(not tag or tag in card.clip["tags"])

    def reload(self):
        """Refreshes in place, so finishing a job never restarts the page or loses the selection."""
        clips = self.library.clips(self.sid)
        if len(clips) != len(self.cards):
            keep = self.clip["id"] if self.clip else None
            self.build_cards()
            self.row = next((i for i, c in enumerate(self.cards) if c.clip["id"] == keep), -1)
            if self.row >= 0:
                self.cards[self.row].select(True)
        else:
            by_id = {c["id"]: c for c in clips}
            for card in self.cards:
                card.set_clip(by_id.get(card.clip["id"], card.clip))
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
        e = clip_edit.settings(c)
        self.keep = clip_edit.keep_ranges(c)
        reasons = "\n".join("•  " + r for r in c["reasons"])
        if clip_edit.length(c) > 60:
            reasons += "\n•  Over 60s: a copyright claim can block a Short worldwide"
        self.why.setText(reasons)
        self.name_box.setText(c["title"])
        self.layout_box.set(c["layout"])
        if self.words.toPlainText().split() != [w["w"] for w in c["words"]]:
            self.words.setPlainText(" ".join(w["w"] for w in c["words"]))
        self.open_file.setEnabled(bool(c["exported"]))
        self.undo_button.setEnabled(bool(self.undo_stack))
        self.redo_button.setEnabled(bool(self.redo_stack))
        self.auto_loud.setChecked(e["auto_loud"])
        self.gain.set(e["gain_db"])
        self.fade_in.set(e["fade_in"])
        self.fade_out.set(e["fade_out"])
        self.pan.set(e["pan"])
        style = self.current_style()
        self.show_style(style)
        self.show_post()
        self.update_boost()
        self.phone.set_style(e["pan"], style)
        self.phone.set_clip(c["words"], c["layout"], self.facecam())
        self.trim.load(self.loud, self.duration, c)
        self.map.set_active(c["id"])
        self.loading = False

    def update_boost(self):
        db = clip_edit.estimate_gain(self.loud, self.clip)
        self.audio.set_boost(db)
        if clip_edit.settings(self.clip)["auto_loud"]:
            self.boost_note.setText("This clip gets about %+.0f dB to reach phone loudness. The preview plays at that level." % db)
        else:
            self.boost_note.setText("The clip keeps its original level, plus your change below.")

    def gain_moved(self, value):
        if self.clip:
            self.audio.set_boost(clip_edit.estimate_gain(self.loud, {**self.clip, "edit": {**self.clip["edit"], "gain_db": value}}))

    def style_moved(self):
        """Shows a drag on the phone straight away. The clip itself changes when the slider is let go."""
        style = self.current_style()
        style.update({key: int(dial.value()) for key, dial in self.style_dials.items()})
        self.phone.set_style(self.pan.value(), style)

    # ---- editing
    def change(self, **fields):
        """Every edit goes through here, so everything can be undone."""
        if not self.clip:
            return
        before = {k: self.clip[k] for k in fields}
        self.undo_stack.append((self.clip["id"], before))
        self.redo_stack.clear()
        self.library.update_clip(self.clip["id"], **fields)
        self.clip = self.library.clip(self.clip["id"])
        self.reload()
        self.show_clip()

    def set_edit(self, **values):
        if self.clip and not self.loading:
            self.change(edit={**self.clip["edit"], **values})

    def restore(self, source, target):
        """Moves one edit from one stack to the other, returning the clip to how it was."""
        if not source:
            return
        entry = source.pop()
        if entry[0] == "split":
            self.flip_split(entry, target)
            return
        cid, fields = entry
        current = self.library.clip(cid)
        if current is None:
            return
        target.append((cid, {k: current[k] for k in fields}))
        self.library.update_clip(cid, **fields)
        for i, card in enumerate(self.cards):
            if card.clip["id"] == cid and i != self.row:
                self.cards[self.row].select(False)
                self.row = i
                card.select(True)
        self.clip = self.library.clip(cid)
        self.reload()
        self.show_clip()

    def flip_split(self, entry, target):
        _, cid, other, at = entry
        if other is None:
            other = self.library.split_clip(cid, at)
            target.append(("split", cid, other, at))
        else:
            self.library.join_clips(cid, other)
            target.append(("split", cid, None, at))
        self.clip = self.library.clip(cid)
        self.reload()
        self.show_clip()

    def undo(self):
        self.restore(self.undo_stack, self.redo_stack)

    def redo(self):
        self.restore(self.redo_stack, self.undo_stack)

    def trim_done(self, start, end):
        if self.clip and (abs(start - self.clip["start"]) > .02 or abs(end - self.clip["end"]) > .02):
            self.change(start=start, end=end)

    def here(self):
        """The playhead, counting a seek still on its way, so a mark always lands where the user sent it."""
        return self.pending if self.pending is not None else self.player.position() / 1000

    def set_start(self):
        if self.clip and self.here() < self.clip["end"] - 1:
            self.change(start=self.here())

    def set_end(self):
        if self.clip and self.here() > self.clip["start"] + 1:
            self.change(end=self.here())

    def mark_in(self):
        self.trim.set_marks(self.here(), self.trim.mark_out)

    def mark_out(self):
        self.trim.set_marks(self.trim.mark_in, self.here())

    def cut(self):
        marked = self.trim.marked()
        if not self.clip:
            return
        if not marked:
            return self.say.emit("Press I and O to mark a part first", "info")
        new = clip_edit.add_cut(self.clip, *marked)
        if new is None:
            return self.say.emit("That would cut away the whole clip", "info")
        self.trim.set_marks(None, None)
        self.change(edit=new)

    def mute_marked(self):
        marked = self.trim.marked()
        if not marked:
            return self.say.emit("Press I and O to mark a part first", "info")
        self.trim.set_marks(None, None)
        self.set_edit(mute=clip_edit.settings(self.clip)["mute"] + [list(marked)])

    def split_here(self):
        c = self.clip
        t = self.here()
        if not c or not c["start"] + 1 < t < c["end"] - 1:
            return self.say.emit("Move the playhead inside the clip first", "info")
        other = self.library.split_clip(c["id"], t)
        fresh = self.library.clip(other)
        media.frame_png(self.library.session(self.sid)["source"], fresh["peak"], clip_thumb(self.sid, fresh["peak"]), 480)
        self.undo_stack.append(("split", c["id"], other, t))
        self.redo_stack.clear()
        self.clip = self.library.clip(c["id"])
        self.reload()
        self.show_clip()

    def name_done(self):
        if self.clip and not self.loading and self.name_box.text().strip() != self.clip["title"]:
            self.change(title=self.name_box.text().strip())

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
            self.redo_stack.clear()
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
        """Moves through the list, passing over clips the filter has hidden."""
        row = self.row + delta
        while 0 <= row < len(self.cards):
            if not self.cards[row].isHidden():
                return self.select(row)
            row += delta

    # ---- preview
    def media_ready(self, status):
        """A seek before the file has loaded is ignored, so the first clip is positioned here."""
        if status == QMediaPlayer.MediaStatus.LoadedMedia and self.clip and self.fresh:
            self.fresh = False
            self.seek(self.clip["start"])
            self.player.play()

    def seek(self, t):
        self.audio.flush()
        self.pending = t
        self.settle.start()
        self.player.setPosition(int(t * 1000))

    def seek_done(self):
        self.pending = None

    def jump(self, seconds):
        if self.clip:
            self.seek(min(max(self.here() + seconds, 0.0), self.duration))

    def nudge(self, seconds):
        self.player.pause()
        self.jump(seconds)

    def go_start(self):
        if self.clip:
            self.seek(self.clip["start"])

    def go_end(self):
        if self.clip:
            self.player.pause()
            self.seek(self.clip["end"] - FRAME)

    def set_speed(self, value):
        self.audio.set_rate(float(value))
        self.player.setPlaybackRate(float(value))

    def set_loop(self, on):
        self.loop = on

    def set_mute(self, on):
        self.audio.set_muted(on)
        self.mute_button.icon_name = "mute" if on else "sound"
        self.mute_button.update()

    def toggle_mute(self):
        self.mute_button.setChecked(not self.mute_button.isChecked())

    def on_position(self, position):
        t = position / 1000
        if self.pending is not None:
            if abs(t - self.pending) > .5:
                return          # an old frame from before the seek: acting on it would fight the user
            self.pending = None
        if self.clip and self.trim.drag is None and self.keep and self.clip["start"] <= t:
            landing = clip_edit.skip_cut(t, self.keep)
            if landing is None and t < self.clip["end"] + 1:
                if self.loop:
                    return self.seek(self.keep[0][0])
                self.player.pause()
            elif landing is not None and landing - t > .05:
                return self.seek(landing)
        self.phone.set_time(t)
        self.trim.set_play(t)
        self.map.set_play(t)
        if self.clip:
            done = clip_edit.to_output(t, self.keep)
            self.clock.setText("%s / %s" % (clock(done or 0)[2:], clock(clip_edit.length(self.clip))[2:]))
            self.audio.set_silent(any(a <= t <= b for a, b in clip_edit.settings(self.clip)["mute"]))

    def on_playing(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.phone.set_paused(not playing)
        self.play_button.icon_name = "pause" if playing else "play"
        self.play_button.update()

    def toggle(self):
        playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self.player.pause() if playing else self.player.play()

    def pin_clicked(self, cid):
        """Opens the clip whose pin was clicked, even when a filter is hiding its card."""
        row = next((i for i, card in enumerate(self.cards) if card.clip["id"] == cid), -1)
        if row >= 0:
            if not self.cards[row].isVisible():
                self.filter_box.set("")
                self.apply_filter()
            self.select(row)

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

    def compilation(self):
        """The kept clips the filter shows, joined in stream order: 'only kills' gives a kills montage."""
        if not self.allowed("compilation"):
            self.upgrade.emit("compilation")
            return
        chosen = [c.clip for c in self.cards if c.isVisible() and c.clip["state"] in ("kept", "exported")]
        if len(chosen) < 2:
            self.say.emit("Keep at least two clips (K) for a compilation. The filter picks which kind.", "info")
            return
        self.save_words()
        kind = {"": "", "funny": "funny moments", "kills": "kills", "deaths": "deaths", "hype": "hype"}.get(
            self.filter_box.value(), "")
        session = self.library.session(self.sid)
        title = "Best %sof %s" % (kind + " " if kind else "", session["name"][:50])
        self.compile.emit(self.sid, [c["id"] for c in chosen], title)
        self.say.emit("Making a %d-clip compilation. It is saved with your clips." % len(chosen), "good")

    def export_all(self):
        if self.gate and not self.gate.allowed("batch"):
            self.upgrade.emit("batch")
            return
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
