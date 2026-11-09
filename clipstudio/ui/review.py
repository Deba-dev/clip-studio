"""The review desk: this is the product. Scan the shortlist, cut, fix the sound and the words, export."""
import json
import os
import tempfile

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QKeySequence, QPainter, QShortcut
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import (QColorDialog, QComboBox, QDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QScrollArea, QSlider, QSplitter, QStackedWidget,
                               QVBoxLayout, QWidget)

from .. import cleanup
from .. import edit as clip_edit
from .. import effects
from .. import games
from .gamepicker import GamePicker
from .. import teach
from .. import view
from .. import media
from .. import captions as caps
from .. import insights
from ..captions import apply_text
from ..paths import clip_thumb, signals_file
from ..render import resolve, stacking_cam
from ..worker import parse_facecam
from . import theme as T
from .audio import PreviewAudio
from .cards import ClipCard, clock
from .facecam import FacecamDialog
from .fx import Button, IconButton, Segmented, Toggle, to_trash
from .phone import Phone
from .timeline import StreamMap, TrimBar

LAYOUTS = [("Auto", "auto"), ("Webcam + game", "stack"), ("Full frame", "blur"), ("Centre crop", "crop")]
FILTERS = [("All", ""), ("Funny", "funny"), ("Kills", "kills"), ("Deaths", "deaths"), ("Hype", "hype")]
TABS = [("Clip", "clip"), ("Audio", "audio"), ("Captions", "captions"), ("Look", "look")]
SCOPES = [("This clip", "one"), ("All clips", "all")]
# What "All clips" carries to every clip. Cuts, mutes, length, name, hook and caption words are each clip's own.
SHARED_EDIT = {"auto_loud", "gain_db", "fade_in", "fade_out", "pan", "zoom", "tally", "caption_style"}
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
    find_kills = Signal(int)            # session: learn the marked kills and find every one
    clip_removed = Signal(int)          # clip: about to be deleted, so its waiting export is dropped

    def __init__(self, library, settings=None):
        super().__init__()
        self.library = library
        self.settings = settings
        self.gate = None            # set by the main window
        self.sid = None
        self.clip = None
        self.hook_for = None        # the clip whose hook the hook box shows
        self.exporting = set()      # clips with an export running
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
        self.game_box = GamePicker("Game: not set", "This stream's game, or what kind of stream it is (podcast, "
                                   "Just Chatting, IRL). Valorant is read from its HUD; games with a kill notice "
                                   "learn it from kills you mark; everything else is clipped from your voice, "
                                   "laughter and chat.")
        self.game_box.setMinimumWidth(210)
        self.game_box.changed.connect(lambda _: self.game_changed())
        self.reader_line = QLabel("")
        self.reader_line.setObjectName("mute")
        self.reader_line.setWordWrap(True)
        head = QHBoxLayout()
        head.addWidget(back)
        head.addWidget(self.title, 1)
        head.addWidget(self.game_box)
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
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search what was said: bhai, clutch, ace…")
        self.search.setToolTip("Finds words in any clip, in Hindi or Roman letters. Enter opens the first match "
                               "at the moment it was said.")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _: self.apply_filter())
        self.search.returnPressed.connect(self.open_match)
        self.list_side = QWidget()
        left = QVBoxLayout(self.list_side)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(6)
        left.addWidget(self.search)
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

        self.scope = Segmented(SCOPES)
        self.scope.setToolTip("All clips: sound, caption style, layout, zoom and kill counter changes go to every "
                              "clip of this stream. Cuts, length, name, hook and caption words stay per clip.")
        self.scope.changed.connect(lambda _: self.show_scope())
        self.scope_note = QLabel("")
        self.scope_note.setObjectName("mute")
        self.scope_note.setWordWrap(True)
        self.scope_note.hide()
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
        self.remove_button = Button("", "trash")
        self.remove_button.setToolTip("Remove this clip from the list and delete its exported video")
        self.remove_button.clicked.connect(self.remove_clip)
        acts = QHBoxLayout()
        acts.setSpacing(0)
        for w in (self.keep_button, self.skip, self.export_one, self.open_file, self.remove_button):
            acts.addWidget(w)
        acts.addStretch()
        self.side = QWidget()
        side = QVBoxLayout(self.side)
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(6)
        scope_row = QHBoxLayout()
        scope_row.setSpacing(8)
        scope_row.addWidget(QLabel("Settings for"))
        scope_row.addWidget(self.scope, 1)
        side.addLayout(scope_row)
        side.addWidget(self.scope_note)
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
        page.addWidget(self.reader_line)
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
        col.addWidget(self.heading("Hook"))
        self.hook_box = QLineEdit()
        self.hook_box.setPlaceholderText("Big text for the first 3 seconds, e.g. Bhai ye kya tha")
        self.hook_box.setToolTip("The first seconds decide whether people keep watching. Empty means no hook.")
        self.hook_box.setMaxLength(effects.HOOK_MAX)
        self.hook_box.textEdited.connect(lambda text: self.phone.set_effects(
            self.phone.zooms, effects.hook_lines(text), self.phone.hook_end))
        self.hook_box.editingFinished.connect(self.hook_done)
        suggest = Button("Suggest", "plus")
        suggest.setToolTip("Fills in a hook from this clip's title ideas. Press again for the next one.")
        suggest.clicked.connect(self.suggest_hook)
        hook_row = QHBoxLayout()
        hook_row.setSpacing(0)
        hook_row.addWidget(self.hook_box, 1)
        hook_row.addWidget(suggest)
        col.addLayout(hook_row)
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
        col.addSpacing(4)
        self.teach_head = self.heading("Teach a kill")
        col.addWidget(self.teach_head)
        self.teach_note = QLabel("")
        self.teach_note.setObjectName("mute")
        self.teach_note.setWordWrap(True)
        mark = self.mark_button = Button("This frame shows my kill", "skull")
        mark.setToolTip("Pause where your kill notice is on screen (the banner, the skull, \"knocked out\", "
                        "GOAL, K.O.), then press this. Two or three are enough; each one makes it better.")
        mark.clicked.connect(self.mark_kill)
        self.find_button = Button("Find every kill", "target")
        self.find_button.clicked.connect(self.find_every_kill)
        row = QHBoxLayout()
        row.setSpacing(0)
        row.addWidget(mark)
        row.addWidget(self.find_button)
        row.addStretch()
        col.addWidget(self.teach_note)
        col.addLayout(row)
        col.addStretch()
        return page

    def game_key(self):
        return self.game_box.currentData() or ""

    def game_changed(self):
        if self.loading or not self.sid:
            return
        self.library.update_session(self.sid, game=games.name_of(self.game_key()))
        self.show_teach()

    def show_teach(self):
        """What the lesson for this game knows so far, and what to do next."""
        key = self.game_key()
        if not key:
            self.teach_note.setText("Choose this stream's game at the top first.")
            self.teach_head.setText("Teach a kill")
            for w in (self.mark_button, self.find_button):
                w.setVisible(True)
            self.find_button.setEnabled(False)
            return
        name = games.name_of(key)
        word = games.notice_word(key)
        teachable = bool(word)
        for w in (self.mark_button, self.find_button):
            w.setVisible(teachable)
        self.teach_head.setText("Teach a " + (word or "kill"))
        if not teachable:
            self.teach_note.setText(games.no_notice(key) + " Mark any moment you want as a clip.")
            return
        plural = games.GAMES[key]["plural"]
        self.mark_button.setText("This frame shows my " + word)
        self.find_button.setText("Find every " + word)
        count = len(teach.examples(key))
        learned = teach.load(key) is not None
        if count < teach.MIN_EXAMPLES:
            text = ("Pause on a frame where your %s %s notice is showing and press the button. %d of %d marked." %
                    (name, word, count, teach.MIN_EXAMPLES))
        else:
            text = ("%d %s %s marked%s. Find every %s learns from them and adds a clip for each, here and on every "
                    "%s stream after this one." % (count, name, plural, ", already learned" if learned else "", word,
                                                  name))
        if key == "valorant":
            text = "Valorant is read from its HUD, no teaching needed. Teaching still helps a stream it could not read. " + text
        self.teach_note.setText(text)
        self.find_button.setEnabled(count >= teach.MIN_EXAMPLES)

    def mark_kill(self):
        key = self.game_key()
        if not key or not self.sid:
            self.say.emit("Choose this stream's game at the top first", "info")
            return
        session = self.library.session(self.sid)
        area = view.parse(session["view"])
        # Without a known game area yet, the background job finds it before reading this example.
        vf = view.game_filter(area, (self.size_info["width"], self.size_info["height"])) \
            if area and self.size_info else None
        t = self.player.position() / 1000
        count = teach.add_example(key, session["source"], t, vf)
        self.show_teach()
        self.say.emit("%s %d marked at %s" % ((games.notice_word(key) or "kill").capitalize(), count, clock(t)[2:]),
                      "good")

    def find_every_kill(self):
        if self.sid:
            self.find_button.set_busy(True)
            self.find_kills.emit(self.sid)
            self.say.emit("Learning your %s, then looking through the whole stream. It runs in the background." %
                          (games.notice_word(self.game_key()) or "kill"), "good")

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
        self.post_copy.done("Copied")

    def hook_done(self):
        """Saves the hook to the clip the box was showing, never to one selected since."""
        if self.clip and self.clip["id"] == self.hook_for and \
                self.hook_box.text().strip() != clip_edit.settings(self.clip)["hook"]:
            self.set_edit(hook=self.hook_box.text().strip())

    def suggest_hook(self):
        """Cycles through the clip's title ideas. They are a Premium feature, so the hook box stays free to type in."""
        if not self.clip:
            return
        if not self.allowed("titles"):
            self.upgrade.emit("titles")
            return
        ideas = insights.titles(self.clip, self.session_info()[0])
        if not ideas:
            return
        now = clip_edit.settings(self.clip)["hook"]
        self.set_edit(hook=ideas[(ideas.index(now) + 1) % len(ideas)] if now in ideas else ideas[0])

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
        col.addSpacing(6)
        col.addWidget(self.heading("Punch-in zoom"))
        self.zoom = Toggle("Zoom in on kills, deaths and laughs", True)
        self.zoom.setToolTip("Snaps in on the game at the second of each kill or death, and on your webcam when you "
                             "laugh. The times come from the game's HUD and the sound, not from guessing.")
        self.zoom.toggled.connect(lambda on: self.loading or self.set_edit(zoom=on))
        self.zoom_note = QLabel("")
        self.zoom_note.setObjectName("mute")
        self.zoom_note.setWordWrap(True)
        col.addWidget(self.zoom)
        col.addWidget(self.zoom_note)
        col.addSpacing(6)
        col.addWidget(self.heading("Kill counter"))
        self.tally = Toggle("Pop up KILL, DOUBLE KILL, TRIPLE KILL on each kill", True)
        self.tally.setToolTip("Named the way your game names them: Ace in Valorant, 3K in CS2, Squad wipe in BGMI.")
        self.tally.toggled.connect(lambda on: self.loading or self.set_edit(tally=on))
        col.addWidget(self.tally)
        col.addStretch()
        return page

    def show_effects(self):
        """Zooms and the hook on the phone, and a plain count of what will zoom."""
        c = self.clip
        e = clip_edit.settings(c)
        layout = resolve(c["layout"], self.facecam())
        zooms = effects.zoom_windows(c, layout)
        self.phone.set_effects(zooms, effects.hook_lines(e["hook"]),
                               min(effects.HOOK_SECONDS, clip_edit.length(c)),
                               effects.tally(c, self.game_key() or "valorant"))
        kinds = [v["kind"] for v in c.get("events") or [] if v["kind"] in effects.KINDS
                 and c["start"] <= v["t"] <= c["end"] and (v["kind"] != "laugh" or layout == "stack")]
        names = {"kill": ("kill", "kills"), "clutch": ("clutch", "clutches"), "death": ("death", "deaths"),
                 "laugh": ("laugh", "laughs")}
        found = ", ".join("%d %s" % (kinds.count(k), names[k][kinds.count(k) > 1]) for k in names if k in kinds)
        if not kinds:
            laughs = any(v["kind"] == "laugh" for v in c.get("events") or [])
            self.zoom_note.setText("Your laugh zooms the webcam in the Webcam + game layout." if laughs else
                                   "No kills, deaths or laughs were found in this clip, so nothing zooms.")
        elif not e["zoom"]:
            self.zoom_note.setText("Off. It would zoom on %s." % found)
        else:
            self.zoom_note.setText("Zooms on %s. Play the clip to see it on the phone." % found)

    def saved_split(self):
        saved = self.settings.get("review_split") if self.settings else None
        return saved if saved and len(saved) == 3 else [350, 340, 480]

    def remember_split(self):
        if self.settings:
            self.settings.set("review_split", self.split.sizes())

    # ---- loading
    def open(self, sid):
        self.save_words()
        self.hook_done()
        self.sid = sid
        self.undo_stack = []
        self.redo_stack = []
        if self.all_clips():        # a new stream starts on single-clip changes, so nothing spreads by surprise
            self.scope.set("one")
        self.show_scope()
        session = self.library.session(sid)
        self.title.setText(self.title.fontMetrics().elidedText(session["name"], Qt.TextElideMode.ElideRight, 520))
        self.loading = True
        self.game_box.set(games.key_of(session["game"]))
        self.loading = False
        try:
            seen = json.loads(session["report"] or "{}")
        except ValueError:
            seen = {}
        self.reader_line.setText(games.describe(seen))
        self.reader_line.setVisible(bool(seen))
        self.show_teach()
        source = session["source"]
        self.duration = session["duration"] or 1.0
        try:
            self.size_info = media.probe(source)
        except (RuntimeError, OSError):     # an unreadable file, or no FFmpeg to read it with
            self.size_info = None
        self.phone.source_size = (self.size_info["width"], self.size_info["height"]) if self.size_info else None
        split = source.endswith(".ffconcat")
        self.phone.clear()
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
        query = self.search.text()
        for card in self.cards:
            card.setVisible((not tag or tag in card.clip["tags"]) and
                            (not query.strip() or insights.find(card.clip, query) is not None))

    def open_match(self):
        """Enter in the search box: the first match in the list, playing from just before the words."""
        row = next((i for i, card in enumerate(self.cards) if card.isVisible()), -1) if self.search.text().strip() else -1
        if row >= 0:
            self.select(row)

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
        self.hook_done()
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
        said = insights.find(self.clip, self.search.text()) if self.search.text().strip() else None
        self.seek(min(max(said - 1.0, self.clip["start"]), self.clip["end"]) if said is not None else self.clip["start"])
        self.player.play()

    def facecam(self):
        """The webcam box the layouts use: none for a vertical recording, which is shown whole (render.stacking_cam)."""
        size = (self.size_info["width"], self.size_info["height"]) if self.size_info else None
        cam = parse_facecam(self.library.session(self.sid)["facecam"])
        return stacking_cam(cam, size) if size else cam

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
        self.show_exporting()
        self.undo_button.setEnabled(bool(self.undo_stack))
        self.redo_button.setEnabled(bool(self.redo_stack))
        self.auto_loud.setChecked(e["auto_loud"])
        self.gain.set(e["gain_db"])
        self.fade_in.set(e["fade_in"])
        self.fade_out.set(e["fade_out"])
        self.pan.set(e["pan"])
        self.zoom.setChecked(e["zoom"])
        self.tally.setChecked(e["tally"])
        if not self.hook_box.hasFocus() or self.hook_for != c["id"]:
            self.hook_box.setText(e["hook"])
        self.hook_for = c["id"]
        self.show_effects()
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
            if self.all_clips() and set(values) <= SHARED_EDIT:
                self.change_all(edit=values)
            else:
                self.change(edit={**self.clip["edit"], **values})

    # ---- all clips at once
    def all_clips(self):
        return self.scope.value() == "all"

    def show_scope(self):
        count = len(self.library.clips(self.sid)) if self.sid else 0
        self.scope_note.setText("Changes below go to all %d clips of this stream. Cuts, length, name, hook and "
                                "caption words stay per clip." % count)
        self.scope_note.setVisible(self.all_clips())

    def change_all(self, edit=None, **fields):
        """One change on every clip of the stream, undone in one step."""
        if not self.clip:
            return
        if edit and "caption_style" in edit:
            if self.gate and not self.gate.allowed("style_all", self.sid):
                self.upgrade.emit("style_all")
                self.show_clip()            # the controls go back to what the clip really has
                return
            if self.gate:
                self.gate.use("style_all", self.sid)
            if self.settings:
                self.settings.set("caption_style_default", edit["caption_style"])
        entries = []
        for c in self.library.clips(self.sid):
            new = dict(fields)
            if edit:
                new["edit"] = {**c["edit"], **edit}
            entries.append((c["id"], {k: c[k] for k in new}))
            self.library.update_clip(c["id"], **new)
        self.undo_stack.append(("many", entries))
        self.redo_stack.clear()
        self.clip = self.library.clip(self.clip["id"])
        self.reload()
        self.show_clip()

    def restore(self, source, target):
        """Moves one edit from one stack to the other, returning the clip to how it was."""
        if not source:
            return
        entry = source.pop()
        if entry[0] == "split":
            self.flip_split(entry, target)
            return
        if entry[0] == "many":
            back = []
            for cid, fields in entry[1]:
                current = self.library.clip(cid)
                if current is not None:
                    back.append((cid, {k: current[k] for k in fields}))
                    self.library.update_clip(cid, **fields)
            target.append(("many", back))
            if self.clip:
                self.clip = self.library.clip(self.clip["id"])
            self.reload()
            self.show_clip()
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
        if not self.loading and self.clip and self.all_clips():
            self.change_all(layout=value)
        elif not self.loading and self.clip and value != self.clip["layout"]:
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
        done = clip_edit.to_output(t, self.keep) if self.clip and self.keep else None
        self.phone.set_time(t, done)
        self.trim.set_play(t)
        self.map.set_play(t)
        if self.clip:
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
        if value > 0:
            self.exporting.add(cid)
        else:
            self.exporting.discard(cid)
        self.show_exporting()

    def show_exporting(self):
        """The Export button spins while this clip is being exported, so it is never started twice."""
        self.export_one.set_busy(bool(self.clip) and self.clip["id"] in self.exporting)

    def export_finished(self, cid, ok):
        self.exporting.discard(cid)
        self.show_exporting()
        if ok and self.clip and self.clip["id"] == cid:
            self.export_one.done("Exported")

    def kills_finished(self, found=None):
        self.find_button.set_busy(False)
        if found is not None:
            self.find_button.done("Found %d" % found, 1800)

    def burst_origin(self, root):
        return self.phone.mapTo(root, QPointF(self.phone.width() / 2, self.phone.height() * .55).toPoint())

    def remove_clip(self):
        """Takes the clip off the list for good: its exported video and preview picture are deleted too."""
        if not self.clip:
            return
        c = self.clip
        if c["id"] in self.exporting:
            self.say.emit("This clip is being exported. Remove it once the export is done.", "info")
            return
        files = cleanup.clip_files(self.library, c)
        videos = [f for f in files if f.lower().endswith((".mp4", ".txt"))]
        exported = [f for f in videos if f.lower().endswith(".mp4")]
        text = "Remove this clip from the list?"
        if exported:
            text += ("\n\nIts exported video (%s) is deleted too. It goes to the Recycle Bin."
                     % os.path.basename(exported[0]))
        if self.ask(text) != QMessageBox.StandardButton.Yes:
            return
        self.save_timer.stop()
        self.clip_removed.emit(c["id"])
        stuck = cleanup.discard(videos, to_trash)
        cleanup.discard([f for f in files if f not in videos])
        self.library.delete_clip(c["id"])
        self.forget_undo(c["id"])
        row = self.row
        self.clip = None
        self.row = -1
        self.build_cards()
        self.map.clips = self.library.clips(self.sid)
        self.map.update()
        self.show_scope()
        if self.cards:
            self.select(min(row, len(self.cards) - 1))
        else:
            self.player.stop()
        if stuck:
            self.say.emit("Removed. %s is open in another app, so it stays on disk." % os.path.basename(stuck[0]),
                          "info")
        else:
            self.say.emit("Clip removed" + (" and its video deleted" if exported else ""), "good")

    def ask(self, text):
        return QMessageBox.question(self, "Clip Studio", text)

    def forget_undo(self, cid):
        """Undo steps for a clip that no longer exists can only fail."""
        def keep(e):
            if e[0] == "split":
                return cid not in (e[1], e[2])
            if e[0] == "many":
                e[1][:] = [x for x in e[1] if x[0] != cid]
                return bool(e[1])
            return e[0] != cid
        self.undo_stack = [e for e in self.undo_stack if keep(e)]
        self.redo_stack = [e for e in self.redo_stack if keep(e)]

    def close_stream(self):
        """The stream is being removed: let go of its recording and forget its clips."""
        self.save_timer.stop()
        self.player.stop()
        self.player.setSource(QUrl())
        for card in self.cards:
            card.deleteLater()
        self.cards = []
        self.clip = None
        self.row = -1
        self.sid = None
        self.undo_stack = []
        self.redo_stack = []

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
