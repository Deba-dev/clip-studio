"""Two views of time: the whole stream at a glance, and a close-up for trimming with handles that snap to words."""
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import theme as T
from .cards import clock
from .fx import alpha, font, panel

BAR = 3
GAP = 2


class StreamMap(QWidget):
    """One series, one hue: how much was happening across the stream, with each clip marked on top."""
    picked = Signal(float)

    def __init__(self):
        super().__init__()
        self.setFixedHeight(66)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.curve = np.zeros(1)
        self.duration = 1.0
        self.clips = []
        self.active = None
        self.play = 0.0
        self.mouse = None

    def load(self, curve, duration, clips):
        self.curve = curve if curve.size else np.zeros(1)
        self.duration = max(duration, 1.0)
        self.clips = clips
        self.update()

    def set_active(self, cid):
        self.active = cid
        self.update()

    def set_play(self, t):
        self.play = t
        self.update()

    def area(self):
        return QRectF(14, 22, self.width() - 28, self.height() - 30)

    def x_of(self, t):
        a = self.area()
        return a.x() + a.width() * t / self.duration

    def time_at(self, x):
        a = self.area()
        return max(0.0, min((x - a.x()) / max(a.width(), 1) * self.duration, self.duration))

    def bins(self):
        count = max(int(self.area().width() // (BAR + GAP)), 1)
        edges = np.linspace(0, self.curve.size, count + 1).astype(int)
        top = float(np.percentile(self.curve, 99.5)) or 1.0
        return [min(float(self.curve[a:max(b, a + 1)].max(initial=0)) / top, 1.0) for a, b in zip(edges, edges[1:])]

    def mouseMoveEvent(self, event):
        self.mouse = event.position().x()
        self.update()

    def leaveEvent(self, event):
        self.mouse = None
        self.update()

    def mousePressEvent(self, event):
        self.picked.emit(self.time_at(event.position().x()))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        panel(p, QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 12)
        p.setFont(font(11, QFont.Weight.DemiBold))
        p.setPen(T.MUTE)
        p.drawText(QRectF(14, 4, 300, 16), Qt.AlignmentFlag.AlignVCenter, "Activity across the stream")
        a = self.area()
        p.drawText(QRectF(a.right() - 120, 4, 120, 16), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                   clock(self.duration))
        for c in self.clips:
            x0, x1 = self.x_of(c["start"]), self.x_of(c["end"])
            active = c["id"] == self.active
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha(T.A2, 70 if active else 26))
            p.drawRoundedRect(QRectF(x0 - 1, a.y() - 1, max(x1 - x0, 4) + 2, a.height() + 2), 3, 3)
        p.setPen(Qt.PenStyle.NoPen)
        for i, v in enumerate(self.bins()):
            height = max(a.height() * v, 2)
            p.setBrush(alpha(T.A2, 95 + 160 * v))       # one hue: taller is also stronger
            p.drawRoundedRect(QRectF(a.x() + i * (BAR + GAP), a.bottom() - height, BAR, height), 1.5, 1.5)
        x = self.x_of(self.play)
        p.setPen(QPen(T.TEXT, 2))
        p.drawLine(QPointF(x, a.y() - 3), QPointF(x, a.bottom() + 2))
        if self.mouse is not None:
            t = self.time_at(self.mouse)
            mx = max(a.x(), min(self.mouse, a.right()))
            p.setPen(QPen(alpha(T.TEXT, 120), 1))
            p.drawLine(QPointF(mx, a.y()), QPointF(mx, a.bottom()))
            text = clock(t)
            width = p.fontMetrics().horizontalAdvance(text) + 14
            tip = QRectF(min(max(mx - width / 2, 2), self.width() - width - 2), 2, width, 18)
            p.setBrush(QColor(8, 5, 26, 235))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(tip, 6, 6)
            p.setPen(T.TEXT)
            p.drawText(tip, Qt.AlignmentFlag.AlignCenter, text)


class TrimBar(QWidget):
    """A close-up of one clip. Drag the handles to trim; they snap to the edges of spoken words."""
    trimmed = Signal(float, float)
    scrub = Signal(float)
    PAD = 14
    SNAP = 8

    def __init__(self):
        super().__init__()
        self.setFixedHeight(86)
        self.setMouseTracking(True)
        self.loud = np.zeros(1)
        self.start = self.end = 0.0
        self.lo, self.hi = 0.0, 1.0
        self.limit = 1.0
        self.words = []
        self.play = 0.0
        self.drag = None

    def load(self, loud, duration, clip):
        self.loud = loud if loud.size else np.zeros(1)
        self.limit = max(duration, 1.0)
        self.start, self.end = clip["start"], clip["end"]
        self.words = clip["words"]
        self.frame()

    def frame(self):
        span = max(self.end - self.start, 4)
        pad = max(span * .35, 8)
        self.lo = max(self.start - pad, 0.0)
        self.hi = min(self.end + pad, self.limit)
        self.update()

    def set_play(self, t):
        self.play = t
        self.update()

    def area(self):
        return QRectF(self.PAD, 24, self.width() - self.PAD * 2, self.height() - 34)

    def x_of(self, t):
        a = self.area()
        return a.x() + a.width() * (t - self.lo) / max(self.hi - self.lo, .1)

    def time_at(self, x):
        a = self.area()
        return self.lo + (x - a.x()) / max(a.width(), 1) * (self.hi - self.lo)

    def snap(self, t):
        best, gap = t, self.SNAP / max(self.area().width(), 1) * (self.hi - self.lo)
        for w in self.words:
            for edge in (w["s"], w["e"]):
                if abs(edge - t) < gap:
                    best, gap = edge, abs(edge - t)
        return best

    def mousePressEvent(self, event):
        x = event.position().x()
        near_start, near_end = abs(x - self.x_of(self.start)), abs(x - self.x_of(self.end))
        if min(near_start, near_end) < 14:
            self.drag = "start" if near_start <= near_end else "end"
        else:
            self.drag = "play"
            self.scrub.emit(self.time_at(x))

    def mouseMoveEvent(self, event):
        x = event.position().x()
        if self.drag == "play":
            self.scrub.emit(self.time_at(x))
        elif self.drag:
            t = self.snap(max(self.lo, min(self.time_at(x), self.hi)))
            if self.drag == "start":
                self.start = max(0.0, min(t, self.end - 1))
                self.scrub.emit(self.start)
            else:
                self.end = min(self.limit, max(t, self.start + 1))
                self.scrub.emit(max(self.end - 1.5, self.start))
            self.update()
        else:
            near = min(abs(x - self.x_of(self.start)), abs(x - self.x_of(self.end))) < 14
            self.setCursor(Qt.CursorShape.SizeHorCursor if near else Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event):
        if self.drag in ("start", "end"):
            self.trimmed.emit(self.start, self.end)
            self.frame()
        self.drag = None

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        panel(p, QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 12)
        a = self.area()
        p.setFont(font(11, QFont.Weight.DemiBold))
        p.setPen(T.MUTE)
        p.drawText(QRectF(14, 4, 340, 16), Qt.AlignmentFlag.AlignVCenter,
                   "Trim: drag the handles. They snap to words.")
        p.setPen(T.TEXT)
        p.drawText(QRectF(a.right() - 190, 4, 190, 16), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                   "%s to %s  ·  %.1fs" % (clock(self.start), clock(self.end), self.end - self.start))
        lo, hi = int(self.lo), int(np.ceil(self.hi))
        part = self.loud[lo:hi].astype(np.float32)
        if part.size:
            floor = float(np.percentile(self.loud[::max(self.loud.size // 2000, 1)], 10))
            top = max(float(part.max()), floor + 1)
            levels = np.clip((part - floor) / (top - floor), .04, 1)
            step = a.width() / max(self.hi - self.lo, .1)
            width = max(step - GAP, 1.5)
            p.setPen(Qt.PenStyle.NoPen)
            for i, v in enumerate(levels):
                t = lo + i
                inside = self.start <= t + .5 <= self.end
                h = a.height() * float(v)
                p.setBrush(alpha(T.A2, 225) if inside else alpha(T.MUTE, 60))
                p.drawRoundedRect(QRectF(self.x_of(t), a.center().y() - h / 2, width, h), 1.5, 1.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha(T.CAPTION, 170))
        for w in self.words:
            if self.lo <= w["s"] <= self.hi:
                p.drawEllipse(QPointF(self.x_of(w["s"]), a.bottom() + 4), 1.6, 1.6)
        x0, x1 = self.x_of(self.start), self.x_of(self.end)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(alpha(T.TEXT, 150), 1))
        p.drawRoundedRect(QRectF(x0, a.y() - 2, x1 - x0, a.height() + 4), 5, 5)
        for x, name in ((x0, "start"), (x1, "end")):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(T.CAPTION if self.drag == name else T.TEXT)
            p.drawRoundedRect(QRectF(x - 4, a.y() - 5, 8, a.height() + 10), 4, 4)
        if self.lo <= self.play <= self.hi:
            x = self.x_of(self.play)
            p.setPen(QPen(T.CAPTION, 2))
            p.drawLine(QPointF(x, a.y() - 5), QPointF(x, a.bottom() + 5))
