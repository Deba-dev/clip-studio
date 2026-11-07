"""Motion and custom controls. Everything is painted by hand, so nothing here needs image assets.

All motion goes through MOTION. It switches off while OBS is recording or streaming: a pretty app must never cost a
streamer a frame.
"""
import math
import random
import re

from PySide6.QtCore import (QEasingCurve, QObject, QPointF, QRect, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal)
from PySide6.QtGui import (QBrush, QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient)
from PySide6.QtWidgets import QCheckBox, QPushButton, QStackedWidget, QWidget

from . import theme as T


class Motion(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.reduced = False
        self.live = False

    @property
    def on(self):
        return not self.reduced and not self.live

    def set(self, reduced=None, live=None):
        if reduced is not None:
            self.reduced = reduced
        if live is not None:
            self.live = live
        self.changed.emit()


MOTION = Motion()


def tween(owner, name, end, ms=220, curve=QEasingCurve.Type.OutCubic, delay=0, on_step=None):
    """Animates a float attribute and repaints. A new tween on the same attribute smoothly takes over."""
    store = owner.__dict__.setdefault("_tweens", {})
    old = store.pop(name, None)
    if old is not None:
        old.stop()

    def step(value):
        setattr(owner, name, value)
        if on_step:
            on_step()
        owner.update()

    if not MOTION.on or ms <= 0:
        step(float(end))
        return
    anim = QVariantAnimation(owner)
    anim.setDuration(ms)
    anim.setStartValue(float(getattr(owner, name)))
    anim.setEndValue(float(end))
    anim.setEasingCurve(curve)
    anim.valueChanged.connect(step)
    store[name] = anim
    if delay:
        QTimer.singleShot(delay, anim, anim.start)
    else:
        anim.start()


def mix(a, b, t):
    return QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t), int(a.alpha() + (b.alpha() - a.alpha()) * t))


def alpha(color, value):
    c = QColor(color)
    c.setAlpha(int(max(0, min(value, 255))))
    return c


def font(size=13, weight=QFont.Weight.Normal):
    f = QFont("Segoe UI")
    f.setPixelSize(size)
    f.setWeight(weight)
    return f


def glow(p, rect, radius, color, strength=1.0, spread=10):
    """A soft halo from a few stacked outlines: far cheaper than a blur effect on every repaint."""
    p.setBrush(Qt.BrushStyle.NoBrush)
    for i in range(spread, 0, -2):
        p.setPen(QPen(alpha(color, 26 * strength * (1 - i / (spread + 2))), 2))
        p.drawRoundedRect(rect.adjusted(-i, -i, i, i), radius + i, radius + i)


