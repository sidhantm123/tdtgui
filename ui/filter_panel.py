"""Filter chain panel widget with channel grouping support."""
from typing import Dict, List, Optional

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QGroupBox,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QGridLayout,
    QScrollArea,
    QFrame,
)

from models import StreamState, FilterConfig, FilterType
from models.probe import ProbeGeometry


# Colors for subgroups (distinct, readable)
SUBGROUP_COLORS = [
    "#1f77b4",  # Blue
    "#ff7f0e",  # Orange
    "#2ca02c",  # Green
    "#d62728",  # Red
    "#9467bd",  # Purple
    "#8c564b",  # Brown
    "#e377c2",  # Pink
    "#17becf",  # Cyan
    "#bcbd22",  # Olive
    "#aec7e8",  # Light blue
]


class ChannelGroupWidget(QWidget):
    """
    Interactive widget for assigning channels to subgroups.

    Top bar: [+ Add Subgroup] [SG 1] [SG 2] ...
    Grid: channel buttons colored by assigned subgroup.
    Status: "X / N channels assigned"
    """

    assignment_changed = Signal()

    def __init__(self, num_channels: int, parent=None):
        super().__init__(parent)
        self._num_channels = num_channels

        # State
        self._subgroups: List[str] = []  # subgroup labels
        self._active_subgroup: Optional[int] = None  # index into _subgroups
        self._assignments: Dict[int, Optional[int]] = {
            i: None for i in range(num_channels)
        }  # channel -> subgroup index or None
        self._channel_buttons: Dict[int, QPushButton] = {}
        self._subgroup_buttons: List[QPushButton] = []

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Subgroup bar in a scroll area
        sg_scroll = QScrollArea()
        sg_scroll.setWidgetResizable(True)
        sg_scroll.setMaximumHeight(45)
        sg_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        sg_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sg_scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._sg_container = QWidget()
        self._sg_layout = QHBoxLayout(self._sg_container)
        self._sg_layout.setContentsMargins(0, 0, 0, 0)
        self._sg_layout.setSpacing(4)

        self._add_sg_btn = QPushButton("+ Add Subgroup")
        self._add_sg_btn.setFixedHeight(30)
        self._add_sg_btn.clicked.connect(self._on_add_subgroup)
        self._sg_layout.addWidget(self._add_sg_btn)
        self._sg_layout.addStretch()

        sg_scroll.setWidget(self._sg_container)
        layout.addWidget(sg_scroll)

        # Channel grid in a scroll area
        ch_scroll = QScrollArea()
        ch_scroll.setWidgetResizable(True)
        ch_scroll.setMinimumHeight(80)
        max_rows = (self._num_channels + 7) // 8
        ch_scroll.setMaximumHeight(min(max_rows * 34 + 10, 250))

        ch_container = QWidget()
        self._ch_grid = QGridLayout(ch_container)
        self._ch_grid.setSpacing(3)
        self._ch_grid.setContentsMargins(2, 2, 2, 2)

        cols = 8
        for i in range(self._num_channels):
            btn = QPushButton(str(i + 1))  # 1-indexed display
            btn.setFixedSize(45, 28)
            btn.setCheckable(False)
            btn.setStyleSheet(self._channel_style(None))
            btn.clicked.connect(lambda checked, ch=i: self._on_channel_clicked(ch))
            row, col = divmod(i, cols)
            self._ch_grid.addWidget(btn, row, col)
            self._channel_buttons[i] = btn

        ch_scroll.setWidget(ch_container)
        layout.addWidget(ch_scroll)

        # Status label
        self._status_label = QLabel(f"0 / {self._num_channels} channels assigned")
        self._status_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self._status_label)

    def _channel_style(self, subgroup_idx: Optional[int]) -> str:
        """Return stylesheet for a channel button given its subgroup."""
        if subgroup_idx is None:
            return (
                "QPushButton { background-color: #e0e0e0; border: 1px solid #bbb; "
                "border-radius: 3px; font-size: 11px; }"
            )
        color = SUBGROUP_COLORS[subgroup_idx % len(SUBGROUP_COLORS)]
        return (
            f"QPushButton {{ background-color: {color}; color: white; "
            f"border: 1px solid {color}; border-radius: 3px; font-weight: bold; "
            f"font-size: 11px; }}"
        )

    def _subgroup_style(self, idx: int, active: bool) -> str:
        """Return stylesheet for a subgroup button."""
        color = SUBGROUP_COLORS[idx % len(SUBGROUP_COLORS)]
        if active:
            return (
                f"QPushButton {{ background-color: {color}; color: white; "
                f"border: 3px solid #333; border-radius: 4px; font-weight: bold; }}"
            )
        return (
            f"QPushButton {{ background-color: {color}; color: white; "
            f"border: 1px solid {color}; border-radius: 4px; }}"
        )

    def _on_add_subgroup(self):
        """Add a new subgroup."""
        idx = len(self._subgroups)
        label = f"SG {idx + 1}"
        self._subgroups.append(label)

        btn = QPushButton(label)
        btn.setFixedHeight(30)
        btn.setMinimumWidth(50)
        btn.setStyleSheet(self._subgroup_style(idx, False))
        btn.clicked.connect(lambda checked, sg=idx: self._on_subgroup_clicked(sg))

        # Insert before the stretch
        self._sg_layout.insertWidget(self._sg_layout.count() - 1, btn)
        self._subgroup_buttons.append(btn)

        # Auto-select the new subgroup
        self._on_subgroup_clicked(idx)

    def _on_subgroup_clicked(self, sg_idx: int):
        """Select a subgroup as the active brush."""
        self._active_subgroup = sg_idx

        # Update all subgroup button styles
        for i, btn in enumerate(self._subgroup_buttons):
            btn.setStyleSheet(self._subgroup_style(i, i == sg_idx))

    def _on_channel_clicked(self, ch: int):
        """Assign/unassign a channel to the active subgroup."""
        if self._active_subgroup is None:
            return

        current = self._assignments[ch]
        if current == self._active_subgroup:
            # Unassign
            self._assignments[ch] = None
        else:
            # Assign to active subgroup
            self._assignments[ch] = self._active_subgroup

        # Update button style
        self._channel_buttons[ch].setStyleSheet(
            self._channel_style(self._assignments[ch])
        )

        self._update_status()
        self.assignment_changed.emit()

    def _update_status(self):
        """Update the status label."""
        assigned = sum(1 for v in self._assignments.values() if v is not None)
        self._status_label.setText(
            f"{assigned} / {self._num_channels} channels assigned"
        )

    def all_assigned(self) -> bool:
        """True if every channel is assigned to a subgroup."""
        return all(v is not None for v in self._assignments.values())

    def get_channel_groups(self) -> List[List[int]]:
        """Return channel groups as list of 0-indexed channel lists."""
        groups: Dict[int, List[int]] = {}
        for ch, sg in self._assignments.items():
            if sg is not None:
                groups.setdefault(sg, []).append(ch)

        # Return in subgroup creation order
        result = []
        for sg_idx in range(len(self._subgroups)):
            if sg_idx in groups:
                result.append(sorted(groups[sg_idx]))
        return result

    def reset(self):
        """Clear all assignments and subgroups, returning widget to initial state."""
        for ch in range(self._num_channels):
            self._assignments[ch] = None
            self._channel_buttons[ch].setStyleSheet(self._channel_style(None))

        for btn in self._subgroup_buttons:
            self._sg_layout.removeWidget(btn)
            btn.setParent(None)
            btn.deleteLater()
        self._subgroup_buttons.clear()
        self._subgroups.clear()
        self._active_subgroup = None

        self._update_status()

    def set_channel_groups(self, groups: List[List[int]]):
        """Load saved channel groups (for editing existing filter)."""
        # Create subgroups
        for i, group in enumerate(groups):
            if i >= len(self._subgroups):
                self._on_add_subgroup()

            for ch in group:
                if 0 <= ch < self._num_channels:
                    self._assignments[ch] = i
                    self._channel_buttons[ch].setStyleSheet(
                        self._channel_style(i)
                    )

        self._update_status()
        self.assignment_changed.emit()


