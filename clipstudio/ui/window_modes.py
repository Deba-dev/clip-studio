"""Window modes shared by every ZunimiLabs app: Windowed, Borderless or Fullscreen, F11, and Esc or close to the tray.

The same file lives in each app, so keep the copies identical. It reads and writes these settings keys:
window_mode ("windowed", "borderless", "fullscreen"), window_geometry, close_to_tray, esc_to_tray, esc_ask,
tray_hint_shown.

- Windowed: a normal window with Windows' title bar. Its size and place are remembered.
- Borderless: no title bar or border, filling the screen above the taskbar.
- Fullscreen: covers the whole screen, taskbar included. F11 switches it on and off at any time.
Borderless and fullscreen have no title bar, so minimize, back-to-window and close slide in at the top right when the
mouse touches the top edge of the screen.
"""
import base64

from PySide6.QtCore import QByteArray, QEvent, QObject, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QPainter, QPen
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QCheckBox, QKeySequenceEdit, QLineEdit, QMenu, QMessageBox,
                               QPlainTextEdit, QSystemTrayIcon, QTextEdit, QWidget)

MODES = (("Windowed", "windowed"), ("Borderless", "borderless"), ("Fullscreen", "fullscreen"))
VALID = {value for _, value in MODES}
TYPING = (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox, QKeySequenceEdit)   # Esc here only leaves the box
HINT = "%s is still running here in the tray. Click this icon to open it, or change this in Settings."


class CornerControls(QWidget):
    """Minimize, back to a normal window, and close, for windows without a title bar."""
    BUTTONS = (("min", "Minimize"), ("window", "Back to a normal window"), ("close", "Close"))
    SIZE = 46

    def __init__(self, modes):
        super().__init__(modes.window)
        self.modes = modes
        self.hot = -1
        self.setFixedSize(self.SIZE * len(self.BUTTONS), 32)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hide()

    def place(self):
        parent = self.parentWidget()
        self.move(parent.width() - self.width() - 8, 6)
        self.raise_()

    def index_at(self, x):
        i = int(x // self.SIZE)
        return i if 0 <= i < len(self.BUTTONS) else -1

    def mouseMoveEvent(self, event):
        i = self.index_at(event.position().x())
        if i != self.hot:
            self.hot = i
            self.setToolTip(self.BUTTONS[i][1] if i >= 0 else "")
            self.update()

    def leaveEvent(self, event):
        self.hot = -1
        self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        i = self.index_at(event.position().x())
        if i < 0:
            return
        self.hide()
        name = self.BUTTONS[i][0]
        if name == "min":
            self.modes.window.showMinimized()
        elif name == "window":
            self.modes.set_mode("windowed")
        else:
            self.modes.window.close()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(12, 14, 20, 225))
        p.drawRoundedRect(self.rect(), 10, 10)
        for i, (name, _) in enumerate(self.BUTTONS):
            r = QRect(i * self.SIZE, 0, self.SIZE, self.height())
            if i == self.hot:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(232, 17, 35) if name == "close" else QColor(255, 255, 255, 40))
                p.drawRoundedRect(r.adjusted(3, 3, -3, -3), 8, 8)
            p.setPen(QPen(QColor(236, 239, 246), 1.4))
            p.setBrush(Qt.BrushStyle.NoBrush)
            c = r.center()
            if name == "min":
                p.drawLine(c.x() - 5, c.y(), c.x() + 5, c.y())
            elif name == "window":
                p.drawRect(c.x() - 5, c.y() - 4, 10, 8)
            else:
                p.drawLine(c.x() - 5, c.y() - 5, c.x() + 5, c.y() + 5)
                p.drawLine(c.x() - 5, c.y() + 5, c.x() + 5, c.y() - 5)


