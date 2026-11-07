"""Premium in the app: the account section in Settings and the dialog that appears when the free plan runs out."""
import time
import webbrowser

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget)

from ..account import Account, run_in_thread
from ..plans import CAPS, PREMIUM_ONLY, Gate
from . import theme as T
from .fx import Button, Segmented

PLANS = (("12m", "Yearly", 4999, 59.99, 12), ("6m", "Every 6 months", 2999, 35.00, 6), ("3m", "Every 3 months", 1699, 20.00, 3))
REGIONS = [("India · ₹, UPI", "in"), ("Other countries · $", "world")]
INCLUDES = ("Streams up to 12 hours, with no weekly limit", "Unlimited exports and every caption style",
            "Fonts, animations and effects on every clip", "1440p, 60 fps and AI upscaling",
            "English captions, virality scores, titles and hashtags", "Compilations and exporting all kept clips at once")


def guess_region():
    return "in" if time.timezone == -19800 else "world"        # India Standard Time


class AccountHub(QObject):
    """One place for the account: runs server calls off the UI thread and tells the UI when anything changed."""
    changed = Signal()
    _done = Signal(object, object, object)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.account = Account(settings)
        self.gate = Gate(settings, self.account)
        self._done.connect(lambda callback, result, error: callback(result, error))

    def run(self, work, callback=lambda result, error: None):
        def finished(result, error):
            self._done.emit(callback, result, error)
        run_in_thread(work, finished)

    def refresh_quietly(self):
        """At start: learn whether billing is live and what plan this account has. Failing is fine offline."""
        def work():
            self.account.plans()
            return self.account.refresh() if self.account.signed_in() else None
        self.run(work, lambda result, error: self.changed.emit())

    def region(self):
        return self.settings.get("region") or guess_region()


class UpgradeDialog(QDialog):
    """Says what the free plan ran out of, and offers the three Premium plans."""

    def __init__(self, parent, hub, feature=None, reason_text=""):
        super().__init__(parent)
        self.hub = hub
        self.setWindowTitle("Clip Studio Premium")
        self.setMinimumWidth(560)
        title = QLabel("Get Premium")
        title.setObjectName("h1")
        why = QLabel(reason_text or (hub.gate.why_not(feature) if feature in CAPS or feature in PREMIUM_ONLY else
                                     "Premium removes every limit of the free plan."))
        why.setWordWrap(True)
        why.setObjectName("mute")
        includes = QLabel("\n".join("✓  " + line for line in INCLUDES))
        self.region = Segmented(REGIONS)
        self.region.set(hub.region())
        self.region.changed.connect(self.region_changed)
        self.cards = QGridLayout()
        self.cards.setSpacing(10)
        self.buttons = []
        for i, (cycle, name, inr, usd, months) in enumerate(PLANS):
            card = QVBoxLayout()
            label = QLabel(name + ("  ·  best value" if cycle == "12m" else ""))
            label.setObjectName("h2" if cycle == "12m" else "")
            price = QLabel()
            price.setObjectName("price")
            button = Button("Choose", "check", primary=cycle == "12m")
            button.clicked.connect(lambda _=False, c=cycle: self.buy(c))
            card.addWidget(label)
            card.addWidget(price)
            card.addWidget(button)
            box = QWidget()
            box.setLayout(card)
            self.cards.addWidget(box, 0, i)
            self.buttons.append((cycle, inr, usd, months, price, button))
        self.note = QLabel("Renews automatically. Cancel any time and Premium lasts to the end of the period. "
                           "One subscription works on 2 PCs.")
        self.note.setWordWrap(True)
        self.note.setObjectName("mute")
        self.status = QLabel("")
        self.status.setWordWrap(True)
        later = Button("Not now", flat=True)
        later.clicked.connect(self.reject)
        col = QVBoxLayout(self)
        col.setContentsMargins(24, 20, 24, 18)
        col.setSpacing(10)
        for w in (title, why, includes, self.region):
            col.addWidget(w)
        col.addLayout(self.cards)
        col.addWidget(self.note)
        col.addWidget(self.status)
        col.addWidget(later, 0, Qt.AlignmentFlag.AlignRight)
        self.region_changed(self.region.value())

    def region_changed(self, region):
        self.hub.settings.set("region", region)
        for cycle, inr, usd, months, price, button in self.buttons:
            if region == "in":
                price.setText("₹%s  (₹%d a month)" % (format(inr, ",d"), round(inr / months)))
            else:
                price.setText("$%.2f  ($%.2f a month)" % (usd, usd / months))

    def buy(self, cycle):
        region = self.region.value()
        account = self.hub.account

        def work():
            if not account.signed_in():
                account.sign_in()
            return account.buy_url(cycle, region)

        def done(url, error):
            if error:
                self.status.setText(error)
                return
            webbrowser.open(url)
            self.status.setText("The checkout opened in your browser. Premium turns on here a minute after paying; "
                                "press Refresh in Settings > Premium if it does not.")
        self.status.setText("Opening sign-in in your browser..." if not account.signed_in() else "Opening the checkout...")
        self.hub.run(work, done)


