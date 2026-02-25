"""Dialog for configuring binary (.i16 / .bin) export options."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QRadioButton,
    QLabel,
    QDoubleSpinBox,
    QComboBox,
    QListWidget,
    QListWidgetItem,
    QDialogButtonBox,
    QButtonGroup,
)

from models import StreamState


class ExportBinaryDialog(QDialog):
    """Dialog for configuring int16 binary export (.i16 / .bin)."""

    def __init__(self, state: StreamState, parent=None):
        super().__init__(parent)
        self._state = state
        self.setWindowTitle("Export Binary File")
        self.setMinimumWidth(400)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ── Export range ─────────────────────────────────────────────────────
        range_group = QGroupBox("Export Range")
        range_layout = QVBoxLayout(range_group)
        self._range_btn_grp = QButtonGroup(self)

        s, e = self._state.view_start, self._state.view_end
        self._range_view = QRadioButton(
            f"Current view  ({s:.3f} – {e:.3f} s)"
        )
        self._range_full = QRadioButton(
            f"Full recording  (0 – {self._state.duration:.3f} s)"
        )
        self._range_view.setChecked(True)
        self._range_btn_grp.addButton(self._range_view)
        self._range_btn_grp.addButton(self._range_full)
        range_layout.addWidget(self._range_view)
        range_layout.addWidget(self._range_full)
        layout.addWidget(range_group)

        # ── Channel selection ─────────────────────────────────────────────────
        ch_group = QGroupBox("Channels")
        ch_layout = QVBoxLayout(ch_group)
        self._ch_btn_grp = QButtonGroup(self)

        displayed = self._state.get_active_channels()
        displayed_str = ", ".join(str(c + 1) for c in displayed)
        self._ch_displayed = QRadioButton(
            f"Currently displayed  (Ch {displayed_str})"
        )
        self._ch_all = QRadioButton(
            f"All channels  ({self._state.num_channels} total)"
        )
        self._ch_select = QRadioButton("Select channels:")

        self._ch_displayed.setChecked(True)
        self._ch_btn_grp.addButton(self._ch_displayed)
        self._ch_btn_grp.addButton(self._ch_all)
        self._ch_btn_grp.addButton(self._ch_select)

        ch_layout.addWidget(self._ch_displayed)
        ch_layout.addWidget(self._ch_all)
        ch_layout.addWidget(self._ch_select)

        # Scrollable channel checklist (enabled only for "Select channels")
        self._ch_list = QListWidget()
        self._ch_list.setMaximumHeight(100)
        self._ch_list.setEnabled(False)
        for i in range(self._state.num_channels):
            item = QListWidgetItem(f"Channel {i + 1}")
            item.setData(Qt.ItemDataRole.UserRole, i)
            item.setCheckState(
                Qt.CheckState.Checked if i in displayed else Qt.CheckState.Unchecked
            )
            self._ch_list.addItem(item)

        self._ch_select.toggled.connect(self._ch_list.setEnabled)
        ch_layout.addWidget(self._ch_list)
        layout.addWidget(ch_group)

        # ── Scale factor ──────────────────────────────────────────────────────
        scale_group = QGroupBox("Scale Factor")
        scale_layout = QVBoxLayout(scale_group)
        scale_layout.addWidget(
            QLabel("Multiply data by (e.g. 1e6 converts V → µV):")
        )
        self._scale_spin = QDoubleSpinBox()
        self._scale_spin.setDecimals(0)
        self._scale_spin.setRange(1, 1_000_000_000)
        self._scale_spin.setValue(1_000_000)
        self._scale_spin.setSingleStep(1_000_000)
        scale_layout.addWidget(self._scale_spin)
        layout.addWidget(scale_group)

        # ── Format options ────────────────────────────────────────────────────
        fmt_group = QGroupBox("Format")
        fmt_layout = QVBoxLayout(fmt_group)

        layout_row = QHBoxLayout()
        layout_row.addWidget(QLabel("Sample layout:"))
        self._layout_combo = QComboBox()
        self._layout_combo.addItem("Interlaced (default, recommended)", "interlaced")
        self._layout_combo.addItem("Channel-sequential", "sequential")
        layout_row.addWidget(self._layout_combo)
        fmt_layout.addLayout(layout_row)

        ext_row = QHBoxLayout()
        ext_row.addWidget(QLabel("File extension:"))
        self._ext_combo = QComboBox()
        self._ext_combo.addItem(".i16  (TDT standard)", ".i16")
        self._ext_combo.addItem(".bin  (Kilosort / Plexon Offline Sorter)", ".bin")
        ext_row.addWidget(self._ext_combo)
        fmt_layout.addLayout(ext_row)

        layout.addWidget(fmt_group)

        # ── Info label ────────────────────────────────────────────────────────
        info = QLabel(
            f"<small><b>Sample rate: {self._state.sample_rate:.6f} Hz</b> — "
            "specify this when importing in Plexon Offline Sorter or Kilosort.</small>"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # ── Buttons ───────────────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_options(self) -> dict:
        """Return selected export options."""
        if self._ch_displayed.isChecked():
            channels = self._state.get_active_channels()
        elif self._ch_all.isChecked():
            channels = list(range(self._state.num_channels))
        else:
            channels = [
                self._ch_list.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self._ch_list.count())
                if self._ch_list.item(i).checkState() == Qt.CheckState.Checked
            ]
            if not channels:
                channels = self._state.get_active_channels()

        return {
            "range": "current_view" if self._range_view.isChecked() else "full",
            "channels": channels,
            "scale": self._scale_spin.value(),
            "layout": self._layout_combo.currentData(),
            "extension": self._ext_combo.currentData(),
        }
