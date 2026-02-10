"""Worker threads for background processing."""
from typing import List, Optional, Tuple
import numpy as np

from PySide6.QtCore import QObject, QRunnable, Signal, Slot, QThreadPool

from models import FilterConfig
from dsp import apply_filter_chain, compute_fft, compute_psd, decimate_for_display


class WorkerSignals(QObject):
    """Signals for worker threads."""

    started = Signal()
    finished = Signal()
    error = Signal(str)
    progress = Signal(int)  # 0-100
    result = Signal(object)  # Generic result
    cancelled = Signal()


class CancellableWorker(QRunnable):
    """Base class for cancellable workers."""

    def __init__(self):
        super().__init__()
        self.signals = WorkerSignals()
        self._cancelled = False

    def cancel(self):
        """Request cancellation."""
        self._cancelled = True

    def is_cancelled(self) -> bool:
        """Check if cancellation was requested."""
        return self._cancelled


class DataLoadWorker(CancellableWorker):
    """
    Worker for loading stream data.

    Emits result as dict with:
        - 'data': np.ndarray (n_channels, n_samples)
        - 'time': np.ndarray
        - 'stream_name': str
        - 'channels': list of channel indices
    """

    def __init__(
        self,
        reader,
        stream_name: str,
        channels: List[int],
        start_time: float,
        end_time: float,
    ):
        super().__init__()
        self.reader = reader
        self.stream_name = stream_name
        self.channels = channels
        self.start_time = start_time
        self.end_time = end_time

    @Slot()
    def run(self):
        """Execute the data loading."""
        self.signals.started.emit()

        try:
            if self.is_cancelled():
                self.signals.cancelled.emit()
                return

            self.signals.progress.emit(10)

            data, time_axis = self.reader.get_stream_data(
                self.stream_name,
                channels=self.channels,
                start_time=self.start_time,
                end_time=self.end_time,
            )

            if self.is_cancelled():
                self.signals.cancelled.emit()
                return

            self.signals.progress.emit(100)

            result = {
                "data": data,
                "time": time_axis,
                "stream_name": self.stream_name,
                "channels": self.channels,
            }

            self.signals.result.emit(result)
            self.signals.finished.emit()

        except Exception as e:
            self.signals.error.emit(str(e))


class FilterWorker(CancellableWorker):
    """
    Worker for applying filter chains.

    Emits result as dict with:
        - 'data': filtered np.ndarray
        - 'time': np.ndarray (unchanged)
        - 'warnings': list of warning strings
        - 'vrms': dict mapping channel index to Vrms value
    """

    def __init__(
        self,
        data: np.ndarray,
        time_axis: np.ndarray,
        filters: List[FilterConfig],
        fs: float,
        global_bypass: bool = False,
        all_channel_data: Optional[np.ndarray] = None,
        channel_indices: Optional[List[int]] = None,
        max_plot_points: int = 8000,
    ):
        super().__init__()
        self.data = data
        self.time_axis = time_axis
        self.filters = filters
        self.fs = fs
        self.global_bypass = global_bypass
        self.all_channel_data = all_channel_data
        self.channel_indices = channel_indices
        self.max_plot_points = max_plot_points

    @Slot()
    def run(self):
        """Execute the filtering and decimation."""
        self.signals.started.emit()

        try:
            if self.is_cancelled():
                self.signals.cancelled.emit()
                return

            self.signals.progress.emit(10)

            filtered_data, warnings, vrms = apply_filter_chain(
                self.data,
                self.filters,
                self.fs,
                self.global_bypass,
                all_channel_data=self.all_channel_data,
                channel_indices=self.channel_indices,
            )

            if self.is_cancelled():
                self.signals.cancelled.emit()
                return

            self.signals.progress.emit(60)

            # Decimate for display
            if filtered_data.ndim == 1:
                n_samples = len(filtered_data)
            else:
                n_samples = filtered_data.shape[1]

            if n_samples > self.max_plot_points:
                plot_data, plot_time = decimate_for_display(
                    filtered_data, self.time_axis,
                    target_points=self.max_plot_points,
                )
            else:
                plot_data = filtered_data
                plot_time = self.time_axis

            if self.is_cancelled():
                self.signals.cancelled.emit()
                return

            self.signals.progress.emit(100)

            result = {
                "data": filtered_data,
                "plot_data": plot_data,
                "plot_time": plot_time,
                "time": self.time_axis,
                "warnings": warnings,
                "vrms": vrms,
            }

            self.signals.result.emit(result)
            self.signals.finished.emit()

        except Exception as e:
            self.signals.error.emit(str(e))


