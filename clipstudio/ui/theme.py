"""The ZunimiLabs dark violet look, shared with ChatDoom."""

QSS = """
* { font-family: "Segoe UI", "Nirmala UI", sans-serif; font-size: 13px; color: #f6f4ff; }
QMainWindow, QWidget#root, QDialog { background: #05031a; }
QFrame#side { background: #0d0728; border-right: 1px solid rgba(124,58,237,0.35); }
QLabel#logo { font-size: 19px; font-weight: 700; padding: 18px 16px 2px 16px; }
QLabel#tag { color: #aaa6cc; font-size: 11px; padding: 0 16px 14px 16px; }
QLabel#h1 { font-size: 21px; font-weight: 700; }
QLabel#mute { color: #aaa6cc; }
QLabel#why { color: #c9b8ff; font-size: 12px; }
QPushButton { background: #1a1140; border: 1px solid rgba(124,58,237,0.45); border-radius: 8px; padding: 7px 13px; }
QPushButton:hover { background: #2a1a63; }
QPushButton:disabled { color: #6d6890; border-color: #2a2550; }
QPushButton#primary { background: #7c3aed; border: none; font-weight: 600; }
QPushButton#primary:hover { background: #9153f5; }
QPushButton#primary:disabled { background: #2a2053; color: #8f8ab0; }
QPushButton#nav { background: transparent; border: none; text-align: left; padding: 10px 16px; border-radius: 0; }
QPushButton#nav:checked { background: rgba(124,58,237,0.28); border-left: 3px solid #c026d3; font-weight: 600; }
QListWidget, QPlainTextEdit, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: #0f0a2c; border: 1px solid #2a2053; border-radius: 8px; padding: 5px; }
QListWidget::item { padding: 2px; border-radius: 6px; }
QListWidget::item:selected { background: rgba(124,58,237,0.32); }
QComboBox QAbstractItemView { background: #0f0a2c; selection-background-color: #7c3aed; }
QProgressBar { background: #0f0a2c; border: none; border-radius: 4px; height: 8px; text-align: center; color: transparent; }
QProgressBar::chunk { background: #c026d3; border-radius: 4px; }
QCheckBox::indicator { width: 16px; height: 16px; }
QVideoWidget { background: #000; }
"""