class WindowModes(QObject):
    """Gives a top-level window the three window modes, F11, Esc to the tray and a remembered size.

    busy() returns a sentence when quitting now would stop something, else "".
    tray: a function telling whether the app's own tray icon is showing. Leave it out and this keeps the icon itself,
    with Open, the extra (text, callback) actions, and Quit in its menu.
    The window calls show() instead of show(), handle_key(event) first in keyPressEvent, and close_event(event) first
    in closeEvent.
    """
    mode_changed = Signal(str)

    def __init__(self, window, settings, name, busy=None, tray=None, actions=()):
        super().__init__(window)
        self.window, self.s, self.name = window, settings, name
        self.busy = busy or (lambda: "")
        self.actions = actions
        self.app_tray = tray
        self.icon = None
        self.quitting = False
        self.current = None             # the mode on screen now; None until the window is first shown
        self.before_full = "windowed"   # where F11 and Esc go back to
        self.controls = CornerControls(self)
        self.watch = QTimer(self, interval=200, timeout=self.hover)
        self.away = 0
        window.installEventFilter(self)
        if tray is None:
            self.sync_tray()

    # ---- modes
    @property
    def mode(self):
        mode = self.s.get("window_mode")
        return mode if mode in VALID else "windowed"

    def show(self):
        """Shows the window for the first time, in the saved mode and at the saved size."""
        self.restore()
        self.apply(self.mode)

    def show_again(self):
        if self.current is None:
            self.show()
        elif self.window.isMinimized():
            self.window.showNormal() if self.current == "windowed" else self.apply(self.current)
        else:
            self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def set_mode(self, mode):
        """Saves a mode and switches to it."""
        mode = mode if mode in VALID else "windowed"
        self.s.set("window_mode", mode)
        self.apply(mode)

    def toggle_fullscreen(self):
        """F11: in and out of fullscreen for now, without changing the saved mode."""
        if self.current == "fullscreen":
            self.apply(self.before_full if self.before_full != "fullscreen" else "windowed")
        else:
            self.before_full = self.current or "windowed"
            self.apply("fullscreen")

    def apply(self, mode):
        w = self.window
        if self.current == "windowed" and mode != "windowed":
            self.remember()
        frameless = mode != "windowed"
        if bool(w.windowFlags() & Qt.WindowType.FramelessWindowHint) != frameless:
            w.setWindowFlag(Qt.WindowType.FramelessWindowHint, frameless)     # this hides the window; shown below
        if mode == "fullscreen":
            w.showFullScreen()
        elif mode == "borderless":
            if w.isFullScreen() or w.isMaximized():
                w.showNormal()
            screen = w.screen() or QApplication.primaryScreen()
            w.setGeometry(screen.availableGeometry())
            w.show()
        else:
            if self.current in ("borderless", "fullscreen"):
                w.showNormal()
                self.restore()
            w.show()
        if mode == "fullscreen" and self.current != "fullscreen" and self.current is not None:
            self.before_full = self.current
        self.current = mode
        if frameless:
            self.watch.start()
        else:
            self.watch.stop()
            self.controls.hide()
        self.mode_changed.emit(mode)

    def remember(self):
        if self.current == "windowed" and self.window.isVisible() and not self.window.isMinimized():
            data = bytes(self.window.saveGeometry())
            self.s.set("window_geometry", base64.b64encode(data).decode("ascii"))

    def restore(self):
        raw = self.s.get("window_geometry")
        if raw:
            try:
                self.window.restoreGeometry(QByteArray(base64.b64decode(raw)))
            except (ValueError, TypeError):
                pass

    # ---- the corner buttons
    def hover(self):
        w = self.window
        if not w.isVisible() or w.isMinimized() or not w.isActiveWindow():
            self.controls.hide()
            return
        pos = w.mapFromGlobal(QCursor.pos())
        near = 0 <= pos.x() <= w.width() and 0 <= pos.y() <= 4
        over = self.controls.isVisible() and self.controls.geometry().adjusted(-24, -8, 8, 24).contains(pos)
        if near or over:
            self.away = 0
            if not self.controls.isVisible():
                self.controls.place()
                self.controls.show()
        elif self.controls.isVisible():
            self.away += 1
            if self.away >= 4:          # about a second after the mouse leaves
                self.controls.hide()

    def eventFilter(self, obj, event):
        if obj is self.window and event.type() == QEvent.Type.Resize and self.controls.isVisible():
            self.controls.place()
        return False

    # ---- keys
    def handle_key(self, event):
        """F11 toggles fullscreen. Esc leaves a text box, then fullscreen, then hides to the tray. True means used."""
        key, mods = event.key(), event.modifiers()
        if key == Qt.Key.Key_F11 and mods == Qt.KeyboardModifier.NoModifier:
            self.toggle_fullscreen()
            return True
        if key != Qt.Key.Key_Escape or mods != Qt.KeyboardModifier.NoModifier:
            return False
        if QApplication.activePopupWidget() is not None or QApplication.activeModalWidget() is not None:
            return False
        focus = QApplication.focusWidget()
        if isinstance(focus, TYPING) and self.window.isAncestorOf(focus):
            focus.clearFocus()
            return True
        if self.current == "fullscreen":
            self.toggle_fullscreen()
            return True
        return bool(self.s.get("esc_to_tray")) and self.esc_hide()

    def esc_hide(self):
        """Esc hides to the tray, but first asks (Cancel is the default, so a second Esc does nothing) unless the
        person ticked "don't ask again"."""
        if not self.tray_ready():
            return False
        if self.s.get("esc_ask") is not False:
            box = QMessageBox(self.window)
            box.setWindowTitle(self.name)
            box.setText("Hide %s to the tray?" % self.name)
            box.setInformativeText("It keeps running. Click the tray icon to open it again.")
            hide = box.addButton("Hide to tray", QMessageBox.ButtonRole.AcceptRole)
            quit_button = box.addButton("Quit", QMessageBox.ButtonRole.DestructiveRole)
            cancel = box.addButton(QMessageBox.StandardButton.Cancel)
            box.setDefaultButton(cancel)
            box.setEscapeButton(cancel)
            never = QCheckBox("Don't ask again when I press Esc")
            box.setCheckBox(never)
            box.exec()
            clicked = box.clickedButton()
            if never.isChecked() and clicked is not cancel:
                self.s.set("esc_ask", False)
            if clicked is quit_button:
                self.quit()
                return True
            if clicked is not hide:
                return True
        return self.hide_to_tray()

    # ---- tray
    def tray_ready(self):
        if self.app_tray is not None:
            return bool(self.app_tray())
        return self.icon is not None and self.icon.isVisible()

    def sync_tray(self):
        """The icon shows while closing or Esc goes to the tray, so the app can always be found again."""
        if self.app_tray is not None:
            return
        wanted = bool(self.s.get("close_to_tray") or self.s.get("esc_to_tray")) and \
            QSystemTrayIcon.isSystemTrayAvailable()
        if wanted and self.icon is None:
            self.icon = QSystemTrayIcon(self.window.windowIcon() or QApplication.windowIcon(), self)
            self.icon.setToolTip(self.name)
            menu = QMenu(self.window)
            menu.addAction("Open %s" % self.name, self.show_again)
            for text, callback in self.actions:
                menu.addAction(text, callback)
            menu.addSeparator()
            menu.addAction("Quit %s" % self.name, self.quit)
            self.icon.setContextMenu(menu)
            self.icon.activated.connect(
                lambda why: self.show_again() if why == QSystemTrayIcon.ActivationReason.Trigger else None)
        if self.icon is not None:
            self.icon.setVisible(wanted)

    def hide_to_tray(self):
        if not self.tray_ready():
            return False
        self.remember()
        self.controls.hide()
        self.window.hide()
        if not self.s.get("tray_hint_shown"):
            icon = self.icon or getattr(self.window, "tray", None)
            if hasattr(icon, "showMessage"):
                icon.showMessage(self.name, HINT % self.name, QSystemTrayIcon.MessageIcon.Information, 6000)
            self.s.set("tray_hint_shown", True)
        return True

    # ---- closing
    def close_event(self, event):
        """Call first in closeEvent. True means the window only went to the tray or the person changed their mind."""
        if not self.quitting and self.s.get("close_to_tray") and self.hide_to_tray():
            event.ignore()
            return True
        if not self.quitting and not self.confirm():
            event.ignore()
            return True
        self.remember()
        self.quitting = True
        if self.icon is not None:
            self.icon.hide()
        return False

    def confirm(self):
        why = self.busy()
        if not why:
            return True
        self.show_again()
        answer = QMessageBox.question(self.window, self.name, why + "\n\nQuit %s anyway?" % self.name)
        return answer == QMessageBox.StandardButton.Yes

    def quit(self):
        """Quits for real, asking first when something would stop."""
        if not self.confirm():
            return
        self.quitting = True
        self.window.close()
        QApplication.quit()