class SpectralWorker(CancellableWorker):
    """
    Worker for spectral analysis (FFT/PSD).

    Emits result as dict with:
        - 'freqs': frequency array
        - 'magnitude': magnitude array (for FFT) or PSD values
        - 'method': 'fft' or 'psd'
        - 'channels': list of channel indices
    """

    def __init__(
        self,
        data: np.ndarray,
        fs: float,
        method: str = "psd",  # 'fft' or 'psd'
        channels: Optional[List[int]] = None,
        nperseg: int = 1024,
        overlap: float = 0.5,
    ):
        super().__init__()
        self.data = data
        self.fs = fs
        self.method = method
        self.channels = channels
        self.nperseg = nperseg
        self.overlap = overlap

    @Slot()
    def run(self):
        """Execute the spectral analysis."""
        self.signals.started.emit()

        try:
            if self.is_cancelled():
                self.signals.cancelled.emit()
                return

            self.signals.progress.emit(10)

            # Select channels
            if self.data.ndim == 1:
                data_to_analyze = self.data
                actual_channels = [0]
            else:
                if self.channels is not None:
                    valid_channels = [
                        c for c in self.channels
                        if 0 <= c < self.data.shape[0]
                    ]
                    if valid_channels:
                        data_to_analyze = self.data[valid_channels, :]
                        actual_channels = valid_channels
                    else:
                        data_to_analyze = self.data
                        actual_channels = list(range(self.data.shape[0]))
                else:
                    data_to_analyze = self.data
                    actual_channels = list(range(self.data.shape[0]))

            if self.is_cancelled():
                self.signals.cancelled.emit()
                return

            self.signals.progress.emit(50)

            if self.method == "fft":
                freqs, magnitude = compute_fft(data_to_analyze, self.fs)
            else:
                freqs, magnitude = compute_psd(
                    data_to_analyze,
                    self.fs,
                    nperseg=self.nperseg,
                    overlap=self.overlap,
                )

            if self.is_cancelled():
                self.signals.cancelled.emit()
                return

            self.signals.progress.emit(100)

            result = {
                "freqs": freqs,
                "magnitude": magnitude,
                "method": self.method,
                "channels": actual_channels,
            }

            self.signals.result.emit(result)
            self.signals.finished.emit()

        except Exception as e:
            self.signals.error.emit(str(e))


class DecimationWorker(CancellableWorker):
    """
    Worker for decimating data for display.

    Emits result as dict with:
        - 'data': decimated np.ndarray
        - 'time': decimated time axis
    """

    def __init__(
        self,
        data: np.ndarray,
        time_axis: np.ndarray,
        target_points: int = 4000,
    ):
        super().__init__()
        self.data = data
        self.time_axis = time_axis
        self.target_points = target_points

    @Slot()
    def run(self):
        """Execute the decimation."""
        self.signals.started.emit()

        try:
            if self.is_cancelled():
                self.signals.cancelled.emit()
                return

            decimated_data, decimated_time = decimate_for_display(
                self.data,
                self.time_axis,
                target_points=self.target_points,
            )

            result = {
                "data": decimated_data,
                "time": decimated_time,
            }

            self.signals.result.emit(result)
            self.signals.finished.emit()

        except Exception as e:
            self.signals.error.emit(str(e))


class WorkerManager:
    """Manages worker threads and provides cancellation."""

    def __init__(self, max_threads: int = 4):
        self.thread_pool = QThreadPool.globalInstance()
        self.thread_pool.setMaxThreadCount(max_threads)
        self._active_workers: List[CancellableWorker] = []

    def submit(self, worker: CancellableWorker):
        """Submit a worker for execution."""
        self._active_workers.append(worker)

        # Remove from list when done
        def cleanup():
            if worker in self._active_workers:
                self._active_workers.remove(worker)

        worker.signals.finished.connect(cleanup)
        worker.signals.error.connect(cleanup)
        worker.signals.cancelled.connect(cleanup)

        self.thread_pool.start(worker)

    def cancel_all(self):
        """Cancel all active workers."""
        for worker in self._active_workers:
            worker.cancel()

    def wait_all(self, timeout_ms: int = 5000) -> bool:
        """Wait for all workers to complete."""
        return self.thread_pool.waitForDone(timeout_ms)