# ---- icons: a tiny path language on a 24 x 24 grid (M move, L line, C curve, Z close, O circle)
ICONS = {
    "film": "M4 5 L20 5 L20 19 L4 19 Z M8 5 L8 19 M16 5 L16 19 M4 12 L20 12",
    "gear": "O 12 12 3 O 12 12 8 M12 2 L12 4 M12 20 L12 22 M2 12 L4 12 M20 12 L22 12 M5 5 L6.5 6.5 "
            "M17.5 17.5 L19 19 M19 5 L17.5 6.5 M6.5 17.5 L5 19",
    "plus": "M12 5 L12 19 M5 12 L19 12",
    "link": "M10 14 L14 10 M8 11 L6 13 C4 15 4 17 6 18.5 C8 20 10 19.5 11 18 L13 16 M16 13 L18 11 "
            "C20 9 20 7 18.5 5.5 C17 4 14.5 4 13 6 L11 8",
    "file": "M6 3 L14 3 L19 8 L19 21 L6 21 Z M14 3 L14 8 L19 8",
    "play": "M8 5 L19 12 L8 19 Z",
    "pause": "M8 5 L8 19 M16 5 L16 19",
    "undo": "M8 7 L4 11 L8 15 M4 11 L15 11 C19 11 20 14 20 15.5 C20 18 18 19 15 19 L10 19",
    "check": "M5 12.5 L10 17.5 L19 7",
    "x": "M6 6 L18 18 M18 6 L6 18",
    "export": "M12 15 L12 4 M7 9 L12 4 L17 9 M5 15 L5 20 L19 20 L19 15",
    "cam": "M3 7 L15 7 L15 17 L3 17 Z M15 11 L21 7.5 L21 16.5 L15 13",
    "back": "M14 6 L8 12 L14 18",
    "more": "O 6 12 1 O 12 12 1 O 18 12 1",
    "folder": "M3 6 L9 6 L11 8 L21 8 L21 19 L3 19 Z",
    "star": "M12 3 L14.6 9 L21 9.5 L16 13.6 L17.6 20 L12 16.6 L6.4 20 L8 13.6 L3 9.5 L9.4 9 Z",
    "chat": "M4 5 L20 5 L20 16 L11 16 L7 20 L7 16 L4 16 Z",
    "wave": "M7 9 L7 15 M10 5 L10 19 M13 8 L13 16 M16 10 L16 14 M19 7 L19 17 M4 11 L4 13",
    "caption": "M3 6 L21 6 L21 18 L3 18 Z M7 14 L11 14 M13 14 L17 14",
    "spark": "M12 3 L13.5 10.5 L21 12 L13.5 13.5 L12 21 L10.5 13.5 L3 12 L10.5 10.5 Z",
    "down": "M12 4 L12 15 M7 10 L12 15 L17 10 M5 20 L19 20",
    "phone": "M7 3 L17 3 L17 21 L7 21 Z M11 18 L13 18",
    "alert": "M12 4 L21 20 L3 20 Z M12 10 L12 15 M12 17 L12 17.5",
    "first": "M6 5 L6 19 M19 5 L9 12 L19 19 Z",
    "last": "M18 5 L18 19 M5 5 L15 12 L5 19 Z",
    "rewind": "M12 6 L4 12 L12 18 Z M21 6 L13 12 L21 18 Z",
    "forward": "M12 6 L20 12 L12 18 Z M3 6 L11 12 L3 18 Z",
    "stepback": "M16 6 L8 12 L16 18 M5 6 L5 18",
    "stepnext": "M8 6 L16 12 L8 18 M19 6 L19 18",
    "redo": "M16 7 L20 11 L16 15 M20 11 L9 11 C5 11 4 14 4 15.5 C4 18 6 19 9 19 L14 19",
    "cut": "O 6 6 2.6 O 6 18 2.6 M8 8 L20 19 M8 16 L20 5",
    "split": "M12 3 L12 21 M4 8 L9 12 L4 16 M20 8 L15 12 L20 16",
    "markin": "M9 4 L5 4 L5 20 L9 20 M12 12 L20 12 M16 8 L20 12 L16 16",
    "markout": "M15 4 L19 4 L19 20 L15 20 M12 12 L4 12 M8 8 L4 12 L8 16",
    "setstart": "M7 4 L7 20 M11 12 L20 12 M11 12 L15 8 M11 12 L15 16",
    "setend": "M17 4 L17 20 M13 12 L4 12 M13 12 L9 8 M13 12 L9 16",
    "loop": "M17 3 L21 7 L17 11 M21 7 L7 7 C5 7 3 9 3 11 M7 21 L3 17 L7 13 M3 17 L17 17 C19 17 21 15 21 13",
    "sound": "M4 9 L8 9 L13 5 L13 19 L8 15 L4 15 Z M16.5 9 C18 10.5 18 13.5 16.5 15 M19 6.5 C22 9.5 22 14.5 19 17.5",
    "mute": "M4 9 L8 9 L13 5 L13 19 L8 15 L4 15 Z M16 9.5 L21 14.5 M21 9.5 L16 14.5",
    "skull": "M12 3 C7 3 4 6.5 4 11 C4 14 5.5 15.5 7 16.5 L7 20 L17 20 L17 16.5 C18.5 15.5 20 14 20 11 C20 6.5 17 3 12 3 Z "
             "O 9 11 1.6 O 15 11 1.6 M10.5 20 L10.5 17.5 M13.5 20 L13.5 17.5",
    "laugh": "O 12 12 9 M7.5 13 C8.5 18 15.5 18 16.5 13 Z M8 9 L10 10 L8 11 M16 9 L14 10 L16 11",
    "target": "O 12 12 8 O 12 12 3 M12 2 L12 6 M12 18 L12 22 M2 12 L6 12 M18 12 L22 12",
    "bolt": "M13 3 L5 14 L11 14 L10 21 L19 10 L13 10 Z",
}
_cache = {}


