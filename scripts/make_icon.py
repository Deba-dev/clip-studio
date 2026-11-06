"""Draws the app icon. Run once after changing the design: python scripts/make_icon.py"""
import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPolygonF

app = QGuiApplication([])
size = 256
image = QImage(size, size, QImage.Format.Format_ARGB32)
image.fill(Qt.GlobalColor.transparent)
p = QPainter(image)
p.setRenderHint(QPainter.RenderHint.Antialiasing)
g = QLinearGradient(0, 0, size, size)
g.setColorAt(0, QColor("#7c3aed"))
g.setColorAt(1, QColor("#c026d3"))
p.setBrush(QBrush(g))
p.setPen(Qt.PenStyle.NoPen)
p.drawRoundedRect(QRectF(8, 8, 240, 240), 58, 58)
p.setBrush(QColor("#ffffff"))
p.drawPolygon(QPolygonF([QPointF(96, 70), QPointF(190, 128), QPointF(96, 186)]))
p.end()
os.makedirs("assets", exist_ok=True)
if not image.save("assets/icon.ico"):
    raise SystemExit("Could not write the icon")
image.save("assets/icon.png")
