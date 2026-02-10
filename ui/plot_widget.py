"""Time series plot widget using pyqtgraph."""
from typing import List, Optional, Dict, Tuple
import numpy as np

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtGui import QColor

import pyqtgraph as pg

# Configure pyqtgraph for performance
pg.setConfigOptions(
    antialias=False,  # Faster rendering
    useOpenGL=False,  # More compatible
    enableExperimental=False,
)


# Color palette for multi-channel overlay
CHANNEL_COLORS = [
    "#1f77b4",  # Blue
    "#ff7f0e",  # Orange
    "#2ca02c",  # Green
    "#d62728",  # Red
    "#9467bd",  # Purple
    "#8c564b",  # Brown
    "#e377c2",  # Pink
    "#7f7f7f",  # Gray
]


class TimeSeriesPlot(QWidget):
    """
    High-performance time series plot widget.

    Features:
    - Multi-channel overlay with distinct colors
    - Mouse wheel zoom
    - Pan with drag
    - Double-click to reset
    - Region selection for FFT
    """

    # Signals
    view_range_changed = Signal(float, float)  # start, end in seconds
    region_selected = Signal(float, float)  # start, end for FFT selection

    def __init__(self, parent=None):
        super().__init__(parent)

        self._setup_ui()
        self._setup_plot()

        # Data state
        self._plot_items: Dict[int, pg.PlotDataItem] = {}  # channel -> plot item
        self._current_data: Optional[np.ndarray] = None
        self._current_time: Optional[np.ndarray] = None
        self._channel_indices: List[int] = []

        # Scatter mode
        self._scatter_mode: bool = False

        # Selection region
        self._selection_region: Optional[pg.LinearRegionItem] = None
        self._selection_enabled = False

    def _setup_ui(self):
        """Set up the widget layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create graphics layout widget
        self._graphics_widget = pg.GraphicsLayoutWidget()
        self._graphics_widget.setBackground("w")
        layout.addWidget(self._graphics_widget)

    def _setup_plot(self):
        """Set up the plot axes."""
        self._plot = self._graphics_widget.addPlot(row=0, col=0)
        self._plot.setLabel("bottom", "Time", units="s")
        self._plot.setLabel("left", "Amplitude")
        self._plot.showGrid(x=True, y=True, alpha=0.3)

        # Enable mouse interaction
        self._plot.setMouseEnabled(x=True, y=True)
        self._plot.enableAutoRange(axis="y", enable=True)

        # Connect signals
        self._plot.sigRangeChanged.connect(self._on_range_changed)

        # Set up view box for custom interactions
        vb = self._plot.getViewBox()
        vb.setMouseMode(pg.ViewBox.RectMode)

    def _on_range_changed(self, view_box, ranges):
        """Handle view range changes."""
        x_range = ranges[0]
        self.view_range_changed.emit(x_range[0], x_range[1])

    def set_data(
        self,
        data: np.ndarray,
        time_axis: np.ndarray,
        channel_indices: List[int],
    ):
        """
        Set data to display.

        Args:
            data: Shape (n_channels, n_samples) or (n_samples,)
            time_axis: Time values in seconds
            channel_indices: Original channel indices for labeling
        """
        self._current_data = data
        self._current_time = time_axis
        self._channel_indices = channel_indices

        # Clear existing plots
        for item in self._plot_items.values():
            self._plot.removeItem(item)
        self._plot_items.clear()

        if data is None or time_axis is None:
            return

        # Ensure 2D
        if data.ndim == 1:
            data = data.reshape(1, -1)

        # Plot each channel
        for i, ch_idx in enumerate(channel_indices):
            if i >= data.shape[0]:
                break

            color = QColor(CHANNEL_COLORS[i % len(CHANNEL_COLORS)])

            if self._scatter_mode:
                plot_item = self._plot.plot(
                    time_axis,
                    data[i],
                    pen=None,
                    symbol="o",
                    symbolSize=2,
                    symbolBrush=pg.mkBrush(color),
                    symbolPen=None,
                    name=f"Ch {ch_idx}",
                )
            else:
                pen = pg.mkPen(color=color, width=1)
                plot_item = self._plot.plot(
                    time_axis,
                    data[i],
                    pen=pen,
                    name=f"Ch {ch_idx}",
                )
            self._plot_items[ch_idx] = plot_item

        # Auto-range Y axis
        self._plot.enableAutoRange(axis="y", enable=True)

    def update_data(self, data: np.ndarray, time_axis: np.ndarray):
        """
        Update data without recreating plot items (faster for filtering).

        Args:
            data: Same shape as previous set_data call
            time_axis: Time values
        """
        if data is None:
            return

        if data.ndim == 1:
            data = data.reshape(1, -1)

        for i, ch_idx in enumerate(self._channel_indices):
            if ch_idx in self._plot_items and i < data.shape[0]:
                self._plot_items[ch_idx].setData(time_axis, data[i])

    def set_scatter_mode(self, enabled: bool):
        """
        Enable or disable scatter/dot rendering mode.

        Args:
            enabled: True for scatter dots, False for lines
        """
        if self._scatter_mode == enabled:
            return
        self._scatter_mode = enabled
        # Re-render with current data if available
        if self._current_data is not None and self._current_time is not None:
            self.set_data(self._current_data, self._current_time, self._channel_indices)

    def set_view_range(self, start: float, end: float):
        """Set the visible time range."""
        self._plot.setXRange(start, end, padding=0)

    def get_view_range(self) -> Tuple[float, float]:
        """Get current visible time range."""
        x_range = self._plot.viewRange()[0]
        return (x_range[0], x_range[1])

    def reset_view(self):
        """Reset to full data range."""
        if self._current_time is not None and len(self._current_time) > 0:
            self._plot.setXRange(
                self._current_time[0],
                self._current_time[-1],
                padding=0.02,
            )
        self._plot.enableAutoRange(axis="y", enable=True)

    def enable_selection(self, enabled: bool = True):
        """Enable or disable region selection for FFT."""
        self._selection_enabled = enabled

        if enabled:
            if self._selection_region is None:
                # Create selection region
                if self._current_time is not None and len(self._current_time) > 1:
                    t_start = self._current_time[0]
                    t_end = self._current_time[-1]
                    mid = (t_start + t_end) / 2
                    span = (t_end - t_start) * 0.1

                    self._selection_region = pg.LinearRegionItem(
                        values=[mid - span / 2, mid + span / 2],
                        brush=pg.mkBrush(100, 100, 255, 50),
                    )
                    self._selection_region.sigRegionChangeFinished.connect(
                        self._on_region_changed
                    )
                    self._plot.addItem(self._selection_region)
        else:
            if self._selection_region is not None:
                self._plot.removeItem(self._selection_region)
                self._selection_region = None

    def get_selection_range(self) -> Optional[Tuple[float, float]]:
        """Get current selection range, if any."""
        if self._selection_region is not None:
            region = self._selection_region.getRegion()
            return (region[0], region[1])
        return None

    def set_selection_range(self, start: float, end: float):
        """Set the selection range."""
        if self._selection_region is not None:
            self._selection_region.setRegion([start, end])

    def _on_region_changed(self):
        """Handle selection region change."""
        if self._selection_region is not None:
            region = self._selection_region.getRegion()
            self.region_selected.emit(region[0], region[1])

    def mouseDoubleClickEvent(self, event):
        """Handle double-click to reset view."""
        self.reset_view()
        super().mouseDoubleClickEvent(event)

    def clear(self):
        """Clear all data from the plot."""
        for item in self._plot_items.values():
            self._plot.removeItem(item)
        self._plot_items.clear()
        self._current_data = None
        self._current_time = None
        self._channel_indices = []

        if self._selection_region is not None:
            self._plot.removeItem(self._selection_region)
            self._selection_region = None


class SpectrumPlot(QWidget):
    """
    Spectrum plot widget for FFT/PSD display.

    Features:
    - Linear or log frequency axis
    - Linear or dB magnitude axis
    - Multi-channel overlay
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._setup_ui()
        self._setup_plot()

        self._plot_items: Dict[int, pg.PlotDataItem] = {}
        self._log_freq = False
        self._log_mag = True  # Default to dB scale

    def _setup_ui(self):
        """Set up the widget layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._graphics_widget = pg.GraphicsLayoutWidget()
        self._graphics_widget.setBackground("w")
        layout.addWidget(self._graphics_widget)

    def _setup_plot(self):
        """Set up the plot axes."""
        self._plot = self._graphics_widget.addPlot(row=0, col=0)
        self._plot.setLabel("bottom", "Frequency", units="Hz")
        self._plot.setLabel("left", "Power", units="dB")
        self._plot.showGrid(x=True, y=True, alpha=0.3)
        self._plot.setMouseEnabled(x=True, y=True)

    def set_data(
        self,
        freqs: np.ndarray,
        magnitude: np.ndarray,
        channel_indices: List[int],
        method: str = "psd",
    ):
        """
        Set spectrum data to display.

        Args:
            freqs: Frequency values in Hz
            magnitude: Magnitude values (can be 1D or 2D)
            channel_indices: Channel indices for labeling
            method: 'fft' or 'psd' for appropriate labeling
        """
        # Clear existing
        for item in self._plot_items.values():
            self._plot.removeItem(item)
        self._plot_items.clear()

        if freqs is None or magnitude is None:
            return

        # Ensure 2D
        if magnitude.ndim == 1:
            magnitude = magnitude.reshape(1, -1)

        # Update axis label
        if method == "psd":
            self._plot.setLabel("left", "PSD", units="V²/Hz")
        else:
            self._plot.setLabel("left", "Magnitude")

        # Convert to dB if log magnitude
        if self._log_mag:
            # Avoid log(0)
            magnitude = 10 * np.log10(np.maximum(magnitude, 1e-20))
            if method == "psd":
                self._plot.setLabel("left", "PSD", units="dB/Hz")
            else:
                self._plot.setLabel("left", "Magnitude", units="dB")

        # Plot each channel
        for i, ch_idx in enumerate(channel_indices):
            if i >= magnitude.shape[0]:
                break

            color = QColor(CHANNEL_COLORS[i % len(CHANNEL_COLORS)])
            pen = pg.mkPen(color=color, width=1)

            if self._log_freq:
                # Filter out zero/negative frequencies for log scale
                mask = freqs > 0
                plot_freqs = freqs[mask]
                plot_mag = magnitude[i, mask]
            else:
                plot_freqs = freqs
                plot_mag = magnitude[i]

            plot_item = self._plot.plot(
                plot_freqs,
                plot_mag,
                pen=pen,
                name=f"Ch {ch_idx}",
            )
            self._plot_items[ch_idx] = plot_item

        # Set log scale if enabled
        self._plot.setLogMode(x=self._log_freq, y=False)

        # Auto-range
        self._plot.enableAutoRange()

    def set_log_frequency(self, enabled: bool):
        """Enable or disable log frequency axis."""
        self._log_freq = enabled
        self._plot.setLogMode(x=enabled, y=False)

    def set_log_magnitude(self, enabled: bool):
        """Enable or disable dB magnitude scale."""
        self._log_mag = enabled
        # Would need to re-plot data to apply this change

    def clear(self):
        """Clear all data from the plot."""
        for item in self._plot_items.values():
            self._plot.removeItem(item)
        self._plot_items.clear()