def icon_path(name):
    if name in _cache:
        return _cache[name]
    path = QPainterPath()
    tokens = re.findall(r"[MLCZO]|-?\d+\.?\d*", ICONS[name])
    i = 0
    while i < len(tokens):
        op = tokens[i]
        i += 1
        if op == "Z":
            path.closeSubpath()
            continue
        count = {"M": 2, "L": 2, "C": 6, "O": 3}[op]
        n = [float(v) for v in tokens[i:i + count]]
        i += count
        if op == "M":
            path.moveTo(n[0], n[1])
        elif op == "L":
            path.lineTo(n[0], n[1])
        elif op == "C":
            path.cubicTo(*n)
        else:
            path.addEllipse(QPointF(n[0], n[1]), n[2], n[2])
    _cache[name] = path
    return path


def draw_icon(p, name, rect, color, width=1.9, fill=False):
    p.save()
    p.translate(rect.x(), rect.y())
    scale = rect.width() / 24
    p.scale(scale, scale)
    pen = QPen(color, width / scale * 1.0)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(color if fill else Qt.BrushStyle.NoBrush)
    p.drawPath(icon_path(name))
    p.restore()


def draw_ring(p, rect, value, color, track=None, width=4):
    p.setBrush(Qt.BrushStyle.NoBrush)
    pen = QPen(track or alpha(T.MUTE, 40), width)
    p.setPen(pen)
    p.drawEllipse(rect)
    pen.setColor(color)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawArc(rect, 90 * 16, int(-360 * 16 * max(0.0, min(value, 1.0))))


def panel(p, rect, radius=14, fill=None, line=None):
    p.setBrush(fill or T.PANEL)
    p.setPen(QPen(line or T.LINE, 1))
    p.drawRoundedRect(rect, radius, radius)


class Aurora(QWidget):
    """The living background. Drawn tiny and scaled up, so it costs almost nothing, and slow enough to stay calm."""

    def __init__(self):
        super().__init__()
        self.setObjectName("root")
        self.phase = random.random() * 10
        self.calm = False
        self.timer = QTimer(self, interval=66, timeout=self.tick)
        self.timer.start()
        MOTION.changed.connect(self.update)

    def tick(self):
        window = self.window()
        if MOTION.on and not self.calm and window.isVisible() and not window.isMinimized():
            self.phase += 0.012
            self.update()

    def paintEvent(self, event):
        w, h = max(self.width() // 8, 8), max(self.height() // 8, 8)
        image = QImage(w, h, QImage.Format.Format_RGB32)
        image.fill(T.BG)
        q = QPainter(image)
        q.setPen(Qt.PenStyle.NoPen)
        t = self.phase
        for color, speed, rx, ry, size, power in ((T.A1, 1.0, .25, .2, .75, 95), (T.A2, .7, .8, .85, .7, 62),
                                                  (T.A3, 1.3, .85, .15, .55, 48)):
            x = w * (rx + .14 * math.sin(t * speed))
            y = h * (ry + .16 * math.cos(t * speed * .8))
            g = QRadialGradient(QPointF(x, y), w * size)
            g.setColorAt(0, alpha(color, power))
            g.setColorAt(1, alpha(color, 0))
            q.setBrush(QBrush(g))
            q.drawRect(0, 0, w, h)
        q.end()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawImage(self.rect(), image)


class Pages(QStackedWidget):
    """Pages cross-slide. It animates a picture of each page, so live widgets underneath stay untouched."""

    def __init__(self):
        super().__init__()
        self.shade = None

    def go(self, widget):
        if widget is self.currentWidget():
            return
        if not MOTION.on or not self.isVisible():
            self.setCurrentWidget(widget)
            return
        root = self.window().centralWidget()
        area = QRect(self.mapTo(root, self.rect().topLeft()), self.size())
        before = root.grab(area)
        self.setCurrentWidget(widget)
        widget.layout() and widget.layout().activate()
        after = root.grab(area)
        if self.shade:
            self.shade.hide()
            self.shade.deleteLater()
        self.shade = Crossfade(self, before, after)


class Crossfade(QWidget):
    def __init__(self, parent, before, after):
        super().__init__(parent)
        self.before, self.after, self.t = before, after, 0.0
        self.setGeometry(parent.rect())
        self.show()
        self.raise_()
        tween(self, "t", 1.0, 300, QEasingCurve.Type.OutQuint, on_step=self.finish)

    def finish(self):
        if self.t >= 0.999:
            self.parent().shade = None
            self.hide()
            self.deleteLater()

    def paintEvent(self, event):
        p = QPainter(self)
        p.drawPixmap(int(-26 * self.t), 0, self.before)
        p.setOpacity(self.t)
        p.drawPixmap(int(46 * (1 - self.t)), 0, self.after)


class Button(QPushButton):
    def __init__(self, text="", icon=None, primary=False, danger=False, flat=False):
        super().__init__(text)
        self.icon_name, self.primary, self.danger, self.flat = icon, primary, danger, flat
        self.hover = 0.0
        self.press = 0.0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFont(font(13, QFont.Weight.DemiBold if primary else QFont.Weight.Medium))

    def sizeHint(self):
        text = self.fontMetrics().horizontalAdvance(self.text())
        return QSize(text + (28 if self.text() else 18) + (24 if self.icon_name else 0) + 8, 44)

    def minimumSizeHint(self):
        return self.sizeHint()

    def enterEvent(self, event):
        tween(self, "hover", 1, 160)

    def leaveEvent(self, event):
        tween(self, "hover", 0, 240)

    def mousePressEvent(self, event):
        tween(self, "press", 1, 70)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        tween(self, "press", 0, 220, QEasingCurve.Type.OutBack)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self.isEnabled()
        inset = 4 + self.press * 1.5
        r = QRectF(self.rect()).adjusted(inset, inset, -inset, -inset)
        accent = T.BAD if self.danger else T.A1
        if on and self.hover > 0.01 and not self.flat:
            glow(p, r, 9, T.A2 if self.primary else accent, self.hover * 1.5, 6)
        if self.primary and on:
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, mix(T.A1, T.A2, self.hover * .35))
            g.setColorAt(1, mix(T.A2, T.A1, 1 - self.hover * .7 - .3))
            p.setBrush(QBrush(g))
            p.setPen(Qt.PenStyle.NoPen)
        elif self.flat:
            p.setBrush(alpha(T.TEXT, 22 * self.hover))
            p.setPen(Qt.PenStyle.NoPen)
        else:
            p.setBrush(mix(QColor(26, 17, 64, 220), QColor(46, 30, 104, 240), self.hover) if on else QColor(22, 17, 48, 150))
            p.setPen(QPen(alpha(accent, (120 + 100 * self.hover) if on else 40), 1))
        p.drawRoundedRect(r, 9, 9)
        color = T.TEXT if on else T.FAINT
        text = self.text()
        width = self.fontMetrics().horizontalAdvance(text)
        size = 16
        total = width + (size + (7 if text else 0) if self.icon_name else 0)
        x = r.center().x() - total / 2
        if self.icon_name:
            draw_icon(p, self.icon_name, QRectF(x, r.center().y() - size / 2, size, size), color)
            x += size + 7
        p.setPen(color)
        p.setFont(self.font())
        p.drawText(QRectF(x, r.y(), width + 2, r.height()), Qt.AlignmentFlag.AlignVCenter, text)


