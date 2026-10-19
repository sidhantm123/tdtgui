"""Read-only dialog showing recording metadata and Blackrock .ccf settings."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QGroupBox,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QCheckBox,
    QDialogButtonBox,
)

from models.recording import RecordingBlock
from blackrock_io.ccf_reader import PREFERRED_FIELDS


class RecordingInfoDialog(QDialog):
    """Shows a summary of the loaded recording and, for Blackrock, its .ccf channel settings."""

    def __init__(self, block: RecordingBlock, parent=None):
        super().__init__(parent)
        self._block = block
        self._ccf = block.metadata.get("ccf") if block.metadata else None
        self.setWindowTitle("Recording Info")
        self.setMinimumSize(560, 420)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ── Summary ──────────────────────────────────────────────────────────
        summary_group = QGroupBox("Recording")
        summary_layout = QVBoxLayout(summary_group)

        block = self._block
        lines = [
            f"<b>{block.name}</b>",
            f"Format: {'Blackrock' if block.source == 'blackrock' else 'TDT'}",
            f"Path: {block.path}",
            f"Duration: {block.duration:.3f} s",
        ]
        for name, info in sorted(block.streams.items()):
            lines.append(
                f"Stream {name}: {info.num_channels} ch @ {info.sample_rate:g} Hz, "
                f"{info.num_samples} samples"
            )
        summary = QLabel("<br>".join(lines))
        summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        summary.setWordWrap(True)
        summary_layout.addWidget(summary)
        layout.addWidget(summary_group)

        # ── CCF settings (Blackrock only) ────────────────────────────────────
        if block.source == "blackrock":
            layout.addWidget(self._build_ccf_group(), 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_ccf_group(self) -> QGroupBox:
        group = QGroupBox("Channel Settings (.ccf)")
        group_layout = QVBoxLayout(group)

        ccf = self._ccf
        if ccf is None:
            group_layout.addWidget(QLabel("No .ccf file found in the recording folder."))
            return group

        header = f"File: {ccf['path']}"
        if ccf.get("version"):
            header += f"  (version {ccf['version']})"
        header_label = QLabel(header)
        header_label.setWordWrap(True)
        group_layout.addWidget(header_label)

        if ccf.get("error"):
            error_label = QLabel(ccf["error"])
            error_label.setWordWrap(True)
            group_layout.addWidget(error_label)
            if not ccf.get("channels"):
                return group

        self._all_fields_check = QCheckBox("Show all fields")
        self._all_fields_check.toggled.connect(self._populate_table)
        group_layout.addWidget(self._all_fields_check)

        self._table = QTableWidget()
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        group_layout.addWidget(self._table)

        self._populate_table(False)
        return group

    def _populate_table(self, show_all: bool):
        channels = self._ccf["channels"]
        present = set()
        for ch in channels:
            present.update(ch["fields"])

        columns = [f for f in PREFERRED_FIELDS if f in present]
        if show_all or len(columns) <= 1:
            # Too little matched the known layout; fall back to every field
            columns += sorted(present - set(columns))

        self._table.clear()
        self._table.setColumnCount(len(columns) + 1)
        self._table.setRowCount(len(channels))
        self._table.setHorizontalHeaderLabels(["chan"] + columns)

        for row, ch in enumerate(channels):
            self._table.setItem(row, 0, QTableWidgetItem(str(ch["chan"])))
            for col, key in enumerate(columns, start=1):
                self._table.setItem(row, col, QTableWidgetItem(ch["fields"].get(key, "")))

        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
