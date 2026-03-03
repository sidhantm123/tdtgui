"""Dialog for importing or manually editing probe geometry."""
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from models.probe import ProbeContact, ProbeGeometry


# ── helpers ───────────────────────────────────────────────────────────────────

_COLUMNS = ["Ch (1-based)", "X (µm)", "Y (µm)", "Shank ID", "Radius (µm)"]


def _geometry_to_rows(geo: ProbeGeometry) -> list:
    """Convert ProbeGeometry to a list of row value tuples."""
    rows = []
    for c in sorted(geo.contacts, key=lambda c: c.channel_idx):
        rows.append(
            (
                str(c.channel_idx + 1),  # 1-indexed display
                f"{c.x_um:.4f}",
                f"{c.y_um:.4f}",
                c.shank_id,
                f"{c.radius_um:.4f}",
            )
        )
    return rows


def _rows_to_geometry(rows: list) -> ProbeGeometry:
    """Parse table rows into a ProbeGeometry. Raises ValueError on bad data."""
    seen_channels = set()
    contacts = []
    for row_idx, row in enumerate(rows):
        label = f"Row {row_idx + 1}"
        ch_str, x_str, y_str, shank_str, r_str = row

        try:
            ch_1based = int(ch_str)
        except ValueError:
            raise ValueError(f"{label}: Channel must be an integer, got '{ch_str}'")
        if ch_1based < 1:
            raise ValueError(f"{label}: Channel must be ≥ 1, got {ch_1based}")
        ch_idx = ch_1based - 1
        if ch_idx in seen_channels:
            raise ValueError(f"{label}: Duplicate channel index {ch_1based}")
        seen_channels.add(ch_idx)

        try:
            x = float(x_str)
            y = float(y_str)
        except ValueError:
            raise ValueError(f"{label}: X and Y must be numbers")

        shank = shank_str.strip()

        try:
            radius = float(r_str)
        except ValueError:
            raise ValueError(f"{label}: Radius must be a number, got '{r_str}'")
        if radius <= 0:
            raise ValueError(f"{label}: Radius must be > 0, got {radius}")

        contacts.append(
            ProbeContact(
                channel_idx=ch_idx,
                contact_id=str(ch_1based),
                x_um=x,
                y_um=y,
                shank_id=shank,
                radius_um=radius,
            )
        )

    if not contacts:
        raise ValueError("No contacts defined")

    return ProbeGeometry(contacts=contacts)


# ── Preview table (read-only) ─────────────────────────────────────────────────