class IconButton(Button):
    """A square tool button. It can stay lit, for switches like loop."""

    def __init__(self, icon, tip, checkable=False):
        super().__init__("", icon, flat=False)
        self.setToolTip(tip)
        self.setCheckable(checkable)
        self.setFixedSize(40, 40)

    def sizeHint(self):
        return QSize(40, 40)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.isChecked():
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setBrush(T.CAPTION)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(12, 32, 16, 2.5), 1.2, 1.2)


class Toggle(QCheckBox):
    """A sliding switch. Label sits on the right."""

    def __init__(self, text="", checked=False):
        super().__init__(text)
        self.setChecked(checked)
        self.knob = 1.0 if checked else 0.0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggled.connect(lambda on: tween(self, "knob", 1 if on else 0, 200, QEasingCurve.Type.OutBack))

    def sizeHint(self):
        return QSize(self.fontMetrics().horizontalAdvance(self.text()) + 58, 28)

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QRectF(1, 5, 38, 20)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(mix(QColor(50, 42, 90), T.A1, self.knob))
        p.drawRoundedRect(track, 10, 10)
        p.setBrush(T.TEXT)
        p.drawEllipse(QPointF(11 + 18 * self.knob, 15), 7.5, 7.5)
        p.setPen(T.TEXT)
        p.setFont(self.font())
        p.drawText(self.rect().adjusted(48, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, self.text())


class Segmented(QWidget):
    """A row of choices with a pill that slides to the chosen one."""
    changed = Signal(str)

    def __init__(self, options):
        super().__init__()
        self.options = options
        self.index = 0
        self.pill = 0.0
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(font(12, QFont.Weight.Medium))

    def set(self, value):
        for i, (_, v) in enumerate(self.options):
            if v == value and i != self.index:
                self.index = i
                tween(self, "pill", i, 240, QEasingCurve.Type.OutCubic)

    def value(self):
        return self.options[self.index][1]

    def mousePressEvent(self, event):
        i = int(event.position().x() / max(self.width() / len(self.options), 1))
        i = max(0, min(i, len(self.options) - 1))
        if i != self.index:
            self.index = i
            tween(self, "pill", i, 240, QEasingCurve.Type.OutCubic)
            self.changed.emit(self.options[i][1])

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        panel(p, r, 10, QColor(12, 8, 36, 220))
        w = r.width() / len(self.options)
        pill = QRectF(r.x() + w * self.pill + 3, r.y() + 3, w - 6, r.height() - 6)
        g = QLinearGradient(pill.topLeft(), pill.bottomRight())
        g.setColorAt(0, T.A1)
        g.setColorAt(1, T.A2)
        p.setBrush(QBrush(g))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(pill, 8, 8)
        p.setFont(self.font())
        for i, (label, _) in enumerate(self.options):
            p.setPen(T.TEXT if abs(self.pill - i) < .5 else T.MUTE)
            p.drawText(QRectF(r.x() + w * i, r.y(), w, r.height()), Qt.AlignmentFlag.AlignCenter, label)


class Toast(QWidget):
    """A message that slides in at the top right and leaves on its own."""

    def __init__(self, parent, text, kind="good", top=18):
        super().__init__(parent)
        self.text, self.kind, self.t, self.top = text, kind, 0.0, top
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFont(font(13, QFont.Weight.Medium))
        self.setFixedSize(min(self.fontMetrics().horizontalAdvance(text) + 76, 520), 52)
        self.place()
        self.show()
        self.raise_()
        tween(self, "t", 1, 340, QEasingCurve.Type.OutBack, on_step=self.place)
        QTimer.singleShot(3600, self, self.leave)

    def place(self):
        self.move(int(self.parent().width() - (self.width() + 18) * min(self.t, 1.05) - 4 + 0), self.top)

    def leave(self):
        tween(self, "t", 0, 240, QEasingCurve.Type.InCubic, on_step=self.gone)

    def gone(self):
        self.place()
        if self.t <= 0.01:
            self.deleteLater()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = {"good": T.GOOD, "bad": T.BAD, "info": T.A2}[self.kind]
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        panel(p, r, 13, QColor(24, 16, 58, 248), alpha(color, 170))
        draw_icon(p, {"good": "check", "bad": "alert", "info": "spark"}[self.kind], QRectF(16, 16, 20, 20), color)
        p.setPen(T.TEXT)
        p.setFont(self.font())
        p.drawText(r.adjusted(46, 0, -12, 0), Qt.AlignmentFlag.AlignVCenter,
                   self.fontMetrics().elidedText(self.text, Qt.TextElideMode.ElideRight, self.width() - 62))


class Confetti(QWidget):
    """A short burst when a clip finishes. Clicks pass straight through it."""
    COLORS = (T.A1, T.A2, T.A3, T.GOOD, T.CAPTION)

    def __init__(self, parent, origin):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setGeometry(parent.rect())
        self.parts = []
        for _ in range(70):
            angle = random.uniform(-math.pi, 0)
            speed = random.uniform(3, 11)
            self.parts.append([origin.x(), origin.y(), math.cos(angle) * speed, math.sin(angle) * speed,
                               random.choice(self.COLORS), random.uniform(0, 6.28), random.uniform(4, 8)])
        self.age = 0
        self.timer = QTimer(self, interval=16, timeout=self.step)
        self.timer.start()
        self.show()
        self.raise_()

    def step(self):
        self.age += 1
        for q in self.parts:
            q[0] += q[2]
            q[1] += q[3]
            q[3] += .22
            q[2] *= .985
            q[5] += .22
        if self.age > 95:
            self.timer.stop()
            self.deleteLater()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        fade = min(1.0, (95 - self.age) / 30)
        for x, y, _, _, color, spin, size in self.parts:
            p.save()
            p.translate(x, y)
            p.rotate(math.degrees(spin))
            p.setBrush(alpha(color, 255 * fade))
            p.drawRect(QRectF(-size / 2, -size / 4, size, size / 2 + abs(math.sin(spin)) * size / 2))
            p.restore()
