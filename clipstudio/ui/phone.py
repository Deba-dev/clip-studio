"""A live phone: the real video in the real 9:16 layout with the real captions, before anything is exported."""
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen
from PySide6.QtMultimedia import QVideoSink
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..captions import MAX_CHARS, group_words
from . import theme as T
from .cards import cover, rounded
from .fx import alpha, draw_icon, font, glow, tween

CAM_SHARE = 680 / 1920
CAPTION_Y = 1360 / 1920     # matches the bottom margin of the exported captions


class Phone(QWidget):
    tapped = Signal()

    def __init__(self):
        super().__init__()
        self.sink = QVideoSink(self)
        self.sink.videoFrameChanged.connect(self.on_frame)
        self.frame = QImage()
        self.layout_name = "auto"
        self.facecam = None
        self.source_size = None
        self.lines = []
        self.time = 0.0
        self.paused = True
        self.pause_mark = 1.0
        self.note = ""
        self.setMinimumSize(200, 340)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(300, 520)

    def on_frame(self, frame):
        image = frame.toImage()
        if not image.isNull():
            self.frame = image
            self.update()

    def set_clip(self, words, layout, facecam):
        self.lines = group_words(words)
        self.layout_name = layout
        self.facecam = facecam
        self.update()

    def set_layout(self, layout):
        self.layout_name = layout
        self.update()

    def set_time(self, t):
        self.time = t
        self.update()

    def set_paused(self, paused):
        self.paused = paused
        tween(self, "pause_mark", 1 if paused else 0, 180)

    def mousePressEvent(self, event):
        self.tapped.emit()

    def screen_rect(self):
        h = self.height() - 10
        w = h * 9 / 16
        if w > self.width() - 16:
            w = self.width() - 16
            h = w * 16 / 9
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        s = self.screen_rect()
        body = s.adjusted(-5, -5, 5, 5)
        glow(p, body, 22, T.A1, 1.1, 8)
        p.setBrush(QColor(4, 3, 14))
        p.setPen(QPen(alpha(T.TEXT, 50), 1.2))
        p.drawRoundedRect(body, 22, 22)
        p.save()
        p.setClipPath(rounded(s, 18))
        p.fillRect(s, QColor(10, 7, 26))
        if not self.frame.isNull():
            self.draw_video(p, s)
        elif self.note:
            p.setPen(T.MUTE)
            p.setFont(font(12))
            p.drawText(s.adjusted(16, 0, -16, 0), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.note)
        self.draw_caption(p, s)
        p.restore()
        p.setBrush(QColor(4, 3, 14))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(s.center().x() - 26, s.y() + 7, 52, 10), 5, 5)
        if self.pause_mark > .01:
            c = s.center()
            p.setOpacity(self.pause_mark)
            p.setBrush(QColor(8, 5, 26, 170))
            p.drawEllipse(c, 28, 28)
            draw_icon(p, "play", QRectF(c.x() - 14, c.y() - 14, 28, 28), T.TEXT, 1.5, fill=True)
            p.setOpacity(1)

    def draw_video(self, p, s):
        image = self.frame
        layout = self.layout_name
        cam = self.scaled_cam()
        if layout == "auto":
            layout = "stack" if cam else "blur"
        if layout == "stack" and cam:
            top = QRectF(s.x(), s.y(), s.width(), s.height() * CAM_SHARE)
            bottom = QRectF(s.x(), top.bottom(), s.width(), s.height() - top.height())
            source = image.copy(*cam)
            self.fill(p, source, top)
            self.fill(p, image, bottom)
        elif layout == "crop":
            self.fill(p, image, s)
        else:
            tiny = image.scaled(48, 27, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.fill(p, tiny, s)
            p.fillRect(s, QColor(0, 0, 0, 60))
            height = s.width() * image.height() / max(image.width(), 1)
            p.drawImage(QRectF(s.x(), s.center().y() - height / 2, s.width(), height), image)

    @staticmethod
    def fill(p, image, rect):
        scale = max(rect.width() / image.width(), rect.height() / image.height())
        w, h = rect.width() / scale, rect.height() / scale
        p.drawImage(rect, image, QRectF((image.width() - w) / 2, (image.height() - h) / 2, w, h))

    def scaled_cam(self):
        if not self.facecam or not self.source_size:
            return None
        k = self.frame.width() / max(self.source_size[0], 1)
        return tuple(int(v * k) for v in self.facecam)

    def draw_caption(self, p, s):
        line = next((l for l in self.lines if l[0]["s"] <= self.time <= l[-1]["e"] + .35), None)
        if not line:
            return
        size = s.width() * 84 / 1080
        f = font(int(size), QFont.Weight.Bold)
        f.setFamilies(["Nirmala UI", "Segoe UI"])
        p.setFont(f)
        metrics = QFontMetricsF(f)
        texts = [w["w"] for w in line]
        space = metrics.horizontalAdvance(" ")
        total = sum(metrics.horizontalAdvance(t) for t in texts) + space * (len(texts) - 1)
        x = s.center().x() - total / 2
        y = s.y() + s.height() * CAPTION_Y
        current = next((i for i in range(len(line) - 1, -1, -1) if line[i]["s"] <= self.time), 0)
        for i, text in enumerate(texts):
            path = QPainterPath()
            path.addText(x, y, f, text)
            p.setPen(QPen(QColor(0, 0, 0), max(size * .16, 1.5), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                          Qt.PenJoinStyle.RoundJoin))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(T.CAPTION if i == current else T.TEXT)
            p.drawPath(path)
            x += metrics.horizontalAdvance(text) + space
