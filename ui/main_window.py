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

        # Current data cache (raw + filtered buffers, wider than the visible view)
        self._raw_data: Optional[np.ndarray] = None
        self._raw_time: Optional[np.ndarray] = None
        self._raw_data_all: Optional[np.ndarray] = None  # All channels for CAR/CMR
        self._filtered_data: Optional[np.ndarray] = None

        # Buffer tracking — describes what time range / channels are in _filtered_data
        self._buffer_channels: list = []
        self._buffer_start: float = -1.0
        self._buffer_end: float = -1.0

        # Async load context — carried from _refresh_plot to _on_data_loaded_async
        self._load_seq: int = 0          # incremented on each new request to discard stale results
        self._pending_channels: list = []
        self._pending_buffer_start: float = 0.0
        self._pending_buffer_end: float = 0.0
        self._pending_needs_all: bool = False

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

        export_menu = file_menu.addMenu("Export")

        export_binary_action = QAction("Stream as Binary (.i16 / .bin)...", self)
        export_binary_action.triggered.connect(self._on_export_binary)
        export_menu.addAction(export_binary_action)

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
            # Invalidate the data buffer so we don't show stale data
            self._filtered_data = None
            self._raw_data = None
            self._raw_time = None
            self._buffer_channels = []
            self._buffer_start = -1.0
            self._buffer_end = -1.0

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
        """Refresh the time series plot, using the in-memory buffer when possible."""
        state = self._app_state.get_current_state()
        if not state or self._app_state.block is None:
            return

        start, end = state.get_view_range()
        channels = state.get_active_channels()

        # ── Buffer fast path ────────────────────────────────────────────────
        # If the current view fits inside already-loaded + filtered data, just
        # re-slice and re-decimate — no disk I/O at all (~5 ms).
        if (
            self._filtered_data is not None
            and self._raw_time is not None
            and channels == self._buffer_channels
            and start >= self._buffer_start
            and end <= self._buffer_end
        ):
            self._apply_filters()  # re-filter in case filter settings changed
            return

        # ── Buffer miss: async disk load ────────────────────────────────────
        # Load 1× the view duration as margin on each side so the next few
        # pan/zoom steps will hit the buffer without touching the disk.
        view_dur = max(end - start, 1.0)
        buf_start = max(0.0, start - view_dur)
        buf_end = min(state.duration, end + view_dur)

        needs_all = any(
            f.filter_type in (FilterType.CAR, FilterType.CMR) and not f.bypassed
            for f in state.filters
        ) and not state.global_bypass

        # When CAR/CMR is active we must load all channels for referencing
        load_channels = list(range(state.num_channels)) if needs_all else channels

        # Cancel any in-flight load; bump sequence so stale results are dropped
        self._worker_manager.cancel_all()
        self._load_seq += 1
        seq = self._load_seq

        # Store context for _on_data_loaded_async
        self._pending_channels = channels
        self._pending_buffer_start = buf_start
        self._pending_buffer_end = buf_end
        self._pending_needs_all = needs_all

        worker = DataLoadWorker(
            self._app_state.reader,
            state.stream_name,
            load_channels,
            buf_start,
            buf_end,
        )
        worker.signals.result.connect(
            lambda result, s=seq: self._on_data_loaded_async(result, s)
        )
        worker.signals.error.connect(
            lambda err: self._status_label.setText(f"Error loading data: {err}")
        )
        self._worker_manager.submit(worker)

    @Slot(object)
    def _on_data_loaded_async(self, result: dict, seq: int):
        """Receive async load result; discard stale results from cancelled workers."""
        if seq != self._load_seq:
            return  # A newer request was already issued — ignore this one

        state = self._app_state.get_current_state()
        if state is None:
            return

        data = result["data"]
        time_axis = result["time"]
        channels = self._pending_channels

        if self._pending_needs_all:
            # data contains ALL channels; split into display subset and full ref
            self._raw_data_all = data
            self._raw_data = data[channels, :] if len(channels) < data.shape[0] else data
        else:
            self._raw_data = data
            self._raw_data_all = None

        self._raw_time = time_axis

        # Record the buffer extent so future view changes can use the fast path
        self._buffer_start = self._pending_buffer_start
        self._buffer_end = self._pending_buffer_end
        self._buffer_channels = channels

        # Apply filters and render
        self._apply_filters()

    def _rerender_from_buffer(self, start: float, end: float, state):
        """
        Slice the in-memory filtered buffer to [start, end] and render.
        Uses binary search (O(log n)) — no boolean mask, no copy for the slice.
        Typically ≤ 5 ms for a 30-second buffer at 24 kHz.
        """
        if self._filtered_data is None or self._raw_time is None:
            return

        time = self._raw_time
        data = self._filtered_data

        # Binary search is faster than a boolean mask for sorted time arrays
        i0 = max(0, int(np.searchsorted(time, start, side="left")))
        i1 = min(len(time), int(np.searchsorted(time, end, side="right")))
        if i1 <= i0:
            return

        # Slice — creates a view (no copy) for C-contiguous arrays
        data_view = data[:, i0:i1] if data.ndim > 1 else data[i0:i1]
        time_view = time[i0:i1]

        n = data_view.shape[1] if data_view.ndim > 1 else len(data_view)
        if n > self.MAX_PLOT_POINTS:
            plot_data, plot_time = decimate_for_display(
                data_view, time_view, target_points=self.MAX_PLOT_POINTS
            )
        else:
            plot_data = data_view
            plot_time = time_view

        channels = state.get_active_channels()
        scatter = state.scatter_mode
        if channels == self._last_plot_channels and scatter == self._last_scatter_mode:
            self._time_plot.update_data(plot_data, plot_time)
        else:
            self._time_plot.set_scatter_mode(scatter)
            self._time_plot.set_data(plot_data, plot_time, channels)
            self._last_plot_channels = channels
            self._last_scatter_mode = scatter

    def _apply_filters(self):
        """Apply filter chain to the loaded buffer, then render the current view."""
        state = self._app_state.get_current_state()
        if state is None or self._raw_data is None:
            return

        channels = state.get_active_channels()

        # Apply filter chain to the full buffer (always returns 3-tuple)
        data, warnings, vrms_dict = apply_filter_chain(
            self._raw_data,
            state.filters,
            state.sample_rate,
            state.global_bypass,
            all_channel_data=self._raw_data_all,
            channel_indices=channels,
        )
        if warnings:
            self._status_label.setText(f"Filter warning: {warnings[0]}")

        # Cache the full-resolution filtered buffer
        self._filtered_data = data

        # Update Vrms display
        state.vrms_values = vrms_dict
        self._control_panel.update_vrms(vrms_dict)

        # Render only the visible view window (slice + decimate from buffer)
        view_start, view_end = state.get_view_range()
        self._rerender_from_buffer(view_start, view_end, state)

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

    def _on_export_binary(self):
        """Export the current stream as an int16 binary file (.i16 / .bin)."""
        from datetime import datetime

        state = self._app_state.get_current_state()
        if not state or self._app_state.block is None:
            QMessageBox.information(
                self, "No Data", "No TDT block is currently loaded."
            )
            return

        from .export_binary_dialog import ExportBinaryDialog

        dialog = ExportBinaryDialog(state, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        opts = dialog.get_options()
        channels = opts["channels"]

        if not channels:
            QMessageBox.warning(self, "Export Error", "No channels selected.")
            return

        # Default save path: <block_folder>/<stream_name><ext>
        default_path = str(
            Path(self._app_state.block.path)
            / (state.stream_name + opts["extension"])
        )
        ext = opts["extension"]
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Export Binary File",
            default_path,
            f"Binary Files (*{ext})",
        )
        if not filepath:
            return
        if not filepath.endswith(ext):
            filepath += ext

        progress = QProgressDialog("Preparing export...", "Cancel", 0, 100, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()
        QApplication.processEvents()

        try:
            displayed_channels = state.get_active_channels()
            use_fast_path = (
                opts["range"] == "current_view"
                and channels == displayed_channels
                and self._filtered_data is not None
            )

            if use_fast_path:
                # Reuse already-filtered data that is in memory (no re-load needed)
                data = self._filtered_data
                progress.setValue(60)
            else:
                if opts["range"] == "current_view":
                    t1, t2 = state.get_view_range()
                else:
                    t1, t2 = 0.0, state.duration

                progress.setLabelText("Loading data from disk...")
                QApplication.processEvents()

                # Check if any active filter needs all channels (CAR/CMR)
                needs_all = any(
                    f.filter_type in (FilterType.CAR, FilterType.CMR) and not f.bypassed
                    for f in state.filters
                ) and not state.global_bypass

                raw, _ = self._app_state.reader.get_stream_data(
                    state.stream_name,
                    channels=channels,
                    start_time=t1,
                    end_time=t2,
                )
                progress.setValue(40)

                all_channel_data = None
                if needs_all:
                    progress.setLabelText("Loading all channels for re-referencing...")
                    QApplication.processEvents()
                    all_channel_data, _ = self._app_state.reader.get_stream_data(
                        state.stream_name,
                        channels=list(range(state.num_channels)),
                        start_time=t1,
                        end_time=t2,
                    )

                progress.setLabelText("Applying filter chain...")
                QApplication.processEvents()
                data, _, _ = apply_filter_chain(
                    raw,
                    state.filters,
                    state.sample_rate,
                    state.global_bypass,
                    all_channel_data=all_channel_data,
                    channel_indices=channels,
                )
                progress.setValue(70)

            # Ensure 2D: (n_channels, n_samples)
            if data.ndim == 1:
                data = data.reshape(1, -1)

            progress.setLabelText("Converting to int16 and writing...")
            QApplication.processEvents()

            scaled = data * opts["scale"]
            clipped = np.clip(scaled, -32768, 32767)
            int16_data = clipped.astype(np.int16)

            if opts["layout"] == "interlaced":
                # Transpose so layout is (n_samples, n_channels) then write row-major
                # → ch0_s0, ch1_s0, ..., ch0_s1, ch1_s1, ...
                np.ascontiguousarray(int16_data.T).tofile(filepath)
            else:
                # Channel-sequential: all samples for ch0, then ch1, ...
                int16_data.tofile(filepath)

            progress.setValue(90)

            # Write companion summary text file
            summary_path = str(Path(filepath).with_suffix(".txt"))
            self._write_export_summary(
                summary_path, state, channels, opts, data.shape, datetime.now()
            )

            progress.setValue(100)

            file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
            self._status_label.setText(f"Exported: {filepath}")
            QMessageBox.information(
                self,
                "Export Complete",
                f"Binary file saved:\n{filepath}\n\n"
                f"Summary file:\n{summary_path}\n\n"
                f"File size: {file_size_mb:.1f} MB\n\n"
                f"Sample rate to use when importing: {state.sample_rate:.4f} Hz",
            )

        except Exception as e:
            QMessageBox.warning(
                self, "Export Error", f"Failed to export data:\n\n{e}"
            )
        finally:
            progress.close()

    def _write_export_summary(
        self,
        filepath: str,
        state,
        channels: list,
        opts: dict,
        data_shape: tuple,
        export_time,
    ):
        """Write a companion .txt summary alongside the binary export."""
        n_channels, n_samples = data_shape

        if opts["range"] == "current_view":
            s, e = state.view_start, state.view_end
            time_range_str = f"{s:.4f} – {e:.4f} s  (current view)"
        else:
            time_range_str = f"0 – {state.duration:.4f} s  (full recording)"

        # Describe active filters
        filter_lines = []
        if state.global_bypass:
            filter_lines.append("  (all filters bypassed)")
        elif not state.filters:
            filter_lines.append("  (none)")
        else:
            idx = 1
            for f in state.filters:
                if f.bypassed:
                    continue
                filter_lines.append(f"  {idx}. {f.get_display_name()}")
                idx += 1
            if not filter_lines:
                filter_lines.append("  (all filters bypassed individually)")

        ch_1based = [c + 1 for c in channels]
        layout_desc = (
            "Interlaced  (ch0_s0, ch1_s0, ..., ch0_s1, ch1_s1, ...)"
            if opts["layout"] == "interlaced"
            else "Channel-sequential  (all samples ch0, then ch1, ...)"
        )

        lines = [
            "TDT Binary Export Summary",
            "=" * 40,
            f"Export Date   : {export_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Block         : {self._app_state.block.name}",
            f"Stream        : {state.stream_name}",
            f"Channels      : {ch_1based}  (1-based)",
            f"Time Range    : {time_range_str}",
            f"Sample Rate   : {state.sample_rate:.6f} Hz",
            f"Samples/Ch    : {n_samples}",
            f"Num Channels  : {n_channels}",
            f"Scale Factor  : {opts['scale']:g}  (data multiplied before int16 conversion)",
            f"Data Type     : int16  (little-endian)",
            f"Sample Layout : {layout_desc}",
            f"File Extension: {opts['extension']}",
            "",
            "Active Filters:",
        ] + filter_lines

        with open(filepath, "w") as fh:
            fh.write("\n".join(lines) + "\n")

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
