"""Spectrum analysis panel widget."""
from typing import List, Optional

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QGroupBox,
    QPushButton,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QCheckBox,
    QListWidget,
    QListWidgetItem,
)

from models import StreamState


class SpectrumPanel(QWidget):
    """
    Panel for controlling FFT/PSD analysis.

    Features:
    - Method selection (FFT/PSD)
    - Time interval selection
    - Channel selection for analysis
    - PSD parameters (nperseg, overlap)
    """

    # Signals
    analyze_requested = Signal(dict)  # Analysis parameters
    enable_selection_changed = Signal(bool)  # Enable/disable plot selection

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._state: Optional[StreamState] = None

    def _setup_ui(self):
        """Set up the widget layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        layout.addWidget(QLabel("<b>Spectrum Analysis</b>"))

        # Method selection
        method_group = QGroupBox("Method")
        method_layout = QVBoxLayout(method_group)

        self._method_combo = QComboBox()
        self._method_combo.addItem("FFT Magnitude", "fft")
        self._method_combo.addItem("PSD (Welch)", "psd")
        self._method_combo.currentIndexChanged.connect(self._on_method_changed)
        method_layout.addWidget(self._method_combo)

        layout.addWidget(method_group)

        # Time interval
        interval_group = QGroupBox("Time Interval")
        interval_layout = QVBoxLayout(interval_group)

        # Enable selection on plot
        self._enable_selection_check = QCheckBox("Select on plot")
        self._enable_selection_check.stateChanged.connect(self._on_selection_toggled)
        interval_layout.addWidget(self._enable_selection_check)

        # Start time
        start_row = QHBoxLayout()
        start_row.addWidget(QLabel("Start (s):"))
        self._start_spin = QDoubleSpinBox()
        self._start_spin.setDecimals(3)
        self._start_spin.setMinimum(0)
        self._start_spin.setMaximum(9999999)
        start_row.addWidget(self._start_spin)
        interval_layout.addLayout(start_row)

        # End time
        end_row = QHBoxLayout()
        end_row.addWidget(QLabel("End (s):"))
        self._end_spin = QDoubleSpinBox()
        self._end_spin.setDecimals(3)
        self._end_spin.setMinimum(0)
        self._end_spin.setMaximum(9999999)
        end_row.addWidget(self._end_spin)
        interval_layout.addLayout(end_row)

        layout.addWidget(interval_group)

        # Channel selection
        channel_group = QGroupBox("Channels")
        channel_layout = QVBoxLayout(channel_group)

        self._use_all_check = QCheckBox("Use all displayed channels")
        self._use_all_check.setChecked(True)
        self._use_all_check.stateChanged.connect(self._on_use_all_changed)
        channel_layout.addWidget(self._use_all_check)

        self._channel_list = QListWidget()
        self._channel_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self._channel_list.setMaximumHeight(80)
        self._channel_list.setEnabled(False)
        channel_layout.addWidget(self._channel_list)

        layout.addWidget(channel_group)

        # PSD parameters
        self._psd_group = QGroupBox("PSD Parameters")
        psd_layout = QVBoxLayout(self._psd_group)

        nperseg_row = QHBoxLayout()
        nperseg_row.addWidget(QLabel("Segment size:"))
        self._nperseg_spin = QSpinBox()
        self._nperseg_spin.setRange(64, 16384)
        self._nperseg_spin.setValue(1024)
        self._nperseg_spin.setSingleStep(64)
        nperseg_row.addWidget(self._nperseg_spin)
        psd_layout.addLayout(nperseg_row)

        overlap_row = QHBoxLayout()
        overlap_row.addWidget(QLabel("Overlap:"))
        self._overlap_spin = QDoubleSpinBox()
        self._overlap_spin.setRange(0, 0.99)
        self._overlap_spin.setValue(0.5)
        self._overlap_spin.setSingleStep(0.1)
        overlap_row.addWidget(self._overlap_spin)
        psd_layout.addLayout(overlap_row)

        layout.addWidget(self._psd_group)

        # Analyze button
        self._analyze_btn = QPushButton("Analyze")
        self._analyze_btn.clicked.connect(self._on_analyze)
        layout.addWidget(self._analyze_btn)

        layout.addStretch()

        # Initial visibility
        self._on_method_changed(0)

    def set_state(self, state: StreamState):
        """Set the stream state."""
        self._state = state

        # Update time range limits
        self._start_spin.setMaximum(state.duration)
        self._end_spin.setMaximum(state.duration)

        # Set default interval if not set
        if state.fft_start is not None:
            self._start_spin.setValue(state.fft_start)
        else:
            self._start_spin.setValue(state.view_start)

        if state.fft_end is not None:
            self._end_spin.setValue(state.fft_end)
        else:
            self._end_spin.setValue(state.view_end)

        # Update PSD params
        self._nperseg_spin.setValue(state.psd_nperseg)
        self._overlap_spin.setValue(state.psd_overlap)

        # Update channel list
        self._channel_list.clear()
        for i in range(state.num_channels):
            item = QListWidgetItem(f"Channel {i+1}")
            item.setData(Qt.ItemDataRole.UserRole, i)
            self._channel_list.addItem(item)

        # Select channels
        if state.fft_channels:
            for i in range(self._channel_list.count()):
                item = self._channel_list.item(i)
                ch = item.data(Qt.ItemDataRole.UserRole)
                item.setSelected(ch in state.fft_channels)

    def _on_method_changed(self, index: int):
        """Handle method selection change."""
        method = self._method_combo.currentData()
        self._psd_group.setVisible(method == "psd")

    def _on_selection_toggled(self, state: int):
        """Handle selection checkbox toggle."""
        enabled = state == Qt.CheckState.Checked.value
        self.enable_selection_changed.emit(enabled)

    def _on_use_all_changed(self, state: int):
        """Handle use all channels checkbox."""
        use_all = state == Qt.CheckState.Checked.value
        self._channel_list.setEnabled(not use_all)

    def update_interval(self, start: float, end: float):
        """Update interval from plot selection."""
        self._start_spin.setValue(start)
        self._end_spin.setValue(end)

    def _on_analyze(self):
        """Handle analyze button click."""
        if not self._state:
            return

        # Get selected channels
        if self._use_all_check.isChecked():
            channels = self._state.get_active_channels()
        else:
            channels = []
            for item in self._channel_list.selectedItems():
                channels.append(item.data(Qt.ItemDataRole.UserRole))
            if not channels:
                channels = self._state.get_active_channels()

        # Save settings to state
        self._state.fft_start = self._start_spin.value()
        self._state.fft_end = self._end_spin.value()
        self._state.fft_channels = channels.copy()
        self._state.psd_nperseg = self._nperseg_spin.value()
        self._state.psd_overlap = self._overlap_spin.value()

        # Emit analysis request
        params = {
            "method": self._method_combo.currentData(),
            "start": self._start_spin.value(),
            "end": self._end_spin.value(),
            "channels": channels,
            "nperseg": self._nperseg_spin.value(),
            "overlap": self._overlap_spin.value(),
        }
        self.analyze_requested.emit(params)

    def clear(self):
        """Clear the panel."""
        self._state = None
        self._channel_list.clear()
        self._start_spin.setValue(0)
        self._end_spin.setValue(10)
