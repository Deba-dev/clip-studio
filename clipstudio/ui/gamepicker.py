"""A dropdown for every game and kind of stream Clip Studio knows, grouped (Shooters, Story and action, Old classics,
Not a game...) and searchable: type part of a name ("gta", "podcast") and pick it from the list."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QComboBox, QCompleter

from .. import games


class GamePicker(QComboBox):
    changed = Signal(str)

    def __init__(self, first_label, tip=""):
        super().__init__()
        model = QStandardItemModel(self)
        model.appendRow(self._item(first_label, ""))
        names = []
        bold = QFont()
        bold.setBold(True)
        for group, entries in games.grouped():
            head = QStandardItem("— " + group + " —")
            head.setFlags(Qt.ItemFlag.NoItemFlags)       # a heading, not a choice
            head.setFont(bold)
            model.appendRow(head)
            for key, name in entries:
                model.appendRow(self._item("    " + name, key))
                names.append(name)
        self.setModel(model)
        self.setMaxVisibleItems(18)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.lineEdit().setPlaceholderText("Type to search: GTA, Minecraft, podcast...")
        finder = QCompleter(names, self)
        finder.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        finder.setFilterMode(Qt.MatchFlag.MatchContains)
        finder.activated.connect(self._picked_name)
        self.setCompleter(finder)
        self.lineEdit().editingFinished.connect(self._typed)
        self.currentIndexChanged.connect(self._index_changed)
        self.activated.connect(lambda _: self._show_current())
        self.setToolTip(tip)
        self._last = ""
        self._show_current()

    @staticmethod
    def _item(text, key):
        item = QStandardItem(text)
        item.setData(key, Qt.ItemDataRole.UserRole)
        return item

    def value(self):
        return self.currentData() or ""

    def set(self, key):
        """Chooses a game by key, quietly; an unknown key falls back to the first choice."""
        self.blockSignals(True)
        self.setCurrentIndex(max(self.findData(key or ""), 0))
        self.blockSignals(False)
        self._last = self.value()
        self._show_current()

    def _show_current(self):
        self.lineEdit().setText(self.itemText(self.currentIndex()).strip())

    def _picked_name(self, name):
        key = games.key_of(name)
        self.setCurrentIndex(max(self.findData(key), 0))

    def _typed(self):
        """Typing a full name picks it; anything else goes back to what was chosen."""
        key = games.key_of(self.lineEdit().text())
        if key and key != self.value():
            self.setCurrentIndex(self.findData(key))
        self._show_current()

    def _index_changed(self, _):
        self._show_current()
        if self.value() != self._last:
            self._last = self.value()
            self.changed.emit(self._last)
