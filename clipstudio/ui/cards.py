"""Stream and clip cards. They paint their own hover, entrance and progress, with no widget effects to slow them."""
import os

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QBrush, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from . import theme as T
from .fx import MOTION, alpha, draw_icon, draw_ring, font, glow, mix, panel, tween

STATUS = {"new": ("Queued", "spark", T.MUTE), "recording": ("Recording", "cam", T.BAD),
          "fetching": ("Downloading", "down", T.A3), "analyzing": ("Analyzing", "wave", T.A2),
          "ready": ("Ready", "check", T.GOOD), "failed": ("Failed", "alert", T.BAD), "stopped": ("Stopped", "x", T.WARN)}
WORKING = ("fetching", "analyzing")


def clock(t):
    t = int(t)
    return "%d:%02d:%02d" % (t // 3600, t // 60 % 60, t % 60)


def cover(p, pixmap, rect):
    """Draws a picture filling rect, cropped rather than squashed."""
    if pixmap.isNull():
        return
    scale = max(rect.width() / pixmap.width(), rect.height() / pixmap.height())
    w, h = rect.width() / scale, rect.height() / scale
    p.drawPixmap(rect, pixmap, QRectF((pixmap.width() - w) / 2, (pixmap.height() - h) / 2, w, h))


def rounded(rect, radius):
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def pill(p, x, y, text, icon, color):
    """A status always shows an icon and a word, never colour alone."""
    p.setFont(font(11, QFont.Weight.DemiBold))
    width = p.fontMetrics().horizontalAdvance(text)
    r = QRectF(x, y, width + 30, 22)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(8, 5, 26, 215))
    p.drawRoundedRect(r, 11, 11)
    draw_icon(p, icon, QRectF(x + 7, y + 4, 14, 14), color, 2.2)
    p.setPen(T.TEXT)
    p.drawText(r.adjusted(24, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, text)
    return r


class Card(QWidget):
    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.hover = 0.0
        self.appear = 0.0
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def enter(self, order=0):
        tween(self, "appear", 1, 420, QEasingCurve.Type.OutCubic, delay=min(order, 12) * 45)

    def enterEvent(self, event):
        tween(self, "hover", 1, 170)

    def leaveEvent(self, event):
        tween(self, "hover", 0, 260)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()


class StreamCard(Card):
    menu = Signal(object)
    WIDTH, HEIGHT = 290, 222

    def __init__(self, row, thumb):
        super().__init__()
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.pixmap = QPixmap(thumb) if os.path.isfile(thumb) else QPixmap()
        self.shine = 0.0
        self.row = None
        self.update_row(row)
        self.shimmer = QTimer(self, interval=33, timeout=self.step)
        self.shimmer.start()

    def update_row(self, row):
        self.row = dict(row)
        self.update()

    def step(self):
        if self.row["status"] in WORKING and MOTION.on:
            self.shine = (self.shine + .016) % 1.3
            self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton or self.more_rect().contains(event.position()):
            self.menu.emit(event.globalPosition().toPoint())

    def mouseReleaseEvent(self, event):
        if not self.more_rect().contains(event.position()):
            super().mouseReleaseEvent(event)

    def more_rect(self):
        return QRectF(self.width() - 46, 14, 30, 30)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        p.setOpacity(self.appear)
        lift = 5 * self.hover + 24 * (1 - self.appear)
        r = QRectF(8, 9 - 5 * self.hover + 24 * (1 - self.appear), self.width() - 16, self.height() - 16)
        if self.hover > .01:
            glow(p, r, 14, T.A2, self.hover * 1.4, 8)
        panel(p, r, 14, T.PANEL, mix(T.LINE, alpha(T.A2, 200), self.hover))
        image = QRectF(r.x() + 1, r.y() + 1, r.width() - 2, 146)
        p.save()
        p.setClipPath(rounded(image, 13))
        if self.pixmap.isNull():
            g = QLinearGradient(image.topLeft(), image.bottomRight())
            g.setColorAt(0, QColor(50, 24, 120))
            g.setColorAt(1, QColor(90, 20, 110))
            p.fillRect(image, QBrush(g))
            draw_icon(p, "film", QRectF(image.center().x() - 20, image.center().y() - 20, 40, 40), alpha(T.TEXT, 120))
        else:
            zoom = 1 + .05 * self.hover
            cover(p, self.pixmap, QRectF(image.x() - image.width() * (zoom - 1) / 2, image.y() - image.height() * (zoom - 1) / 2,
                                         image.width() * zoom, image.height() * zoom))
        status = self.row["status"]
        if status in WORKING:
            x = image.x() + image.width() * (self.shine - .25)
            g = QLinearGradient(x, 0, x + image.width() * .3, 0)
            g.setColorAt(0, alpha(T.TEXT, 0))
            g.setColorAt(.5, alpha(T.TEXT, 56))
            g.setColorAt(1, alpha(T.TEXT, 0))
            p.fillRect(image, QBrush(g))
        p.restore()
        label, icon, color = STATUS.get(status, STATUS["new"])
        pill(p, r.x() + 10, r.y() + 10, label, icon, color)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(8, 5, 26, 215))
        more = self.more_rect().translated(0, r.y() - 9)
        p.drawEllipse(more)
        draw_icon(p, "more", more.adjusted(6, 6, -6, -6), T.TEXT, 2.2)

        p.setPen(T.TEXT)
        p.setFont(font(14, QFont.Weight.DemiBold))
        name = p.fontMetrics().elidedText(self.row["name"], Qt.TextElideMode.ElideRight, int(r.width() - 26))
        p.drawText(QRectF(r.x() + 13, r.y() + 153, r.width() - 26, 24), Qt.AlignmentFlag.AlignVCenter, name)
        p.setFont(font(12))
        p.setPen(T.BAD if self.row["error"] else T.MUTE)
        if self.row["error"]:
            meta = self.row["error"]
        else:
            count = self.row["clip_count"]
            meta = "%s  ·  %d clip%s" % (clock(self.row["duration"] or 0), count, "" if count == 1 else "s")
        meta = p.fontMetrics().elidedText(meta, Qt.TextElideMode.ElideRight, int(r.width() - 26))
        p.drawText(QRectF(r.x() + 13, r.y() + 177, r.width() - 26, 22), Qt.AlignmentFlag.AlignVCenter, meta)
        if self.row["error"]:
            self.setToolTip(self.row["error"])


