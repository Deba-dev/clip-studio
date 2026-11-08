"""A live phone: the real video in the real 9:16 layout with the real captions, before anything is exported."""
import time

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen
from PySide6.QtMultimedia import QVideoSink
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..captions import HOLD, font_for, group_words, shown, style_of
from . import theme as T
from .cards import cover, rounded
from .fx import alpha, draw_icon, font, glow, tween

CAM_SHARE = 680 / 1920
FPS = 30                # the preview's own frame rate: smooth to the eye, half the work of a 60 fps stream
SMOOTH = Qt.TransformationMode.SmoothTransformation


class Phone(QWidget):
    tapped = Signal()

    def __init__(self):
        super().__init__()
        self.sink = QVideoSink(self)
        self.sink.videoFrameChanged.connect(self.on_frame)
        self.frame = QImage()           # the latest frame at full size
        self.incoming = None            # a decoded frame not converted yet: only the newest is ever converted
        self.serial = 0
        self.shown_at = 0.0
        self.cache_key = None
        self.small = self.tiny = self.cam_image = QImage()
        self.later = QTimer(self, singleShot=True, timeout=self.update)
        self.layout_name = "auto"
        self.facecam = None
        self.source_size = None
        self.lines = []
        self.time = 0.0
        self.paused = True
        self.pause_mark = 1.0
        self.note = ""
        self.pan = 0.0
        self.style = style_of({})
        self.words = []
        self.setMinimumSize(200, 340)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(300, 520)

    def on_frame(self, frame):
        """Only notes the frame. Converting every decoded frame of a 1080p60 stream on the UI thread was the lag:
        now frames that arrive faster than the preview draws are skipped, and only the newest one is converted."""
        self.incoming = frame
        wait = self.shown_at + 1 / FPS - time.monotonic()
        if wait <= 0:
            self.update()
        elif not self.later.isActive():
            self.later.start(int(wait * 1000) + 1)

    def clear(self):
        self.incoming = None
        self.frame = QImage()
        self.cache_key = None
        self.update()

    def take_frame(self):
        if self.incoming is None:
            return
        image = self.incoming.toImage()
        self.incoming = None
        self.shown_at = time.monotonic()
        if not image.isNull():
            self.frame = image
            self.serial += 1

    def prepare(self, s):
        """The frame at the size it is drawn, built once per frame instead of being scaled down on every repaint."""
        dpr = self.devicePixelRatioF()
        key = (self.serial, int(s.width() * dpr), int(s.height() * dpr), self.facecam, self.source_size)
        if key == self.cache_key:
            return
        self.cache_key = key
        image = self.frame
        self.small = image          # drawn straight from the frame: a smooth pre-scale costs more than it saves
        quarter = image.scaled(max(image.width() // 8, 48), max(image.height() // 8, 27))
        self.tiny = quarter.scaled(48, 27, Qt.AspectRatioMode.IgnoreAspectRatio, SMOOTH)
        self.cam_image = QImage()
        cam = self.scaled_cam(image)
        if cam:
            crop = image.copy(*cam)
            if not crop.isNull():
                k = max(s.width() * dpr / crop.width(), s.height() * CAM_SHARE * dpr / crop.height())
                self.cam_image = crop.scaled(int(crop.width() * k) + 1, int(crop.height() * k) + 1,
                                             Qt.AspectRatioMode.IgnoreAspectRatio, SMOOTH) if k < .9 else crop

    def showEvent(self, event):
        self.cache_key = None
        super().showEvent(event)

    def set_clip(self, words, layout, facecam):
        self.words = words
        self.lines = group_words(words, self.style["words"])
        self.layout_name = layout
        self.facecam = facecam
        self.update()

    def set_style(self, pan, style):
        """Everything the export will do to the picture, so the preview never lies."""
        self.pan = pan
        if style["words"] != self.style["words"]:
            self.lines = group_words(self.words, style["words"])
        self.style = style
        self.update()

    def set_layout(self, layout):
        self.layout_name = layout
        self.update()

    def set_time(self, t):
        self.time = t
        if self.paused or self.incoming is None:
            self.update()           # while playing, the next frame repaints anyway

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
        self.take_frame()
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
        self.prepare(s)
        image = self.small
        layout = self.layout_name
        has_cam = not self.cam_image.isNull()
        if layout == "auto":
            layout = "stack" if has_cam else "blur"
        if layout == "stack" and has_cam:
            top = QRectF(s.x(), s.y(), s.width(), s.height() * CAM_SHARE)
            bottom = QRectF(s.x(), top.bottom(), s.width(), s.height() - top.height())
            self.fill(p, self.cam_image, top)
            self.fill(p, image, bottom)
        elif layout == "crop":
            self.fill(p, image, s, self.pan)
        else:
            self.fill(p, self.tiny, s)
            p.fillRect(s, QColor(0, 0, 0, 60))
            height = s.width() * image.height() / max(image.width(), 1)
            p.drawImage(QRectF(s.x(), s.center().y() - height / 2, s.width(), height), image)

    @staticmethod
    def fill(p, image, rect, pan=0.0):
        scale = max(rect.width() / image.width(), rect.height() / image.height())
        w, h = rect.width() / scale, rect.height() / scale
        p.drawImage(rect, image, QRectF((image.width() - w) * (pan + 1) / 2, (image.height() - h) / 2, w, h))

    def scaled_cam(self, image):
        if not self.facecam or not self.source_size:
            return None
        k = image.width() / max(self.source_size[0], 1)
        return tuple(int(v * k) for v in self.facecam)

    def draw_caption(self, p, s):
        """Draws the caption exactly as captions.build_ass styles it for the export."""
        st = self.style
        line = next((l for l in self.lines if l[0]["s"] <= self.time <= l[-1]["e"] + HOLD), None)
        if not line:
            return
        k = s.width() / 1080                    # export pixels to preview pixels
        texts = [shown(w["w"], st) for w in line]
        f = QFont()
        f.setFamilies([font_for(" ".join(texts), st), "Nirmala UI", "Segoe UI"])
        f.setPixelSize(max(int(st["size"] * k * 0.92), 6))
        f.setBold(bool(st["bold"]))
        f.setItalic(bool(st["italic"]))
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, st["spacing"] * k)
        metrics = QFontMetricsF(f)
        space = metrics.horizontalAdvance(" ")
        widths = [metrics.horizontalAdvance(t) for t in texts]
        total = sum(widths) + space * (len(texts) - 1)
        base_y = s.y() + s.height() * (1920 - st["y"]) / 1920 - metrics.descent()
        current = next((i for i in range(len(line) - 1, -1, -1) if line[i]["s"] <= self.time), 0)
        since_line = self.time - line[0]["s"]
        since_word = self.time - line[current]["s"]

        p.save()
        cx, cy = s.center().x(), base_y - metrics.ascent() / 2
        p.translate(cx, cy)
        p.rotate(-st["tilt"])                   # ASS turns counter-clockwise for positive angles
        scale, opacity, lift = 1.0, 1.0, 0.0
        if st["animation"] == "bounce":
            scale = 0.7 + 0.38 * min(since_line / .11, 1) if since_line < .11 else                 1.08 - 0.08 * min((since_line - .11) / .08, 1)
        elif st["animation"] == "fade" or (st["animation"] == "slide" and since_line < .16):
            opacity = min(since_line / (0.14 if st["animation"] == "fade" else 0.1), 1)
            lift = 0 if st["animation"] == "fade" else 26 * k * (1 - min(since_line / .16, 1))
        p.scale(scale, scale)
        p.translate(-cx, -cy + lift)
        p.setOpacity(opacity)

        x0 = cx - total / 2
        if st["box"]:
            pad = 14 * k
            box = QRectF(x0 - pad, base_y - metrics.ascent() - pad, total + 2 * pad, metrics.height() + 2 * pad)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha(QColor("#" + st["box_color"]), int(255 * st["box_opacity"] / 100)))
            p.drawRect(box)
        x = x0
        for i, text in enumerate(texts):
            path = QPainterPath()
            path.addText(0, 0, f, text)
            grow = 1.0
            if i == current and st["animation"] == "pop":
                grow = 1 + .24 * min(since_word / .07, 1) if since_word < .07 else 1.24 - .12 * min((since_word - .07) / .08, 1)
            p.save()
            p.translate(x + widths[i] / 2, base_y - metrics.ascent() / 3)
            p.scale(grow, grow)
            p.translate(-widths[i] / 2, metrics.ascent() / 3)
            spoken = i == current and st["highlight_mode"] in ("color", "box")
            if st["shadow"] and not st["box"]:
                p.save()
                p.translate(st["shadow"] * k, st["shadow"] * k)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(alpha(QColor("#" + st["shadow_color"]), 160))
                p.drawPath(path)
                p.restore()
            ring = st["outline_width"] if not st["box"] else 0
            ring_color = QColor("#" + st["outline"])
            if spoken and st["highlight_mode"] == "box":
                ring, ring_color = max(st["outline_width"], 6) + 10, QColor("#" + st["highlight"])
            if ring:
                p.setPen(QPen(ring_color, max(ring * 2 * k, 1.0), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                              Qt.PenJoinStyle.RoundJoin))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(path)
            p.setPen(Qt.PenStyle.NoPen)
            fill = QColor("#" + (st["highlight"] if spoken and st["highlight_mode"] == "color" else st["text"]))
            p.setBrush(fill)
            p.drawPath(path)
            if st["highlight_mode"] == "fill":      # karaoke: the colour sweeps across each word as it is said
                w = line[i]
                end = line[i + 1]["s"] if i + 1 < len(line) else line[-1]["e"]
                done = 1.0 if self.time >= end else max(0.0, (self.time - w["s"]) / max(end - w["s"], .01))
                if done > 0:
                    p.save()
                    p.setClipRect(QRectF(-4, -metrics.ascent() - 4, widths[i] * done + 4, metrics.height() + 8))
                    p.setBrush(QColor("#" + st["highlight"]))
                    p.drawPath(path)
                    p.restore()
            p.restore()
            x += widths[i] + space
        p.restore()