#!/usr/bin/env python3
"""Minimal BibTeX literature list. pip install PySide6 "bibtexparser<2" """
import json
import sys
from pathlib import Path

import bibtexparser
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QFormLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QSplitter, QVBoxLayout, QWidget,
)

DB_PATH = Path.home() / "litlist" / "library.json"
DB_PATH.parent.mkdir(exist_ok=True)
USER_DEFAULTS = {"include": False, "notes": ""}  # add your own fields here
SKIP = {"ID", "ENTRYTYPE"}


def label(bib):
    first_author = bib.get("author", "?").split(" and ")[0]
    return f"{bib.get('title', '(no title)')} — {first_author} ({bib.get('year', 'n.d.')})"


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Literature")
        self.resize(1100, 650)
        self.db = self.load()
        self.key = None
        self.loading = False

        # left: import button + list
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self.show_entry)
        self.list.itemChanged.connect(self.on_item_checked)
        btn = QPushButton("Import BibTeX…")
        btn.clicked.connect(self.import_bib)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.addWidget(btn)
        lv.addWidget(self.list)
        btn_clip = QPushButton("Import from clipboard")
        btn_clip.clicked.connect(self.import_clipboard)
        lv.addWidget(btn_clip)

        # right: detail view
        self.form_host = QWidget()
        self.form = QFormLayout(self.form_host)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.form_host)
        self.include = QCheckBox("Include")
        self.include.toggled.connect(self.on_include_toggled)
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("Notes")
        self.notes.textChanged.connect(self.on_notes_changed)
        self.right = QWidget()
        rv = QVBoxLayout(self.right)
        rv.addWidget(scroll, 2)
        rv.addWidget(self.include)
        rv.addWidget(QLabel("Notes"))
        rv.addWidget(self.notes, 1)
        self.right.setEnabled(False)

        split = QSplitter()
        split.addWidget(left)
        split.addWidget(self.right)
        split.setSizes([450, 650])
        self.setCentralWidget(split)
        self.populate()

    # ---- persistence ----
    @staticmethod
    def load():
        db = json.loads(DB_PATH.read_text("utf-8")) if DB_PATH.exists() else {}
        for e in db.values():
            for k, v in USER_DEFAULTS.items():
                e["user"].setdefault(k, v)
        return db

    def save(self):
        DB_PATH.write_text(json.dumps(self.db, indent=2, ensure_ascii=False), "utf-8")

    # ---- list ----
    def populate(self):
        self.list.blockSignals(True)
        self.list.clear()
        for key, e in sorted(self.db.items()):
            item = QListWidgetItem(label(e["bib"]))
            item.setData(Qt.UserRole, key)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if e["user"]["include"] else Qt.Unchecked)
            self.list.addItem(item)
        self.list.blockSignals(False)

    def import_bib(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open BibTeX", "", "BibTeX (*.bib);;All files (*)")
        if not path:
            return
        with open(path, encoding="utf-8") as fh:
            self.import_bib_text(fh.read())
        
    def import_clipboard(self):
        self.import_bib_text(QApplication.clipboard().text())

    def import_bib_text(self, text):
        entries = bibtexparser.loads(text).entries
        if not entries:
            QMessageBox.warning(self, "Import", "No BibTeX entries found.")
            return
        for entry in entries:
            key = entry["ID"]
            if key in self.db:
                self.db[key]["bib"].update(entry)  # keep user fields
            else:
                self.db[key] = {"bib": entry, "user": dict(USER_DEFAULTS)}
        self.save()
        self.populate()
        self.show_entry(None)
        

    # ---- detail view ----
    def show_entry(self, item, _prev=None):
        self.loading = True
        while self.form.rowCount():
            self.form.removeRow(0)
        self.key = item.data(Qt.UserRole) if item else None
        self.right.setEnabled(item is not None)
        if item:
            e = self.db[self.key]
            self.form.addRow("ID", QLabel(self.key))
            self.form.addRow("Type", QLabel(e["bib"].get("ENTRYTYPE", "")))
            for field, value in e["bib"].items():
                if field in SKIP:
                    continue
                edit = QLineEdit(value)
                edit.setCursorPosition(0)
                edit.textEdited.connect(lambda t, f=field: self.on_field_edited(f, t))
                self.form.addRow(field, edit)
            self.include.setChecked(e["user"]["include"])
            self.notes.setPlainText(e["user"]["notes"])
        else:
            self.include.setChecked(False)
            self.notes.clear()
        self.loading = False

    # ---- edit handlers ----
    def on_field_edited(self, field, text):
        self.db[self.key]["bib"][field] = text
        self.save()
        if field in ("title", "author", "year"):
            self.list.blockSignals(True)
            self.list.currentItem().setText(label(self.db[self.key]["bib"]))
            self.list.blockSignals(False)

    def on_include_toggled(self, checked):
        if self.loading or not self.key:
            return
        self.db[self.key]["user"]["include"] = checked
        self.save()
        self.list.blockSignals(True)
        self.list.currentItem().setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.list.blockSignals(False)

    def on_item_checked(self, item):
        key = item.data(Qt.UserRole)
        checked = item.checkState() == Qt.Checked
        self.db[key]["user"]["include"] = checked
        self.save()
        if key == self.key:
            self.loading = True
            self.include.setChecked(checked)
            self.loading = False

    def on_notes_changed(self):
        if self.loading or not self.key:
            return
        self.db[self.key]["user"]["notes"] = self.notes.toPlainText()
        self.save()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = Main()
    win.show()
    sys.exit(app.exec())
