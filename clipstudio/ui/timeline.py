"""Two views of time: the whole stream at a glance, and a close-up for trimming with handles that snap to words."""
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .. import edit as clip_edit
from . import theme as T
from .cards import clock
from .fx import alpha, draw_icon, font, panel

BAR = 3
GAP = 2
PIN = 16            # clip pins above the activity map
PINS = {"kill": ("target", T.TAGS["kills"][2]), "clutch": ("star", T.TAGS["kills"][2]),
        "death": ("skull", T.TAGS["deaths"][2]), "laugh": ("laugh", T.TAGS["funny"][2])}


def lane_bins(lane, count):
    edges = np.linspace(0, lane.size, count + 1).astype(int)
    return [float(lane[a:max(b, a + 1)].max(initial=0)) for a, b in zip(edges, edges[1:])]


class StreamMap(QWidget):
    """One series, one hue: how much was happening across the stream, with each clip marked on top.

    Every clip has a pin in its tag's colour at its peak. Hover a pin to see what it is, click it to open the clip.
    """
    picked = Signal(float)
    chosen = Signal(int)            # a clip's id, from clicking its pin

    def __init__(self):
        super().__init__()
        self.setFixedHeight(104)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.laugh = np.zeros(0)
        self.events = []
        self.curve = np.zeros(1)
        self.duration = 1.0
        self.clips = []
        self.active = None
        self.play = 0.0
        self.mouse = None
        self.mouse_y = 0.0

    def load(self, curve, duration, clips, laugh=None, events=()):
        self.curve = curve if curve.size else np.zeros(1)
        self.laugh = laugh if laugh is not None else np.zeros(0)
        self.events = list(events)
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
        return QRectF(14, 46, self.width() - 28, self.height() - 66)

    def pin_at(self, x):
        """The clip whose pin is under x, preferring the stronger clip where pins overlap."""
        near = [c for c in self.clips if abs(self.x_of(c["peak"]) - x) <= PIN / 2 + 1]
        return max(near, key=lambda c: c["score"]) if near else None

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
        self.mouse_y = event.position().y()
        self.update()

    def leaveEvent(self, event):
        self.mouse = None
        self.update()

    def mousePressEvent(self, event):
        pos = event.position()
        pin = self.pin_at(pos.x()) if pos.y() < self.area().y() else None
        if pin:
            self.chosen.emit(pin["id"])
        else:
            self.picked.emit(self.time_at(pos.x()))

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
        self.paint_pins(p, a)
        self.paint_clip_pins(p, a)
        x = self.x_of(self.play)
        p.setPen(QPen(T.TEXT, 2))
        p.drawLine(QPointF(x, a.y() - 3), QPointF(x, a.bottom() + 2))
        if self.mouse is not None:
            t = self.time_at(self.mouse)
            mx = max(a.x(), min(self.mouse, a.right()))
            pin = self.pin_at(self.mouse) if self.mouse_y < a.y() else None
            p.setPen(QPen(alpha(T.TEXT, 120), 1))
            p.drawLine(QPointF(mx, a.y()), QPointF(mx, a.bottom()))
            text = clock(t)
            if pin:
                name = T.TAGS.get((pin["tags"] or ["hype"])[0], T.TAGS["hype"])[0]
                text = "%s  ·  %s  ·  %s" % (name, clock(pin["peak"]), pin["title"] or "Moment")
                text = p.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, 360)
            width = p.fontMetrics().horizontalAdvance(text) + 14
            tip = QRectF(min(max(mx - width / 2, 2), self.width() - width - 2), 2, width, 18)
            p.setBrush(QColor(8, 5, 26, 235))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(tip, 6, 6)
            p.setPen(T.TEXT)
            p.drawText(tip, Qt.AlignmentFlag.AlignCenter, text)


    def paint_clip_pins(self, p, a):
        """A row of pins above the activity: one per clip, coloured by what kind of moment it is."""
        y = a.y() - PIN - 6
        for c in sorted(self.clips, key=lambda c: (c["id"] == self.active, c["score"])):
            name, icon, color = T.TAGS.get((c["tags"] or ["hype"])[0], T.TAGS["hype"])
            x = self.x_of(c["peak"])
            active = c["id"] == self.active
            size = PIN + (4 if active else 0)
            dim = 255 if active or c["state"] != "skipped" else 90
            p.setPen(QPen(alpha(color, 70 if active else 40), 1))
            p.drawLine(QPointF(x, y + size), QPointF(x, a.y() - 1))
            p.setPen(QPen(alpha(T.TEXT, 230), 1.5) if active else Qt.PenStyle.NoPen)
            p.setBrush(alpha(color, dim if active else min(dim, 215)))
            box = QRectF(x - size / 2, y - (4 if active else 0), size, size)
            p.drawEllipse(box)
            draw_icon(p, icon, box.adjusted(3, 3, -3, -3), QColor(10, 6, 30), 2.4)

    def paint_pins(self, p, a):
        """A lane under the activity: kills, deaths and laughter, so the stream can be read at a glance."""
        y = a.bottom() + 5
        p.setPen(Qt.PenStyle.NoPen)
        for e in self.events:
            kind = {"enemy_down": "kill", "you_down": "death", "clutch": "clutch"}.get(e["kind"])
            if kind:
                p.setBrush(alpha(PINS[kind][1], 210))
                p.drawEllipse(QPointF(self.x_of(e["t"]), y + 3), 2.4, 2.4)
        if self.laugh.size:
            count = max(int(a.width() // 4), 1)
            color = PINS["laugh"][1]
            for i, v in enumerate(lane_bins(self.laugh, count)):
                if v >= .12:
                    p.setBrush(alpha(color, 120 + 135 * min(v * 2, 1)))
                    p.drawRoundedRect(QRectF(a.x() + i * a.width() / count, y + 7, 3, 4), 1, 1)
        p.setFont(font(10))
        x = a.right() - 250
        for label, color in (("Kills + deaths", T.TAGS["kills"][2]), ("Laughter", PINS["laugh"][1])):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawEllipse(QPointF(x, 12), 3, 3)
            p.setPen(T.MUTE)
            p.drawText(QRectF(x + 7, 4, 90, 16), Qt.AlignmentFlag.AlignVCenter, label)
            x += 100


class TrimBar(QWidget):
    """A close-up of one clip. Drag the handles to trim; they snap to the edges of spoken words.

    The mouse wheel zooms in on the pointer, for cuts that need to land between two words.
    """
    trimmed = Signal(float, float)
    scrub = Signal(float)
    PAD = 14
    SNAP = 8

    def __init__(self):
        super().__init__()
        self.setFixedHeight(104)
        self.setMouseTracking(True)
        self.clip_id = None
        self.cuts = []
        self.mutes = []
        self.pins = []
        self.mark_in = self.mark_out = None
        self.zoomed = False
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
        same = clip["id"] == self.clip_id
        self.start, self.end = clip["start"], clip["end"]
        self.words = clip["words"]
        e = clip_edit.settings(clip)
        self.cuts, self.mutes = clip_edit.merge(e["cuts"]), clip_edit.merge(e["mute"])
        self.pins = clip.get("events", [])
        if not same:
            self.clip_id = clip["id"]
            self.mark_in = self.mark_out = None
            self.zoomed = False
        if same and self.zoomed:
            self.update()
        else:
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

    def set_marks(self, mark_in, mark_out):
        self.mark_in, self.mark_out = mark_in, mark_out
        self.update()

    def marked(self):
        """The marked range in order, or None until both ends are set."""
        if self.mark_in is None or self.mark_out is None or self.mark_in == self.mark_out:
            return None
        return min(self.mark_in, self.mark_out), max(self.mark_in, self.mark_out)

    def wheelEvent(self, event):
        at = self.time_at(event.position().x())
        span = self.hi - self.lo
        scale = .8 if event.angleDelta().y() > 0 else 1.25
        new = max(min(span * scale, self.limit), 2.0)
        share = (at - self.lo) / max(span, .1)
        self.lo = max(at - new * share, 0.0)
        self.hi = min(self.lo + new, self.limit)
        self.zoomed = True
        self.update()

    def area(self):
        return QRectF(self.PAD, 24, self.width() - self.PAD * 2, self.height() - 44)

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
                   "Drag the handles to trim. Scroll to zoom.")
        p.setPen(T.TEXT)
        kept = self.end - self.start - sum(min(b, self.end) - max(a2, self.start) for a2, b in self.cuts
                                           if b > self.start and a2 < self.end)
        p.drawText(QRectF(a.right() - 240, 4, 240, 16), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                   "%s to %s  ·  %.1fs" % (clock(self.start), clock(self.end), kept))
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
                inside = self.start <= t + .5 <= self.end and not any(c0 <= t + .5 <= c1 for c0, c1 in self.cuts)
                h = a.height() * float(v)
                p.setBrush(alpha(T.A2, 225) if inside else alpha(T.MUTE, 60))
                p.drawRoundedRect(QRectF(self.x_of(t), a.center().y() - h / 2, width, h), 1.5, 1.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha(T.CAPTION, 170))
        for w in self.words:
            if self.lo <= w["s"] <= self.hi:
                p.drawEllipse(QPointF(self.x_of(w["s"]), a.bottom() + 4), 1.6, 1.6)
        self.paint_ranges(p, a)
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

    def paint_ranges(self, p, a):
        """Cuts are hatched out, muted parts show a band, marks show what the next cut would take."""
        for c0, c1 in self.cuts:
            r = QRectF(self.x_of(c0), a.y() - 2, self.x_of(c1) - self.x_of(c0), a.height() + 4)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(8, 5, 26, 170))
            p.drawRect(r)
            p.setBrush(QBrush(alpha(T.BAD, 170), Qt.BrushStyle.BDiagPattern))
            p.drawRect(r)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha(T.A3, 150))
        for m0, m1 in self.mutes:
            p.drawRoundedRect(QRectF(self.x_of(m0), a.bottom() + 8, self.x_of(m1) - self.x_of(m0), 4), 2, 2)
        marked = self.marked()
        if marked:
            p.setBrush(alpha(T.CAPTION, 46))
            p.drawRect(QRectF(self.x_of(marked[0]), a.y() - 2, self.x_of(marked[1]) - self.x_of(marked[0]), a.height() + 4))
        for t in (self.mark_in, self.mark_out):
            if t is not None and self.lo <= t <= self.hi:
                p.setPen(QPen(T.CAPTION, 1.5, Qt.PenStyle.DashLine))
                p.drawLine(QPointF(self.x_of(t), a.y() - 4), QPointF(self.x_of(t), a.bottom() + 4))
        for e in self.pins:
            if self.lo <= e["t"] <= self.hi and e["kind"] in PINS:
                icon, color = PINS[e["kind"]]
                x = self.x_of(e["t"])
                draw_icon(p, icon, QRectF(x - 6, a.bottom() + 7, 12, 12), color, 2)
