"""Drag a box around the webcam once per session. Fixed webcam overlays make this all the framing a clip needs."""
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QRubberBand, QVBoxLayout


class Picture(QLabel):
    def __init__(self, pixmap):
        super().__init__()
        self.setPixmap(pixmap)
        self.setFixedSize(pixmap.size())
        self.band = QRubberBand(QRubberBand.Shape.Rectangle, self)
        self.origin = QPoint()

    def mousePressEvent(self, event):
        self.origin = event.position().toPoint()
        self.band.setGeometry(QRect(self.origin, QSize()))
        self.band.show()

    def mouseMoveEvent(self, event):
        self.band.setGeometry(QRect(self.origin, event.position().toPoint()).normalized().intersected(self.rect()))


class FacecamDialog(QDialog):
    def __init__(self, image_path, video_size, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mark your webcam")
        self.video_size = video_size
        self.cleared = False
        pixmap = QPixmap(image_path).scaledToWidth(960, Qt.TransformationMode.SmoothTransformation)
        self.picture = Picture(pixmap)
        tip = QLabel("Drag a box around your webcam. Clips will stack it above the gameplay.")
        tip.setObjectName("mute")
        save = QPushButton("Save")
        save.setObjectName("primary")
        none = QPushButton("I have no webcam")
        save.clicked.connect(self.accept)
        none.clicked.connect(self._clear)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(none)
        row.addWidget(save)
        box = QVBoxLayout(self)
        box.addWidget(tip)
        box.addWidget(self.picture)
        box.addLayout(row)

    def _clear(self):
        self.cleared = True
        self.accept()

    def value(self):
        """The rectangle in real video pixels, as text for the library, or "" for none."""
        if self.cleared or not self.picture.band.isVisible():
            return ""
        rect = self.picture.band.geometry()
        if rect.width() < 10 or rect.height() < 10:
            return ""
        scale = self.video_size[0] / self.picture.width()
        return ",".join(str(int(v * scale)) for v in (rect.x(), rect.y(), rect.width(), rect.height()))
