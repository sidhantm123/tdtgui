"""Control panel widget for channel selection and view controls."""
from typing import Dict, List, Optional

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QGroupBox,
    QRadioButton,
    QButtonGroup,
    QSpinBox,
    QComboBox,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QDoubleSpinBox,
    QCheckBox,
    QFrame,
)

from models import StreamState, ChannelMode


class ControlPanel(QWidget):
    """
    Control panel for stream and channel selection.

    Contains:
    - Channel mode selection (single/overlay)
    - Single channel selector
    - Overlay channel list with add/remove
    - View range controls
    """

    # Signals
    channel_mode_changed = Signal(ChannelMode)
    single_channel_changed = Signal(int)
    overlay_channels_changed = Signal(list)  # List[int]
    view_range_requested = Signal(float, float)  # start, end
    refresh_requested = Signal()
    scatter_mode_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._state: Optional[StreamState] = None

    def _setup_ui(self):
        """Set up the widget layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Stream info
        self._stream_info_label = QLabel("No stream selected")
        self._stream_info_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._stream_info_label)

        # Channel mode group
        mode_group = QGroupBox("Channel Mode")
        mode_layout = QVBoxLayout(mode_group)

        self._mode_button_group = QButtonGroup(self)

        self._single_radio = QRadioButton("Single Channel")
        self._single_radio.setChecked(True)
        self._mode_button_group.addButton(self._single_radio, 0)
        mode_layout.addWidget(self._single_radio)

        self._overlay_radio = QRadioButton("Overlay Channels")
        self._mode_button_group.addButton(self._overlay_radio, 1)
        mode_layout.addWidget(self._overlay_radio)

        self._mode_button_group.idClicked.connect(self._on_mode_changed)

        layout.addWidget(mode_group)

        # Single channel selection
        self._single_group = QGroupBox("Channel Selection")
        single_layout = QHBoxLayout(self._single_group)

        single_layout.addWidget(QLabel("Channel:"))
        self._channel_spin = QSpinBox()
        self._channel_spin.setMinimum(0)
        self._channel_spin.setMaximum(0)
        self._channel_spin.valueChanged.connect(self._on_single_channel_changed)
        single_layout.addWidget(self._channel_spin)
        single_layout.addStretch()

        layout.addWidget(self._single_group)

        # Overlay channel selection
        self._overlay_group = QGroupBox("Overlay Channels (max 8)")
        overlay_layout = QVBoxLayout(self._overlay_group)

        # Add channel row
        add_row = QHBoxLayout()
        add_row.addWidget(QLabel("Add:"))
        self._add_channel_combo = QComboBox()
        self._add_channel_combo.setMinimumWidth(80)
        add_row.addWidget(self._add_channel_combo)

        self._add_btn = QPushButton("+")
        self._add_btn.setFixedWidth(30)
        self._add_btn.clicked.connect(self._on_add_channel)
        add_row.addWidget(self._add_btn)
        add_row.addStretch()
        overlay_layout.addLayout(add_row)

        # Channel list
        self._overlay_list = QListWidget()
        self._overlay_list.setMaximumHeight(120)
        overlay_layout.addWidget(self._overlay_list)

        # Remove button
        self._remove_btn = QPushButton("Remove Selected")
        self._remove_btn.clicked.connect(self._on_remove_channel)
        overlay_layout.addWidget(self._remove_btn)

        self._overlay_group.setVisible(False)
        layout.addWidget(self._overlay_group)

        # View controls
        view_group = QGroupBox("View Range")
        view_layout = QVBoxLayout(view_group)

        # Start time
        start_row = QHBoxLayout()
        start_row.addWidget(QLabel("Start (s):"))
        self._start_spin = QDoubleSpinBox()
        self._start_spin.setDecimals(3)
        self._start_spin.setMinimum(0)
        self._start_spin.setMaximum(9999999)
        self._start_spin.setSingleStep(0.1)
        start_row.addWidget(self._start_spin)
        view_layout.addLayout(start_row)

        # End time
        end_row = QHBoxLayout()
        end_row.addWidget(QLabel("End (s):"))
        self._end_spin = QDoubleSpinBox()
        self._end_spin.setDecimals(3)
        self._end_spin.setMinimum(0)
        self._end_spin.setMaximum(9999999)
        self._end_spin.setSingleStep(0.1)
        end_row.addWidget(self._end_spin)
        view_layout.addLayout(end_row)

        # Apply button
        btn_row = QHBoxLayout()
        self._apply_view_btn = QPushButton("Apply View")
        self._apply_view_btn.clicked.connect(self._on_apply_view)
        btn_row.addWidget(self._apply_view_btn)

        self._reset_view_btn = QPushButton("Reset")
        self._reset_view_btn.clicked.connect(self._on_reset_view)
        btn_row.addWidget(self._reset_view_btn)
        view_layout.addLayout(btn_row)

        layout.addWidget(view_group)

        # Vrms display
        self._vrms_group = QGroupBox("Vrms")
        vrms_layout = QVBoxLayout(self._vrms_group)
        self._vrms_label = QLabel("--")
        self._vrms_label.setStyleSheet("font-family: monospace; font-size: 11px;")
        vrms_layout.addWidget(self._vrms_label)
        layout.addWidget(self._vrms_group)

        # Display options
        display_group = QGroupBox("Display")
        display_layout = QVBoxLayout(display_group)
        self._scatter_check = QCheckBox("Scatter / Dot Mode")
        self._scatter_check.setChecked(False)
        self._scatter_check.stateChanged.connect(self._on_scatter_mode_changed)
        display_layout.addWidget(self._scatter_check)
        layout.addWidget(display_group)

        # Refresh button
        self._refresh_btn = QPushButton("Refresh Plot")
        self._refresh_btn.clicked.connect(lambda: self.refresh_requested.emit())
        layout.addWidget(self._refresh_btn)

        layout.addStretch()

    def set_state(self, state: StreamState):
        """Set the stream state to display."""
        self._state = state

        # Update stream info
        self._stream_info_label.setText(
            f"{state.stream_name}\n"
            f"{state.num_channels} ch @ {state.sample_rate:.0f} Hz"
        )

        # Update channel selector range
        self._channel_spin.setMaximum(max(0, state.num_channels - 1))
        self._channel_spin.setValue(state.selected_channel)

        # Update overlay channel combo
        self._add_channel_combo.clear()
        for i in range(state.num_channels):
            self._add_channel_combo.addItem(f"Ch {i}", i)

        # Update mode
        if state.channel_mode == ChannelMode.SINGLE:
            self._single_radio.setChecked(True)
            self._single_group.setVisible(True)
            self._overlay_group.setVisible(False)
        else:
            self._overlay_radio.setChecked(True)
            self._single_group.setVisible(False)
            self._overlay_group.setVisible(True)

        # Update overlay list
        self._update_overlay_list()

        # Update view range
        self._start_spin.setMaximum(state.duration)
        self._end_spin.setMaximum(state.duration)
        self._start_spin.setValue(state.view_start)
        self._end_spin.setValue(state.view_end)

        # Restore scatter mode
        self._scatter_check.blockSignals(True)
        self._scatter_check.setChecked(state.scatter_mode)
        self._scatter_check.blockSignals(False)

        # Restore Vrms display
        self.update_vrms(state.vrms_values if state.vrms_values else None)

    def _update_overlay_list(self):
        """Update the overlay channel list widget."""
        self._overlay_list.clear()
        if self._state:
            for ch in self._state.overlay_channels:
                item = QListWidgetItem(f"Channel {ch}")
                item.setData(Qt.ItemDataRole.UserRole, ch)
                self._overlay_list.addItem(item)

    def _on_mode_changed(self, button_id: int):
        """Handle channel mode change."""
        if button_id == 0:
            mode = ChannelMode.SINGLE
            self._single_group.setVisible(True)
            self._overlay_group.setVisible(False)
        else:
            mode = ChannelMode.OVERLAY
            self._single_group.setVisible(False)
            self._overlay_group.setVisible(True)

        if self._state:
            self._state.channel_mode = mode
        self.channel_mode_changed.emit(mode)

    def _on_single_channel_changed(self, value: int):
        """Handle single channel selection change."""
        if self._state:
            self._state.selected_channel = value
        self.single_channel_changed.emit(value)

    def _on_add_channel(self):
        """Handle add channel button click."""
        if not self._state:
            return

        ch = self._add_channel_combo.currentData()
        if ch is not None and self._state.add_overlay_channel(ch):
            self._update_overlay_list()
            self.overlay_channels_changed.emit(self._state.overlay_channels.copy())

    def _on_remove_channel(self):
        """Handle remove channel button click."""
        if not self._state:
            return

        item = self._overlay_list.currentItem()
        if item:
            ch = item.data(Qt.ItemDataRole.UserRole)
            # Don't allow removing the last channel
            if len(self._state.overlay_channels) > 1:
                if self._state.remove_overlay_channel(ch):
                    self._update_overlay_list()
                    self.overlay_channels_changed.emit(
                        self._state.overlay_channels.copy()
                    )

    def _on_apply_view(self):
        """Handle apply view button click."""
        start = self._start_spin.value()
        end = self._end_spin.value()

        if end <= start:
            end = start + 0.1

        if self._state:
            self._state.view_start = start
            self._state.view_end = end

        self.view_range_requested.emit(start, end)

    def _on_reset_view(self):
        """Handle reset view button click."""
        if self._state:
            self._start_spin.setValue(0)
            self._end_spin.setValue(min(10.0, self._state.duration))
            self._on_apply_view()

    def update_view_range(self, start: float, end: float):
        """Update the view range spinboxes (called from plot)."""
        self._start_spin.blockSignals(True)
        self._end_spin.blockSignals(True)
        self._start_spin.setValue(start)
        self._end_spin.setValue(end)
        self._start_spin.blockSignals(False)
        self._end_spin.blockSignals(False)

        if self._state:
            self._state.view_start = start
            self._state.view_end = end

    def _on_scatter_mode_changed(self, state: int):
        """Handle scatter mode checkbox toggle."""
        enabled = state == Qt.CheckState.Checked.value
        if self._state:
            self._state.scatter_mode = enabled
        self.scatter_mode_changed.emit(enabled)

    def update_vrms(self, vrms_values: Optional[Dict[int, float]]):
        """Update the Vrms display."""
        if not vrms_values:
            self._vrms_label.setText("--")
            return

        lines = []
        for ch_idx, vrms in sorted(vrms_values.items()):
            if vrms < 1e-6:
                lines.append(f"Ch {ch_idx}: {vrms * 1e9:.1f} nV")
            elif vrms < 1e-3:
                lines.append(f"Ch {ch_idx}: {vrms * 1e6:.1f} uV")
            elif vrms < 1:
                lines.append(f"Ch {ch_idx}: {vrms * 1e3:.2f} mV")
            else:
                lines.append(f"Ch {ch_idx}: {vrms:.4f} V")

        self._vrms_label.setText("\n".join(lines))

    def clear(self):
        """Clear the panel."""
        self._state = None
        self._stream_info_label.setText("No stream selected")
        self._channel_spin.setMaximum(0)
        self._channel_spin.setValue(0)
        self._add_channel_combo.clear()
        self._overlay_list.clear()
        self._start_spin.setValue(0)
        self._end_spin.setValue(10)
        self._vrms_label.setText("--")
        self._scatter_check.setChecked(False)