class _PreviewTable(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(0, len(_COLUMNS), parent)
        self.setHorizontalHeaderLabels(_COLUMNS)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.verticalHeader().setVisible(False)

    def load(self, rows: list):
        self.setRowCount(0)
        for row in rows:
            r = self.rowCount()
            self.insertRow(r)
            for col, val in enumerate(row):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.setItem(r, col, item)


# ── Editable table ────────────────────────────────────────────────────────────

class _EditTable(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(0, len(_COLUMNS), parent)
        self.setHorizontalHeaderLabels(_COLUMNS)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.verticalHeader().setVisible(False)

    def load(self, rows: list):
        self.setRowCount(0)
        for row in rows:
            self.append_row(row)

    def append_row(self, values=None):
        r = self.rowCount()
        self.insertRow(r)
        defaults = (str(r + 1), "0.0", "0.0", "0", "10.0")
        vals = values if values is not None else defaults
        for col, val in enumerate(vals):
            self.setItem(r, col, QTableWidgetItem(str(val)))

    def remove_selected(self):
        rows = sorted(
            {idx.row() for idx in self.selectedIndexes()}, reverse=True
        )
        for r in rows:
            self.removeRow(r)

    def get_rows(self) -> list:
        rows = []
        for r in range(self.rowCount()):
            row = []
            for col in range(len(_COLUMNS)):
                item = self.item(r, col)
                row.append(item.text().strip() if item else "")
            rows.append(tuple(row))
        return rows


# ── Main dialog ───────────────────────────────────────────────────────────────

class ProbeImportDialog(QDialog):
    """
    Two-tab dialog for loading probe geometry.

    Tab 1 — Import JSON:   pick a probeinterface JSON file and preview.
    Tab 2 — Table Editor:  manually enter or edit contacts row by row.

    Call exec(); if Accepted, geometry() returns the parsed ProbeGeometry.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Load Probe Geometry")
        self.setMinimumWidth(640)
        self.setMinimumHeight(480)

        self._geometry: Optional[ProbeGeometry] = None
        self._setup_ui()

    # ── UI setup ──────────────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._make_json_tab(), "Import JSON")
        self._tabs.addTab(self._make_table_tab(), "Table Editor")
        layout.addWidget(self._tabs)

        # Status label
        self._status = QLabel("")
        self._status.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self._status)

        # Buttons
        self._btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._btn_box.accepted.connect(self._on_accept)
        self._btn_box.rejected.connect(self.reject)
        layout.addWidget(self._btn_box)

        self._ok_btn = self._btn_box.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_btn.setEnabled(False)

    def _make_json_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # File picker row
        pick_row = QHBoxLayout()
        self._json_path_edit = QLineEdit()
        self._json_path_edit.setPlaceholderText("Path to probeinterface .json file...")
        self._json_path_edit.setReadOnly(True)
        pick_row.addWidget(self._json_path_edit)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._on_browse_json)
        pick_row.addWidget(browse_btn)
        layout.addLayout(pick_row)

        # Info label
        self._json_info = QLabel("")
        self._json_info.setStyleSheet("font-size: 11px; color: #444;")
        layout.addWidget(self._json_info)

        # Preview table
        layout.addWidget(QLabel("Preview:"))
        self._preview_table = _PreviewTable()
        layout.addWidget(self._preview_table)

        return tab

    def _make_table_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Editable table — created first so button signals can bind to it
        self._edit_table = _EditTable()

        # Top action bar
        bar = QHBoxLayout()
        import_btn = QPushButton("Load from JSON...")
        import_btn.setToolTip("Pre-fill table from a probeinterface JSON file")
        import_btn.clicked.connect(self._on_table_import_json)
        bar.addWidget(import_btn)
        bar.addStretch()
        add_btn = QPushButton("+ Add Row")
        add_btn.clicked.connect(self._edit_table.append_row)
        bar.addWidget(add_btn)
        remove_btn = QPushButton("− Remove Row")
        remove_btn.clicked.connect(self._edit_table.remove_selected)
        bar.addWidget(remove_btn)
        layout.addLayout(bar)

        layout.addWidget(self._edit_table)

        # Hint
        hint = QLabel("Ch is 1-indexed (Ch 1 = TDT channel 0 internally).")
        hint.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(hint)

        return tab

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_browse_json(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Probe JSON", "", "JSON Files (*.json)"
        )
        if not path:
            return
        self._load_json_file(path, update_table=False)

    def _on_table_import_json(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Probe JSON", "", "JSON Files (*.json)"
        )
        if not path:
            return
        self._load_json_file(path, update_table=True)
        self._tabs.setCurrentIndex(1)  # stay on / switch to table tab

    def _load_json_file(self, path: str, update_table: bool):
        try:
            geo = ProbeGeometry.from_probeinterface_file(path)
        except Exception as exc:
            QMessageBox.warning(self, "Parse Error", str(exc))
            return

        rows = _geometry_to_rows(geo)
        n_shanks = len(geo.get_shank_groups())

        # Update JSON tab
        self._json_path_edit.setText(path)
        self._json_info.setText(
            f"{len(rows)} contacts  ·  {n_shanks} shanks  ·  "
            f"units: {geo.si_units}"
        )
        self._preview_table.load(rows)

        # Optionally pre-fill the table editor
        if update_table:
            self._edit_table.load(rows)

        self._geometry = geo
        self._ok_btn.setEnabled(True)
        self._set_status(f"Loaded {len(rows)} contacts from {path}")

    def _on_accept(self):
        # Determine which tab is active
        active = self._tabs.currentIndex()

        if active == 0:
            # JSON tab — geometry already parsed
            if self._geometry is None:
                QMessageBox.warning(
                    self, "No Probe Loaded", "Please select and parse a JSON file first."
                )
                return
        else:
            # Table editor — parse from table
            rows = self._edit_table.get_rows()
            try:
                self._geometry = _rows_to_geometry(rows)
            except ValueError as exc:
                QMessageBox.warning(self, "Validation Error", str(exc))
                return

        self.accept()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_status(self, msg: str):
        self._status.setText(msg)

    def geometry(self) -> Optional[ProbeGeometry]:
        """Return the parsed ProbeGeometry after the dialog is accepted."""
        return self._geometry