class ClipCard(Card):
    HEIGHT = 96

    def __init__(self, clip, thumb, best):
        super().__init__()
        self.setFixedHeight(self.HEIGHT)
        self.pixmap = QPixmap(thumb) if os.path.isfile(thumb) else QPixmap()
        self.clip = clip
        self.best = max(best, 1e-6)
        self.selected = 0.0
        self.ring = 0.0
        self.flash = 0.0
        self.export = 0.0

    def enter(self, order=0):
        super().enter(order)
        tween(self, "ring", self.value(), 800, QEasingCurve.Type.OutCubic, delay=min(order, 12) * 45 + 120)

    def value(self):
        return 1.0 if self.clip["score"] >= 100 else min(self.clip["score"] / self.best, 1.0)

    def set_clip(self, clip):
        if clip["state"] != self.clip["state"]:
            self.flash = 1.0
            tween(self, "flash", 0, 520)
        self.clip = clip
        self.update()

    def select(self, on):
        tween(self, "selected", 1 if on else 0, 200)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        c = self.clip
        state = c["state"]
        p.setOpacity(self.appear * (.5 if state == "skipped" else 1))
        shift = 34 * (1 - self.appear)
        r = QRectF(3 + shift, 3, self.width() - 6, self.height() - 7)
        accent = {"kept": T.GOOD, "exported": T.A3, "skipped": T.FAINT}.get(state, T.A2)
        if self.selected > .01:
            glow(p, r, 12, accent, self.selected * 1.3, 6)
        panel(p, r, 12, mix(T.PANEL, T.PANEL_HI, max(self.selected, self.hover * .6)),
              mix(T.LINE, alpha(accent, 230), self.selected))
        if self.flash > .01:
            p.setBrush(alpha(accent, 110 * self.flash))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(r, 12, 12)

        image = QRectF(r.x() + 7, r.y() + 7, 116, r.height() - 14)
        p.save()
        p.setClipPath(rounded(image, 8))
        p.fillRect(image, QColor(30, 18, 70))
        cover(p, self.pixmap, image)
        p.restore()
        p.setFont(font(11, QFont.Weight.Bold))
        badge = QRectF(image.x() + 5, image.y() + 5, 24, 19)
        p.setBrush(QColor(8, 5, 26, 215))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(badge, 6, 6)
        p.setPen(T.TEXT)
        p.drawText(badge, Qt.AlignmentFlag.AlignCenter, str(c["rank"]))
        length = "%ds" % (c["end"] - c["start"])
        tw = p.fontMetrics().horizontalAdvance(length) + 12
        tag = QRectF(image.right() - tw - 5, image.bottom() - 24, tw, 19)
        p.setBrush(QColor(8, 5, 26, 215))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(tag, 6, 6)
        p.setPen(T.TEXT)
        p.drawText(tag, Qt.AlignmentFlag.AlignCenter, length)

        x = image.right() + 11
        width = r.right() - x - 54
        p.setFont(font(13, QFont.Weight.DemiBold))
        p.setPen(T.TEXT)
        title = c["title"] or "Moment at " + clock(c["peak"])
        p.drawText(QRectF(x, r.y() + 9, width, 40), Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignTop,
                   p.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight, int(width * 1.75)))
        p.setFont(font(11))
        p.setPen(T.MUTE)
        status = {"kept": "Kept", "skipped": "Skipped", "exported": "Exported"}.get(state, clock(c["start"]))
        icon = {"kept": "check", "skipped": "x", "exported": "export"}.get(state)
        y = r.bottom() - 26
        tx = x
        if icon:
            draw_icon(p, icon, QRectF(x, y + 3, 14, 14), accent, 2.2)
            tx += 18
        p.setPen(T.TEXT if icon else T.MUTE)
        p.drawText(QRectF(tx, y, width, 20), Qt.AlignmentFlag.AlignVCenter, status)

        ring = QRectF(r.right() - 46, r.center().y() - 19, 38, 38)
        marked = c["score"] >= 100
        draw_ring(p, ring, self.ring, T.CAPTION if marked else T.A2)
        if marked:
            draw_icon(p, "star", ring.adjusted(10, 10, -10, -10), T.CAPTION, 1.8, fill=True)
        else:
            p.setPen(T.TEXT)
            p.setFont(font(11, QFont.Weight.Bold))
            p.drawText(ring, Qt.AlignmentFlag.AlignCenter, str(int(self.ring * 100)))
        if self.export > 0:
            bar = QRectF(r.x() + 9, r.bottom() - 5, (r.width() - 18) * self.export, 3)
            p.setBrush(T.A3)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(bar, 1.5, 1.5)
