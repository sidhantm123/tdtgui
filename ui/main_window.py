"""Main application window."""
import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Slot, QTimer
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QTabWidget,
    QStatusBar,
    QMenuBar,
    QMenu,
    QFileDialog,
    QMessageBox,
    QProgressDialog,
    QLabel,
    QApplication,
)
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent

import numpy as np

from core.app_state import AppState
from core.workers import (
    WorkerManager,
    DataLoadWorker,
    FilterWorker,
    SpectralWorker,
)
from models import StreamState, ChannelMode
from tdt_io import TDTReader, TDTBlock
from dsp import apply_filter_chain, decimate_for_display
from models.filter_config import FilterType

from .stream_panel import StreamPanel
from .control_panel import ControlPanel
from .filter_panel import FilterPanel
from .spectrum_panel import SpectrumPanel
from .plot_widget import TimeSeriesPlot, SpectrumPlot


class MainWindow(QMainWindow):
    """Main application window."""

    # Maximum points to plot without decimation
    MAX_PLOT_POINTS = 8000

    def __init__(self):
        super().__init__()

        self.setWindowTitle("TDT Multi-Channel Viewer")
        self.setMinimumSize(1200, 800)

        # State
        self._app_state = AppState()
        self._worker_manager = WorkerManager()

        # Current data cache
        self._raw_data: Optional[np.ndarray] = None
        self._raw_time: Optional[np.ndarray] = None
        self._raw_data_all: Optional[np.ndarray] = None  # All channels for CAR/CMR
        self._filtered_data: Optional[np.ndarray] = None

        # Fast-path tracking
        self._last_plot_channels: list = []
        self._last_scatter_mode: bool = False

        # Pending operations
        self._pending_refresh = False

        self._setup_ui()
        self._setup_menu()
        self._setup_statusbar()
        self._connect_signals()

        # Enable drag and drop
        self.setAcceptDrops(True)

    def _setup_ui(self):
        """Set up the main UI layout."""
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # Main splitter
        self._main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel: Stream list
        self._stream_panel = StreamPanel()
        self._stream_panel.setMaximumWidth(250)
        self._stream_panel.setMinimumWidth(150)
        self._main_splitter.addWidget(self._stream_panel)

        # Center: Plots
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)

        # Tab widget for Time Series / Spectrum
        self._plot_tabs = QTabWidget()

        # Time series tab
        self._time_plot = TimeSeriesPlot()
        self._plot_tabs.addTab(self._time_plot, "Time Series")

        # Spectrum tab
        self._spectrum_plot = SpectrumPlot()
        self._plot_tabs.addTab(self._spectrum_plot, "Spectrum")

        center_layout.addWidget(self._plot_tabs)
        self._main_splitter.addWidget(center_widget)

        # Right panel: Controls
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Right tabs for different control groups
        self._control_tabs = QTabWidget()

        # Channel control tab
        self._control_panel = ControlPanel()
        self._control_tabs.addTab(self._control_panel, "Channels")

        # Filter tab
        self._filter_panel = FilterPanel()
        self._control_tabs.addTab(self._filter_panel, "Filters")

        # Spectrum analysis tab
        self._spectrum_panel = SpectrumPanel()
        self._control_tabs.addTab(self._spectrum_panel, "Analysis")

        right_layout.addWidget(self._control_tabs)

        right_widget.setMaximumWidth(300)
        right_widget.setMinimumWidth(200)
        self._main_splitter.addWidget(right_widget)

        # Set splitter sizes
        self._main_splitter.setSizes([200, 700, 280])

        main_layout.addWidget(self._main_splitter)

    def _setup_menu(self):
        """Set up the menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")

        open_action = QAction("Open TDT Block...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._on_open_folder)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        save_session = QAction("Save Session...", self)
        save_session.setShortcut("Ctrl+S")
        save_session.triggered.connect(self._on_save_session)
        file_menu.addAction(save_session)

        load_session = QAction("Load Session...", self)
        load_session.setShortcut("Ctrl+L")
        load_session.triggered.connect(self._on_load_session)
        file_menu.addAction(load_session)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View menu
        view_menu = menubar.addMenu("View")

        reset_view = QAction("Reset View", self)
        reset_view.setShortcut("Ctrl+R")
        reset_view.triggered.connect(lambda: self._time_plot.reset_view())
        view_menu.addAction(reset_view)

        # Help menu
        help_menu = menubar.addMenu("Help")

        about_action = QAction("About", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _setup_statusbar(self):
        """Set up the status bar."""
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)

        self._status_label = QLabel("Ready - Open a TDT block folder to begin")
        self._statusbar.addWidget(self._status_label, 1)

        self._filter_indicator = QLabel("")
        self._statusbar.addPermanentWidget(self._filter_indicator)

    def _connect_signals(self):
        """Connect all signals."""
        # Stream panel
        self._stream_panel.stream_selected.connect(self._on_stream_selected)

        # Control panel
        self._control_panel.channel_mode_changed.connect(self._on_channel_mode_changed)
        self._control_panel.single_channel_changed.connect(self._on_channel_changed)
        self._control_panel.overlay_channels_changed.connect(self._on_channels_changed)
        self._control_panel.view_range_requested.connect(self._on_view_range_requested)
        self._control_panel.refresh_requested.connect(self._refresh_plot)

        # Scatter mode
        self._control_panel.scatter_mode_changed.connect(self._on_scatter_mode_changed)

        # Filter panel
        self._filter_panel.filters_changed.connect(self._on_filters_changed)

        # Spectrum panel
        self._spectrum_panel.analyze_requested.connect(self._on_analyze_requested)
        self._spectrum_panel.enable_selection_changed.connect(
            self._time_plot.enable_selection
        )

        # Plot signals
        self._time_plot.view_range_changed.connect(self._on_plot_view_changed)
        self._time_plot.region_selected.connect(self._spectrum_panel.update_interval)

    def _on_open_folder(self):
        """Handle open folder action."""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select TDT Block Folder",
            "",
            QFileDialog.Option.ShowDirsOnly,
        )

        if folder:
            self._load_block(folder)

    def _load_block(self, folder_path: str):
        """Load a TDT block from folder."""
        # Show progress
        progress = QProgressDialog("Loading TDT block...", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()
        QApplication.processEvents()

        try:
            block = self._app_state.load_block(folder_path)

            # Update UI
            self._stream_panel.set_block(block)

            # Select first stream
            if block.streams:
                first_stream = list(block.streams.keys())[0]
                self._on_stream_selected(first_stream)

            self._update_status()

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error Loading Block",
                f"Failed to load TDT block:\n\n{e}\n\n"
                "Ensure the folder contains valid TDT recording files "
                "(.tdx, .tev, .tsq, etc.)",
            )

        finally:
            progress.close()

    @Slot(str)
    def _on_stream_selected(self, stream_name: str):
        """Handle stream selection."""
        self._app_state.select_stream(stream_name)
        state = self._app_state.get_current_state()

        if state:
            # Reset tracking state for new stream
            self._last_plot_channels = []
            self._last_scatter_mode = False
            self._raw_data_all = None

            # Restore scatter mode from stream state
            self._time_plot.set_scatter_mode(state.scatter_mode)

            # Update control panels
            self._control_panel.set_state(state)
            self._filter_panel.set_state(state)
            self._spectrum_panel.set_state(state)

            # Load and display data
            self._refresh_plot()

            self._update_status()

    @Slot(ChannelMode)
    def _on_channel_mode_changed(self, mode: ChannelMode):
        """Handle channel mode change."""
        self._refresh_plot()

    @Slot(int)
    def _on_channel_changed(self, channel: int):
        """Handle single channel selection change."""
        self._refresh_plot()

    @Slot(list)
    def _on_channels_changed(self, channels: list):
        """Handle overlay channels change."""
        self._refresh_plot()

    @Slot(float, float)
    def _on_view_range_requested(self, start: float, end: float):
        """Handle view range change request."""
        self._time_plot.set_view_range(start, end)
        self._refresh_plot()

    @Slot(object, object)
    def _on_plot_view_changed(self, start: float, end: float):
        """Handle plot view range change (from user interaction)."""
        state = self._app_state.get_current_state()
        if state:
            state.set_view_range(start, end)
            self._control_panel.update_view_range(start, end)

            # Debounced refresh for smooth zooming
            if not self._pending_refresh:
                self._pending_refresh = True
                QTimer.singleShot(100, self._delayed_refresh)

    def _delayed_refresh(self):
        """Delayed refresh after view change."""
        self._pending_refresh = False
        self._refresh_plot()

    @Slot()
    def _on_filters_changed(self):
        """Handle filter chain change."""
        self._apply_filters()
        self._update_status()

    @Slot(bool)
    def _on_scatter_mode_changed(self, enabled: bool):
        """Handle scatter mode toggle."""
        state = self._app_state.get_current_state()
        if state:
            state.scatter_mode = enabled
        # Force full re-render since plot items change
        self._last_scatter_mode = not enabled  # Invalidate fast path
        self._apply_filters()

    @Slot(dict)
    def _on_analyze_requested(self, params: dict):
        """Handle spectrum analysis request."""
        state = self._app_state.get_current_state()
        if not state or self._app_state.block is None:
            return

        # Show progress
        progress = QProgressDialog("Computing spectrum...", "Cancel", 0, 100, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()

        try:
            # Load data for analysis interval
            data, time_axis = self._app_state.reader.get_stream_data(
                state.stream_name,
                channels=params["channels"],
                start_time=params["start"],
                end_time=params["end"],
            )

            # Apply filters if any
            if state.filters and not state.global_bypass:
                data, _, _ = apply_filter_chain(
                    data, state.filters, state.sample_rate, state.global_bypass
                )

            progress.setValue(50)

            # Compute spectrum
            worker = SpectralWorker(
                data,
                state.sample_rate,
                method=params["method"],
                channels=list(range(data.shape[0])) if data.ndim > 1 else [0],
                nperseg=params["nperseg"],
                overlap=params["overlap"],
            )

            # Run synchronously for simplicity
            if params["method"] == "fft":
                from dsp import compute_fft
                freqs, magnitude = compute_fft(data, state.sample_rate)
            else:
                from dsp import compute_psd
                freqs, magnitude = compute_psd(
                    data,
                    state.sample_rate,
                    nperseg=params["nperseg"],
                    overlap=params["overlap"],
                )

            progress.setValue(100)

            # Display result
            self._spectrum_plot.set_data(
                freqs,
                magnitude,
                params["channels"],
                method=params["method"],
            )

            # Switch to spectrum tab
            self._plot_tabs.setCurrentIndex(1)

        except Exception as e:
            QMessageBox.warning(
                self,
                "Analysis Error",
                f"Failed to compute spectrum:\n\n{e}",
            )

        finally:
            progress.close()

    def _refresh_plot(self):
        """Refresh the time series plot."""
        state = self._app_state.get_current_state()
        if not state or self._app_state.block is None:
            return

        # Get view range
        start, end = state.get_view_range()
        channels = state.get_active_channels()

        try:
            # Load data for displayed channels
            data, time_axis = self._app_state.reader.get_stream_data(
                state.stream_name,
                channels=channels,
                start_time=start,
                end_time=end,
            )

            self._raw_data = data
            self._raw_time = time_axis

            # Check if any active filter needs all channels (CAR/CMR)
            needs_all = any(
                f.filter_type in (FilterType.CAR, FilterType.CMR) and not f.bypassed
                for f in state.filters
            ) and not state.global_bypass

            if needs_all:
                # Load ALL channels for re-referencing
                all_channels = list(range(state.num_channels))
                all_data, _ = self._app_state.reader.get_stream_data(
                    state.stream_name,
                    channels=all_channels,
                    start_time=start,
                    end_time=end,
                )
                self._raw_data_all = all_data
            else:
                self._raw_data_all = None

            # Apply filters
            self._apply_filters()

        except Exception as e:
            self._status_label.setText(f"Error loading data: {e}")

    def _apply_filters(self):
        """Apply filter chain and update plot."""
        state = self._app_state.get_current_state()
        if state is None or self._raw_data is None:
            return

        data = self._raw_data
        time_axis = self._raw_time
        channels = state.get_active_channels()

        # Apply filter chain (always returns 3-tuple)
        data, warnings, vrms_dict = apply_filter_chain(
            data,
            state.filters,
            state.sample_rate,
            state.global_bypass,
            all_channel_data=self._raw_data_all,
            channel_indices=channels,
        )
        if warnings:
            self._status_label.setText(f"Filter warning: {warnings[0]}")

        self._filtered_data = data

        # Update Vrms display
        state.vrms_values = vrms_dict
        self._control_panel.update_vrms(vrms_dict)

        # Decimate for display if needed
        if data.ndim == 1:
            n_samples = len(data)
        else:
            n_samples = data.shape[1] if data.ndim > 1 else len(data)

        if n_samples > self.MAX_PLOT_POINTS:
            plot_data, plot_time = decimate_for_display(
                data, time_axis, target_points=self.MAX_PLOT_POINTS
            )
        else:
            plot_data = data
            plot_time = time_axis

        # Fast path: reuse existing plot items if channels and scatter mode unchanged
        scatter = state.scatter_mode
        if channels == self._last_plot_channels and scatter == self._last_scatter_mode:
            self._time_plot.update_data(plot_data, plot_time)
        else:
            self._time_plot.set_scatter_mode(scatter)
            self._time_plot.set_data(plot_data, plot_time, channels)
            self._last_plot_channels = channels
            self._last_scatter_mode = scatter

        # Update filter indicator
        if state.filters:
            if state.global_bypass:
                self._filter_indicator.setText("Filters: BYPASSED")
            else:
                active = sum(1 for f in state.filters if not f.bypassed)
                self._filter_indicator.setText(f"Filters: {active} active")
        else:
            self._filter_indicator.setText("")

    def _update_status(self):
        """Update status bar."""
        state = self._app_state.get_current_state()
        block = self._app_state.block

        if block and state:
            duration_str = f"{state.duration:.1f}s"
            if state.duration >= 60:
                mins = int(state.duration // 60)
                secs = state.duration % 60
                duration_str = f"{mins}m {secs:.1f}s"

            self._status_label.setText(
                f"Block: {block.name} | "
                f"Stream: {state.stream_name} | "
                f"{state.num_channels} ch @ {state.sample_rate:.0f} Hz | "
                f"Duration: {duration_str}"
            )
        else:
            self._status_label.setText("Ready - Open a TDT block folder to begin")

    def _on_save_session(self):
        """Save current session to file."""
        if self._app_state.block is None:
            QMessageBox.information(
                self, "No Data", "No TDT block is currently loaded."
            )
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Save Session",
            "",
            "JSON Files (*.json)",
        )

        if filepath:
            try:
                self._app_state.save_session(filepath)
                self._status_label.setText(f"Session saved to {filepath}")
            except Exception as e:
                QMessageBox.warning(
                    self, "Save Error", f"Failed to save session:\n\n{e}"
                )

    def _on_load_session(self):
        """Load session from file."""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Load Session",
            "",
            "JSON Files (*.json)",
        )

        if filepath:
            try:
                self._app_state.load_session(filepath)

                # Update UI
                block = self._app_state.block
                if block:
                    self._stream_panel.set_block(block)

                    if self._app_state.current_stream:
                        self._stream_panel.select_stream(self._app_state.current_stream)
                        self._on_stream_selected(self._app_state.current_stream)

                self._status_label.setText(f"Session loaded from {filepath}")

            except Exception as e:
                QMessageBox.warning(
                    self, "Load Error", f"Failed to load session:\n\n{e}"
                )

    def _on_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About TDT Viewer",
            "<h3>TDT Multi-Channel Viewer</h3>"
            "<p>Version 1.0.0</p>"
            "<p>A cross-platform application for viewing and analyzing "
            "Tucker-Davis Technologies neural recording data.</p>"
            "<p>Features:</p>"
            "<ul>"
            "<li>Multi-channel time series visualization</li>"
            "<li>Configurable filter chains</li>"
            "<li>FFT and PSD analysis</li>"
            "<li>Session save/load</li>"
            "</ul>",
        )

    # Drag and drop support
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter."""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and urls[0].isLocalFile():
                path = urls[0].toLocalFile()
                if os.path.isdir(path):
                    event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        """Handle drop."""
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if os.path.isdir(path):
                self._load_block(path)

    def closeEvent(self, event):
        """Handle window close."""
        # Cancel any running workers
        self._worker_manager.cancel_all()
        self._app_state.close()
        event.accept()