class FilterEditDialog(QDialog):
    """Dialog for adding/editing a filter."""

    def __init__(
        self,
        parent=None,
        filter_config: Optional[FilterConfig] = None,
        sample_rate: float = 24000,
        num_channels: int = 1,
        probe: Optional[ProbeGeometry] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Edit Filter" if filter_config else "Add Filter")
        self.setMinimumWidth(300)

        self._sample_rate = sample_rate
        self._num_channels = num_channels
        self._config = filter_config
        self._probe = probe

        self._setup_ui()

        if filter_config:
            self._load_config(filter_config)

    def _setup_ui(self):
        """Set up the dialog layout."""
        layout = QVBoxLayout(self)

        form = QFormLayout()

        # Filter type
        self._type_combo = QComboBox()
        self._type_combo.addItem("Low-pass", FilterType.LOWPASS)
        self._type_combo.addItem("High-pass", FilterType.HIGHPASS)
        self._type_combo.addItem("Band-pass", FilterType.BANDPASS)
        self._type_combo.addItem("Notch", FilterType.NOTCH)
        self._type_combo.addItem("Common Avg Ref (CAR)", FilterType.CAR)
        self._type_combo.addItem("Common Median Ref (CMR)", FilterType.CMR)
        self._type_combo.addItem("Vrms Threshold", FilterType.VRMS_THRESHOLD)
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        form.addRow("Type:", self._type_combo)

        # Order (for butter filters)
        self._order_spin = QSpinBox()
        self._order_spin.setRange(1, 10)
        self._order_spin.setValue(4)
        self._order_label = QLabel("Order:")
        form.addRow(self._order_label, self._order_spin)

        # Cutoff low
        nyquist = self._sample_rate / 2
        self._cutoff_low_spin = QDoubleSpinBox()
        self._cutoff_low_spin.setRange(0.1, nyquist - 1)
        self._cutoff_low_spin.setValue(300)
        self._cutoff_low_spin.setSuffix(" Hz")
        self._cutoff_low_label = QLabel("Low Cutoff:")
        form.addRow(self._cutoff_low_label, self._cutoff_low_spin)

        # Cutoff high
        self._cutoff_high_spin = QDoubleSpinBox()
        self._cutoff_high_spin.setRange(0.1, nyquist - 1)
        self._cutoff_high_spin.setValue(6000)
        self._cutoff_high_spin.setSuffix(" Hz")
        self._cutoff_high_label = QLabel("High Cutoff:")
        form.addRow(self._cutoff_high_label, self._cutoff_high_spin)

        # Notch frequency
        self._notch_freq_spin = QDoubleSpinBox()
        self._notch_freq_spin.setRange(0.1, nyquist - 1)
        self._notch_freq_spin.setValue(60)
        self._notch_freq_spin.setSuffix(" Hz")
        self._notch_freq_label = QLabel("Notch Freq:")
        form.addRow(self._notch_freq_label, self._notch_freq_spin)

        # Notch Q
        self._notch_q_spin = QDoubleSpinBox()
        self._notch_q_spin.setRange(1, 100)
        self._notch_q_spin.setValue(30)
        self._notch_q_label = QLabel("Q Factor:")
        form.addRow(self._notch_q_label, self._notch_q_spin)

        # Vrms multiplier
        self._vrms_mult_spin = QDoubleSpinBox()
        self._vrms_mult_spin.setRange(0.1, 100.0)
        self._vrms_mult_spin.setValue(3.0)
        self._vrms_mult_spin.setSingleStep(0.5)
        self._vrms_mult_label = QLabel("Threshold (x Vrms):")
        form.addRow(self._vrms_mult_label, self._vrms_mult_spin)

        layout.addLayout(form)

        # Channel group widget (for CAR/CMR)
        self._group_widget = ChannelGroupWidget(self._num_channels, self)
        self._group_widget.assignment_changed.connect(self._on_assignment_changed)
        self._group_widget.setVisible(False)
        layout.addWidget(self._group_widget)

        # Auto-group button (shown only when CAR/CMR is selected)
        self._auto_group_btn = QPushButton("Auto-group by Shank")
        self._auto_group_btn.setToolTip(
            "Assign channels to subgroups based on the loaded probe shank layout"
        )
        self._auto_group_btn.clicked.connect(self._on_auto_group_by_shank)
        self._auto_group_btn.setVisible(False)
        self._auto_group_btn.setEnabled(self._probe is not None)
        layout.addWidget(self._auto_group_btn)

        # Buttons
        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._button_box.accepted.connect(self.accept)
        self._button_box.rejected.connect(self.reject)
        layout.addWidget(self._button_box)

        # Initial visibility
        self._on_type_changed(0)

    def _on_type_changed(self, index: int):
        """Update UI based on selected filter type."""
        filter_type = self._type_combo.currentData()

        # Hide all type-specific controls first
        for widget in [
            self._order_label, self._order_spin,
            self._cutoff_low_label, self._cutoff_low_spin,
            self._cutoff_high_label, self._cutoff_high_spin,
            self._notch_freq_label, self._notch_freq_spin,
            self._notch_q_label, self._notch_q_spin,
            self._vrms_mult_label, self._vrms_mult_spin,
        ]:
            widget.setVisible(False)

        self._group_widget.setVisible(False)
        self._auto_group_btn.setVisible(False)

        if filter_type == FilterType.LOWPASS:
            self._order_label.setVisible(True)
            self._order_spin.setVisible(True)
            self._cutoff_high_label.setText("Cutoff:")
            self._cutoff_high_label.setVisible(True)
            self._cutoff_high_spin.setVisible(True)
            self.setMinimumWidth(300)
            self._enable_ok(True)

        elif filter_type == FilterType.HIGHPASS:
            self._order_label.setVisible(True)
            self._order_spin.setVisible(True)
            self._cutoff_low_label.setText("Cutoff:")
            self._cutoff_low_label.setVisible(True)
            self._cutoff_low_spin.setVisible(True)
            self.setMinimumWidth(300)
            self._enable_ok(True)

        elif filter_type == FilterType.BANDPASS:
            self._order_label.setVisible(True)
            self._order_spin.setVisible(True)
            self._cutoff_low_label.setText("Low Cutoff:")
            self._cutoff_low_label.setVisible(True)
            self._cutoff_low_spin.setVisible(True)
            self._cutoff_high_label.setText("High Cutoff:")
            self._cutoff_high_label.setVisible(True)
            self._cutoff_high_spin.setVisible(True)
            self.setMinimumWidth(300)
            self._enable_ok(True)

        elif filter_type == FilterType.NOTCH:
            self._notch_freq_label.setVisible(True)
            self._notch_freq_spin.setVisible(True)
            self._notch_q_label.setVisible(True)
            self._notch_q_spin.setVisible(True)
            self.setMinimumWidth(300)
            self._enable_ok(True)

        elif filter_type in (FilterType.CAR, FilterType.CMR):
            self._group_widget.setVisible(True)
            self._auto_group_btn.setVisible(True)
            self._auto_group_btn.setEnabled(self._probe is not None)
            self.setMinimumWidth(450)
            # OK only enabled when all channels assigned
            self._enable_ok(self._group_widget.all_assigned())

        elif filter_type == FilterType.VRMS_THRESHOLD:
            self._vrms_mult_label.setVisible(True)
            self._vrms_mult_spin.setVisible(True)
            self.setMinimumWidth(300)
            self._enable_ok(True)

        self.adjustSize()

    def _on_auto_group_by_shank(self):
        """Populate channel groups from probe shank assignments."""
        if self._probe is None:
            return
        shank_groups = self._probe.get_shank_groups()
        # Build list of channel lists in sorted shank order, filtered to valid channels
        groups = [
            [ch for ch in chs if ch < self._num_channels]
            for chs in shank_groups.values()
        ]
        groups = [g for g in groups if g]  # drop empty groups
        if not groups:
            return
        self._group_widget.reset()
        self._group_widget.set_channel_groups(groups)
        self._enable_ok(self._group_widget.all_assigned())

    def _on_assignment_changed(self):
        """Handle channel assignment change in group widget."""
        filter_type = self._type_combo.currentData()
        if filter_type in (FilterType.CAR, FilterType.CMR):
            self._enable_ok(self._group_widget.all_assigned())

    def _enable_ok(self, enabled: bool):
        """Enable or disable the OK button."""
        ok_btn = self._button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn:
            ok_btn.setEnabled(enabled)

    def _load_config(self, config: FilterConfig):
        """Load values from existing config."""
        # Set type
        for i in range(self._type_combo.count()):
            if self._type_combo.itemData(i) == config.filter_type:
                self._type_combo.setCurrentIndex(i)
                break

        self._order_spin.setValue(config.order)

        if config.cutoff_low is not None:
            self._cutoff_low_spin.setValue(config.cutoff_low)
        if config.cutoff_high is not None:
            self._cutoff_high_spin.setValue(config.cutoff_high)
        if config.notch_freq is not None:
            self._notch_freq_spin.setValue(config.notch_freq)
        self._notch_q_spin.setValue(config.notch_q)
        self._vrms_mult_spin.setValue(config.vrms_multiplier)

        if config.channel_groups and config.filter_type in (
            FilterType.CAR,
            FilterType.CMR,
        ):
            self._group_widget.set_channel_groups(config.channel_groups)

    def get_config(self) -> FilterConfig:
        """Get the configured filter."""
        filter_type = self._type_combo.currentData()

        cutoff_low = None
        cutoff_high = None
        notch_freq = None
        channel_groups = None
        vrms_multiplier = 3.0

        if filter_type == FilterType.LOWPASS:
            cutoff_high = self._cutoff_high_spin.value()
        elif filter_type == FilterType.HIGHPASS:
            cutoff_low = self._cutoff_low_spin.value()
        elif filter_type == FilterType.BANDPASS:
            cutoff_low = self._cutoff_low_spin.value()
            cutoff_high = self._cutoff_high_spin.value()
        elif filter_type == FilterType.NOTCH:
            notch_freq = self._notch_freq_spin.value()
        elif filter_type in (FilterType.CAR, FilterType.CMR):
            channel_groups = self._group_widget.get_channel_groups()
        elif filter_type == FilterType.VRMS_THRESHOLD:
            vrms_multiplier = self._vrms_mult_spin.value()

        # Preserve UID if editing
        uid = self._config.uid if self._config else None

        config = FilterConfig(
            filter_type=filter_type,
            order=self._order_spin.value(),
            cutoff_low=cutoff_low,
            cutoff_high=cutoff_high,
            notch_freq=notch_freq,
            notch_q=self._notch_q_spin.value(),
            channel_groups=channel_groups,
            vrms_multiplier=vrms_multiplier,
        )

        if uid:
            config.uid = uid

        return config


class FilterPanel(QWidget):
    """Panel for managing the filter chain."""

    # Signals
    filters_changed = Signal()
    filter_bypass_changed = Signal(str, bool)
    global_bypass_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._state: Optional[StreamState] = None
        self._probe: Optional[ProbeGeometry] = None

    def set_probe(self, probe: Optional[ProbeGeometry]):
        """Store probe geometry so it can be passed to filter edit dialogs."""
        self._probe = probe

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Header with global bypass
        header = QHBoxLayout()
        header.addWidget(QLabel("<b>Filter Chain</b>"))
        header.addStretch()
        self._global_bypass_check = QCheckBox("Bypass All")
        self._global_bypass_check.stateChanged.connect(self._on_global_bypass_changed)
        header.addWidget(self._global_bypass_check)
        layout.addLayout(header)

        # Filter list
        self._filter_list = QListWidget()
        self._filter_list.setMaximumHeight(150)
        self._filter_list.itemDoubleClicked.connect(self._on_edit_filter)
        layout.addWidget(self._filter_list)

        # Buttons
        btn_layout = QHBoxLayout()
        self._add_btn = QPushButton("Add")
        self._add_btn.clicked.connect(self._on_add_filter)
        btn_layout.addWidget(self._add_btn)
        self._edit_btn = QPushButton("Edit")
        self._edit_btn.clicked.connect(self._on_edit_selected)
        btn_layout.addWidget(self._edit_btn)
        self._remove_btn = QPushButton("Remove")
        self._remove_btn.clicked.connect(self._on_remove_filter)
        btn_layout.addWidget(self._remove_btn)
        layout.addLayout(btn_layout)

        # Reorder buttons
        order_layout = QHBoxLayout()
        self._up_btn = QPushButton("Up")
        self._up_btn.clicked.connect(self._on_move_up)
        order_layout.addWidget(self._up_btn)
        self._down_btn = QPushButton("Down")
        self._down_btn.clicked.connect(self._on_move_down)
        order_layout.addWidget(self._down_btn)
        layout.addLayout(order_layout)

        # Per-filter bypass
        self._bypass_btn = QPushButton("Toggle Bypass")
        self._bypass_btn.clicked.connect(self._on_toggle_bypass)
        layout.addWidget(self._bypass_btn)

        layout.addStretch()

    def set_state(self, state: StreamState):
        self._state = state
        self._global_bypass_check.setChecked(state.global_bypass)
        self._update_list()

    def _update_list(self):
        self._filter_list.clear()
        if not self._state:
            return
        for filt in self._state.filters:
            text = filt.get_display_name()
            if filt.bypassed:
                text = f"[BYPASS] {text}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, filt.uid)
            if filt.bypassed:
                item.setForeground(Qt.GlobalColor.gray)
            self._filter_list.addItem(item)

    def _on_add_filter(self):
        if not self._state:
            return
        dialog = FilterEditDialog(
            self,
            sample_rate=self._state.sample_rate,
            num_channels=self._state.num_channels,
            probe=self._probe,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            config = dialog.get_config()
            self._state.add_filter(config)
            self._update_list()
            self.filters_changed.emit()

    def _on_edit_selected(self):
        item = self._filter_list.currentItem()
        if item:
            self._on_edit_filter(item)

    def _on_edit_filter(self, item: QListWidgetItem):
        if not self._state:
            return
        uid = item.data(Qt.ItemDataRole.UserRole)
        config = None
        for f in self._state.filters:
            if f.uid == uid:
                config = f
                break
        if config:
            dialog = FilterEditDialog(
                self,
                filter_config=config,
                sample_rate=self._state.sample_rate,
                num_channels=self._state.num_channels,
                probe=self._probe,
            )
            if dialog.exec() == QDialog.DialogCode.Accepted:
                new_config = dialog.get_config()
                for i, f in enumerate(self._state.filters):
                    if f.uid == uid:
                        new_config.bypassed = f.bypassed
                        new_config.uid = f.uid
                        self._state.filters[i] = new_config
                        break
                self._update_list()
                self.filters_changed.emit()

    def _on_remove_filter(self):
        if not self._state:
            return
        item = self._filter_list.currentItem()
        if item:
            uid = item.data(Qt.ItemDataRole.UserRole)
            self._state.remove_filter(uid)
            self._update_list()
            self.filters_changed.emit()

    def _on_move_up(self):
        if not self._state:
            return
        row = self._filter_list.currentRow()
        if row > 0:
            self._state.move_filter(row, row - 1)
            self._update_list()
            self._filter_list.setCurrentRow(row - 1)
            self.filters_changed.emit()

    def _on_move_down(self):
        if not self._state:
            return
        row = self._filter_list.currentRow()
        if row >= 0 and row < len(self._state.filters) - 1:
            self._state.move_filter(row, row + 1)
            self._update_list()
            self._filter_list.setCurrentRow(row + 1)
            self.filters_changed.emit()

    def _on_toggle_bypass(self):
        if not self._state:
            return
        item = self._filter_list.currentItem()
        if item:
            uid = item.data(Qt.ItemDataRole.UserRole)
            for f in self._state.filters:
                if f.uid == uid:
                    f.bypassed = not f.bypassed
                    self._update_list()
                    self.filter_bypass_changed.emit(uid, f.bypassed)
                    self.filters_changed.emit()
                    break

    def _on_global_bypass_changed(self, state: int):
        bypassed = state == Qt.CheckState.Checked.value
        if self._state:
            self._state.global_bypass = bypassed
        self.global_bypass_changed.emit(bypassed)
        self.filters_changed.emit()

    def clear(self):
        self._state = None
        self._filter_list.clear()
        self._global_bypass_check.setChecked(False)