class PremiumSection(QWidget):
    """Settings > Premium: who is signed in, the plan, a licence key, and the PCs using Premium."""
    upgrade = Signal()

    def __init__(self, hub):
        super().__init__()
        self.hub = hub
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.sign_in = Button("Sign in with Google", "check", primary=True)
        self.sign_in.clicked.connect(self.do_sign_in)
        self.sign_out = Button("Sign out", flat=True)
        self.sign_out.clicked.connect(lambda: self.hub.run(self.hub.account.sign_out, lambda r, e: self.hub.changed.emit()))
        self.refresh = Button("Refresh", flat=True)
        self.refresh.clicked.connect(self.do_refresh)
        self.get = Button("Get Premium", "check")
        self.get.clicked.connect(self.upgrade.emit)
        self.key = QLineEdit(placeholderText="CS-XXXX-XXXX-XXXX-XXXX")
        self.activate = Button("Use a licence key")
        self.activate.clicked.connect(self.do_activate)
        self.devices = QVBoxLayout()
        self.devices.setSpacing(4)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setObjectName("mute")
        buttons = QHBoxLayout()
        for b in (self.sign_in, self.get, self.refresh, self.sign_out):
            buttons.addWidget(b)
        buttons.addStretch()
        keyrow = QHBoxLayout()
        keyrow.addWidget(self.key, 1)
        keyrow.addWidget(self.activate)
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(8)
        col.addWidget(self.status)
        col.addLayout(buttons)
        col.addLayout(keyrow)
        col.addLayout(self.devices)
        col.addWidget(self.message)
        hub.changed.connect(self.show_state)
        self.show_state()

    def show_state(self):
        account, gate = self.hub.account, self.hub.gate
        signed = account.signed_in()
        ready = bool(self.hub.settings.get("sign_in_ready")) or signed
        for w in (self.sign_in, self.sign_out, self.refresh, self.get, self.key, self.activate):
            w.setVisible(ready)
        if not ready:
            self.status.setText("Premium is coming soon. Until then every feature is free.")
            return
        cache = account.cache()
        if not signed:
            text = "Not signed in. Clip Studio is free to use; sign in to get Premium or use a licence key."
        elif account.plan() == "premium":
            until = time.strftime("%d %b %Y", time.localtime(cache.get("until", 0)))
            text = "%s · Premium · %s %s" % (account.email(), "renews" if cache.get("renews") else "ends", until)
        else:
            text = "%s · Free plan" % account.email()
            if cache.get("device_ok") is False:
                text += ". Premium is already on 2 other PCs: remove one below to use it here."
        if not gate.enforced():
            text += "\nAll features are open while Premium payments are being set up."
        self.status.setText(text)
        self.sign_in.setVisible(not signed)
        self.sign_out.setVisible(signed)
        self.refresh.setVisible(signed)
        self.get.setVisible(account.plan() != "premium")
        self.key.setEnabled(signed)
        self.activate.setEnabled(signed)
        while self.devices.count():
            item = self.devices.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        mine = account.device_id()
        for d in cache.get("devices") or []:
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            name = QLabel("🖥  %s%s" % (d.get("name") or "PC", "  (this PC)" if d.get("device_id") == mine else ""))
            line.addWidget(name, 1)
            if d.get("device_id") != mine:
                remove = Button("Remove", flat=True)
                remove.clicked.connect(lambda _=False, did=d["device_id"]: self.call(
                    lambda: self.hub.account.remove_device(did), "PC removed"))
                line.addWidget(remove)
            self.devices.addWidget(row)

    def call(self, work, success):
        def done(result, error):
            self.message.setText(error or success)
            self.hub.changed.emit()
        self.message.setText("Working...")
        self.hub.run(work, done)

    def do_sign_in(self):
        self.message.setText("Finish signing in in your browser...")
        self.call(self.hub.account.sign_in, "Signed in")

    def do_refresh(self):
        self.call(self.hub.account.refresh, "Up to date")

    def do_activate(self):
        key = self.key.text().strip()
        if key:
            self.call(lambda: self.hub.account.activate(key), "Licence key used. Premium is on.")
