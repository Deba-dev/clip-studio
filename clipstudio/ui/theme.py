"""Clip Studio's looks: Film suite (warm graphite and tangerine, the default) and Midnight gold.

Every colour is one QColor object that `use()` repaints in place, so a widget that kept a colour from import time
still follows a change of look. The QSS is rebuilt from the same tokens.
"""
from string import Template

from PySide6.QtGui import QColor

LOOKS = {
    "film": {"label": "Film suite", "BG": "#141110", "DEEP": "#0c0a09", "SURF": "#1e1a18", "SURF_HI": "#2c2522",
             "PANEL": (30, 26, 24, 215), "PANEL_HI": (44, 37, 33, 235), "LINE": (255, 122, 26, 58),
             "TEXT": "#fbefe0", "MUTE": "#b5a597", "FAINT": "#7a6d62",
             "A1": "#ff7a1a", "A2": "#ffb347", "A3": "#ffe8c2", "ON": "#1a0d03",
             "AURORA": (("A1", 46), ("A2", 22), ("A3", 10))},
    "midnight": {"label": "Midnight gold", "BG": "#070a14", "DEEP": "#04060d", "SURF": "#0f1526", "SURF_HI": "#18223c",
                 "PANEL": (15, 21, 38, 215), "PANEL_HI": (24, 34, 60, 235), "LINE": (245, 196, 81, 55),
                 "TEXT": "#eef1fb", "MUTE": "#8e98b8", "FAINT": "#5b6585",
                 "A1": "#f5c451", "A2": "#e0963a", "A3": "#8fb0ff", "ON": "#1a1302",
                 "AURORA": (("A3", 40), ("A1", 22), ("A2", 12))},
}
DEFAULT_LOOK = "film"

BG, DEEP, SURF, SURF_HI = QColor(), QColor(), QColor(), QColor()
PANEL, PANEL_HI, LINE = QColor(), QColor(), QColor()
TEXT, MUTE, FAINT = QColor(), QColor(), QColor()
A1, A2, A3, ON = QColor(), QColor(), QColor(), QColor()
GOOD = QColor("#34d399")
WARN = QColor("#fbbf24")
BAD = QColor("#f87171")
CAPTION = QColor("#ffe100")
TAGS = {"funny": ("Funny", "laugh", QColor("#fbbf24")), "kills": ("Kill", "target", QColor("#34d399")),
        "deaths": ("Death", "skull", QColor("#f87171")), "hype": ("Hype", "bolt", QColor("#c084fc")),
        "marked": ("Marked", "star", QColor("#ffe100"))}
LOOK = DEFAULT_LOOK
QSS = ""


def aurora():
    """The background's three lights for this look: (colour, strength 0-255)."""
    return [(globals()[name], power) for name, power in LOOKS[LOOK]["AURORA"]]


def deep(a=255):
    """The darkest shade of the look, for scrims and behind pictures."""
    c = QColor(DEEP)
    c.setAlpha(int(a))
    return c


def surf(a=255, hi=0.0):
    """A raised surface (cards, dialogs, idle buttons); hi moves it toward the hover shade."""
    c = QColor(SURF.red() + (SURF_HI.red() - SURF.red()) * hi, SURF.green() + (SURF_HI.green() - SURF.green()) * hi,
               SURF.blue() + (SURF_HI.blue() - SURF.blue()) * hi)
    c.setAlpha(int(a))
    return c


_QSS = Template("""
* { font-family: "Segoe UI Variable Display", "Segoe UI", "Nirmala UI", sans-serif; font-size: 13px; color: $text; }
QMainWindow, QDialog { background: $bg; }
QLabel { background: transparent; }
QLabel#h1 { font-size: 25px; font-weight: 800; }
QLabel#h2 { font-size: 14px; font-weight: 700; }
QLabel#mute { color: $mute; }
QLabel#why { color: $a3; font-size: 12px; }
QPlainTextEdit, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: $deep; border: 1px solid $line; border-radius: 8px; padding: 7px 9px;
    selection-background-color: $a1; selection-color: $on; }
QPlainTextEdit:focus, QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border: 1px solid $a1; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: $surf; border: 1px solid $line; selection-background-color: $a1;
    selection-color: $on; }
QSpinBox::up-button, QSpinBox::down-button { width: 0; }
QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
QScrollBar::handle:vertical { background: $faint; border-radius: 3px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: $a1; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical, QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical { background: none; height: 0; }
QMenu { background: $surf; border: 1px solid $line; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 7px 22px; border-radius: 6px; }
QMenu::item:selected { background: $a1; color: $on; }
QSlider::groove:horizontal { height: 5px; border-radius: 2px; background: $surfhi; }
QSlider::sub-page:horizontal { height: 5px; border-radius: 2px; background: $a1; }
QSlider::handle:horizontal { background: $text; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }
QSlider::handle:horizontal:hover { background: $a1; }
QSplitter::handle { background: transparent; }
QSplitter::handle:hover { background: $a1; border-radius: 2px; }
QToolTip { background: $surf; color: $text; border: 1px solid $line; padding: 4px; }
""")


def _set(color, value):
    color.setRgba(QColor(*value).rgba() if isinstance(value, tuple) else QColor(value).rgba())


def use(name):
    """Switches every colour to a look ("film" or "midnight") and rebuilds QSS. Returns the QSS to apply."""
    global LOOK, QSS
    LOOK = name if name in LOOKS else DEFAULT_LOOK
    look = LOOKS[LOOK]
    for key, color in (("BG", BG), ("DEEP", DEEP), ("SURF", SURF), ("SURF_HI", SURF_HI), ("PANEL", PANEL),
                       ("PANEL_HI", PANEL_HI), ("LINE", LINE), ("TEXT", TEXT), ("MUTE", MUTE), ("FAINT", FAINT),
                       ("A1", A1), ("A2", A2), ("A3", A3), ("ON", ON)):
        _set(color, look[key])
    line = QColor(*look["LINE"])
    QSS = _QSS.substitute(bg=BG.name(), deep=DEEP.name(), surf=SURF.name(), surfhi=SURF_HI.name(), text=TEXT.name(),
                          mute=MUTE.name(), faint=FAINT.name(), a1=A1.name(), a3=A3.name(), on=ON.name(),
                          line="rgba(%d,%d,%d,%.2f)" % (line.red(), line.green(), line.blue(), line.alphaF() * 1.6))
    return QSS


use(DEFAULT_LOOK)
