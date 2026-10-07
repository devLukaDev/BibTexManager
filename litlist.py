#!/usr/bin/env python3
"""Minimal BibTeX literature list. pip install PySide6 "bibtexparser<2" """
import json
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction
import bibtexparser
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QSplitter, QVBoxLayout, QWidget,
)
import shutil
from PySide6.QtCore import QSettings, Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtCore import QSize
from PySide6.QtGui import QPixmap
from PySide6.QtPdf import QPdfDocument
from PySide6.QtGui import QImage, QPainter

DEFAULT_DB_PATH = Path.home() / "litlist" / "library.json"
DB_PATH = Path.home() / "litlist" / "library.json"
DB_PATH.parent.mkdir(exist_ok=True)
USER_DEFAULTS = {"include": False, "notes": "", "pdf": ""}  # add your own fields here
SKIP = {"ID", "ENTRYTYPE"}
PDF_W, PDF_H = 360, 525


def label(bib):
    first_author = bib.get("author", "?").split(" and ")[0]
    return f"{bib.get('title', '(no title)')} — {first_author} ({bib.get('year', 'n.d.')})"


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("litlist", "litlist")
        db_path = self.settings.value("db_path", str(DEFAULT_DB_PATH))
        self.db_path = Path(
            str(db_path)) if db_path is not None else DEFAULT_DB_PATH
        self.db = self.load()
        self.update_title()
        self.resize(1600, 900)
        self.db = self.load()
        self.key = None
        self.loading = False
        self.pdf_doc = QPdfDocument(self)

        # left: import button + list
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self.show_entry)
        self.list.itemChanged.connect(self.on_item_checked)
        btn = QPushButton("Import BibTeX…")
        btn.clicked.connect(self.import_bib)
        btn_clip = QPushButton("Import from clipboard")
        btn_clip.clicked.connect(self.import_clipboard)
        left = QWidget()
        lv = QVBoxLayout(left)
        row = QHBoxLayout()
        row.addWidget(btn)
        row.addWidget(btn_clip)
        lv.addLayout(row)
        lv.addWidget(self.list)

        # right, top: bibtex fields | PDF preview + attach button
        self.form_host = QWidget()
        self.form = QFormLayout(self.form_host)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.form_host)

        self.pdf_label = QLabel("(no PDF)")
        # same size with or without a PDF
        self.pdf_label.setFixedSize(PDF_W, PDF_H)
        self.pdf_label.setAlignment(Qt.AlignCenter)
        self.pdf_label.setStyleSheet("background: white; color: black;")
        self.pdf_label.mouseDoubleClickEvent = lambda e: self.open_pdf()
        btn_pdf = QPushButton("Attach PDF…")
        btn_pdf.clicked.connect(self.attach_pdf)
        pdf_box = QVBoxLayout()
        pdf_box.addWidget(self.pdf_label)
        pdf_box.addWidget(btn_pdf)
        pdf_box.addStretch(1)

        top = QHBoxLayout()
        top.addWidget(scroll, 1)
        top.addLayout(pdf_box)

        # right, bottom: include + notes
        self.include = QCheckBox("Include")
        self.include.toggled.connect(self.on_include_toggled)
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("Notes")
        self.notes.textChanged.connect(self.on_notes_changed)

        self.right = QWidget()
        rv = QVBoxLayout(self.right)
        rv.addLayout(top, 2)
        rv.addWidget(self.include)
        rv.addWidget(self.notes, 1)
        self.right.setEnabled(False)

        split = QSplitter()
        split.addWidget(left)
        split.addWidget(self.right)
        split.setSizes([450, 650])
        self.setCentralWidget(split)
        self.populate()

        menu = self.menuBar().addMenu("Settings")
        act_loc = QAction("Library location…", self)
        act_loc.triggered.connect(self.change_location)
        menu.addAction(act_loc)

    # ---- persistence ----
    def load(self):
        db = json.loads(self.db_path.read_text("utf-8")
                        ) if self.db_path.exists() else {}
        for e in db.values():
            for k, v in USER_DEFAULTS.items():
                e["user"].setdefault(k, v)
        return db

    def save(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path.write_text(json.dumps(
            self.db, indent=2, ensure_ascii=False), "utf-8")

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
        self.select_key(entries[0]["ID"])

    def select_key(self, key):
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.data(Qt.UserRole) == key:
                # fires currentItemChanged -> show_entry
                self.list.setCurrentItem(item)
                self.list.scrollToItem(item)
                return
        self.show_entry(None)
        
    def update_title(self):
        self.setWindowTitle(f"Literature — {self.db_path}")

    def change_location(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Library location", str(self.db_path), "JSON (*.json)",
            options=QFileDialog.Option.DontConfirmOverwrite)
        if not path:
            return
        new = Path(path)
        if not new.suffix:
            new = new.with_suffix(".json")
        if new == self.db_path:
            return
        self.db_path = new
        self.settings.setValue("db_path", str(new))
        if new.exists():
            self.db = self.load()  # switch to the library already there
        else:
            self.save()            # write the current library to the new location
        self.populate()
        self.show_entry(None)
        self.update_title()


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
            self.update_pdf_label()
        else:
            self.include.setChecked(False)
            self.notes.clear()
            self.pdf_label.setText("(no PDF)")

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
        
    def pdf_dir(self):
        d = self.db_path.parent / "pdfs"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def attach_pdf(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Attach PDF", "", "PDF files (*.pdf)")
        if not path:
            return
        safe_key = self.key.replace("/", "_")
        dest = self.pdf_dir() / f"{safe_key}.pdf"
        shutil.copy(path, dest)
        self.db[self.key]["user"]["pdf"] = dest.relative_to(
            self.db_path.parent).as_posix()
        self.save()
        self.update_pdf_label()

    def open_pdf(self):
        pdf = self.db[self.key]["user"]["pdf"] if self.key else ""
        if not pdf:
            return
        path = self.resolve_pdf(pdf)
        if not path.exists():
            QMessageBox.warning(self, "Open PDF", f"File not found:\n{path}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def resolve_pdf(self, stored):
        p = Path(stored)
        if not p.is_absolute():
            return self.db_path.parent / p
        if p.exists():
            return p
        # old absolute entry from another device: fall back to the pdfs folder here
        return self.pdf_dir() / p.name

    def update_pdf_label(self):
        pdf = self.db[self.key]["user"]["pdf"]
        if not pdf:
            self.pdf_label.setText("(no PDF)")
            return
        path = self.resolve_pdf(pdf)
        if not path.exists():
            self.pdf_label.setText(f"(PDF not found: {path.name})")
            return
        self.pdf_doc.load(str(path))
        if self.pdf_doc.status() != QPdfDocument.Status.Ready:
            self.pdf_label.setText(f"(cannot preview {path.name})")
            return
        pts = self.pdf_doc.pagePointSize(0)
        h = int(PDF_W * pts.height() / pts.width())
        img = self.pdf_doc.render(0, QSize(PDF_W, h))
        page = QImage(img.size(), QImage.Format_RGB32)
        page.fill(Qt.white)
        p = QPainter(page)
        p.drawImage(0, 0, img)
        p.end()
        self.pdf_label.setPixmap(QPixmap.fromImage(
            page.copy(0, 0, PDF_W, min(PDF_H, h))))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = Main()
    win.show()
    sys.exit(app.exec())
