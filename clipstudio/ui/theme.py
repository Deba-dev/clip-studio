"""The ZunimiLabs dark violet look, shared with ChatDoom."""
from PySide6.QtGui import QColor

BG = QColor("#07051a")
PANEL = QColor(20, 13, 48, 215)
PANEL_HI = QColor(32, 21, 72, 235)
LINE = QColor(124, 58, 237, 70)
TEXT = QColor("#f6f4ff")
MUTE = QColor("#aaa6cc")
FAINT = QColor("#6d6890")
A1 = QColor("#7c3aed")
A2 = QColor("#c026d3")
A3 = QColor("#3b82f6")
GOOD = QColor("#34d399")
WARN = QColor("#fbbf24")
BAD = QColor("#f87171")
CAPTION = QColor("#ffe100")

QSS = """
* { font-family: "Segoe UI", "Nirmala UI", sans-serif; font-size: 13px; color: #f6f4ff; }
QMainWindow, QDialog { background: #07051a; }
QLabel { background: transparent; }
QLabel#h1 { font-size: 24px; font-weight: 700; }
QLabel#h2 { font-size: 14px; font-weight: 600; }
QLabel#mute { color: #aaa6cc; }
QLabel#why { color: #d6c9ff; font-size: 12px; }
QPlainTextEdit, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: rgba(12,8,36,0.85); border: 1px solid rgba(124,58,237,0.32); border-radius: 9px; padding: 7px 9px;
    selection-background-color: #7c3aed; }
QPlainTextEdit:focus, QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border: 1px solid #a855f7; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: #120c2e; border: 1px solid #3a2a78; selection-background-color: #7c3aed; }
QSpinBox::up-button, QSpinBox::down-button { width: 0; }
QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
QScrollBar::handle:vertical { background: rgba(170,166,204,0.28); border-radius: 3px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: rgba(192,38,211,0.7); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical, QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical { background: none; height: 0; }
QMenu { background: #140d30; border: 1px solid #3a2a78; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 7px 22px; border-radius: 6px; }
QMenu::item:selected { background: #7c3aed; }
QToolTip { background: #140d30; color: #f6f4ff; border: 1px solid #3a2a78; padding: 4px; }
"""
