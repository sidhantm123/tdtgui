"""TDT file reading with windowed loading support."""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np

try:
    import tdt
    TDT_AVAILABLE = True
except ImportError:
    TDT_AVAILABLE = False


@dataclass
class StreamInfo:
    """Information about a TDT stream."""

    name: str
    num_channels: int
    sample_rate: float
    duration: float  # seconds
    num_samples: int
    dtype: str


@dataclass
class TDTBlock:
    """Represents a loaded TDT block with metadata."""

    path: str
    name: str
    start_time: float
    stop_time: float
    duration: float
    streams: Dict[str, StreamInfo]

    def get_stream_names(self) -> List[str]:
        """Return list of stream names."""
        return list(self.streams.keys())


class TDTReader:
    """Reader for TDT neural recording data with windowed loading."""

    # Known TDT file extensions
    TDT_EXTENSIONS = {".tdx", ".tev", ".tsq", ".tnt", ".tbk", ".tin", ".sev"}

    def __init__(self):
        self._block_path: Optional[str] = None
        self._block_info: Optional[TDTBlock] = None
        self._raw_data: Optional[object] = None  # Cached tdt read result

    @staticmethod
    def is_tdt_folder(folder_path: str) -> bool:
        """Check if folder contains TDT data files."""
        if not TDT_AVAILABLE:
            return False

        folder = Path(folder_path)
        if not folder.is_dir():
            return False

        # Check for any TDT-related files
        for f in folder.iterdir():
            if f.suffix.lower() in TDTReader.TDT_EXTENSIONS:
                return True

        # Also check for subdirectories that might contain TDT data
        # TDT often stores data in block folders
        return False

    def load_block(self, folder_path: str, headers_only: bool = True) -> TDTBlock:
        """
        Load TDT block from folder.

        Args:
            folder_path: Path to TDT block folder
            headers_only: If True, only load headers (faster). Set False to cache all data.

        Returns:
            TDTBlock with metadata

        Raises:
            ImportError: If tdt package not available
            FileNotFoundError: If folder doesn't exist
            ValueError: If not a valid TDT block
        """
        if not TDT_AVAILABLE:
            raise ImportError(
                "TDT package not installed. Install with: pip install tdt"
            )

        folder = Path(folder_path)
        if not folder.exists():
            raise FileNotFoundError(f"Folder not found: {folder_path}")

        try:
            # Load with headers only for speed, or full data if requested
            if headers_only:
                data = tdt.read_block(str(folder), headers=1)
            else:
                data = tdt.read_block(str(folder))

            self._raw_data = data
            self._block_path = str(folder)

        except Exception as e:
            raise ValueError(f"Failed to read TDT block: {e}")

        # Extract block info
        block_name = folder.name

        # Get timing info
        start_time = getattr(data, "start_time", [0.0])
        stop_time = getattr(data, "stop_time", [0.0])
        if isinstance(start_time, (list, np.ndarray)):
            start_time = float(start_time[0]) if len(start_time) > 0 else 0.0
        if isinstance(stop_time, (list, np.ndarray)):
            stop_time = float(stop_time[0]) if len(stop_time) > 0 else 0.0

        duration = stop_time - start_time if stop_time > start_time else 0.0

        # Extract stream information
        streams = {}

        # Check for streams store
        if hasattr(data, "streams"):
            streams_data = data.streams
            for stream_name in dir(streams_data):
                if stream_name.startswith("_"):
                    continue

                stream = getattr(streams_data, stream_name, None)
                if stream is None:
                    continue

                # Get stream properties
                try:
                    fs = float(getattr(stream, "fs", 0))
                    if fs == 0:
                        continue

                    # Get data shape for channel count
                    stream_data = getattr(stream, "data", None)
                    if stream_data is not None:
                        if isinstance(stream_data, np.ndarray):
                            if stream_data.ndim == 1:
                                n_channels = 1
                                n_samples = stream_data.shape[0]
                            else:
                                n_channels = stream_data.shape[0]
                                n_samples = stream_data.shape[1]
                            dtype = str(stream_data.dtype)
                        else:
                            n_channels = int(getattr(stream, "channel", [1])[0]) if hasattr(stream, "channel") else 1
                            n_samples = int(duration * fs)
                            dtype = "float32"
                    else:
                        n_channels = int(getattr(stream, "channel", [1])[-1]) if hasattr(stream, "channel") else 1
                        n_samples = int(duration * fs)
                        dtype = "float32"

                    stream_duration = n_samples / fs if fs > 0 else duration

                    streams[stream_name] = StreamInfo(
                        name=stream_name,
                        num_channels=n_channels,
                        sample_rate=fs,
                        duration=stream_duration,
                        num_samples=n_samples,
                        dtype=dtype,
                    )
                except (AttributeError, TypeError, IndexError):
                    continue

        # If no streams found, try alternative detection
        if not streams:
            # Check for epocs, snips, scalars
            for store_type in ["epocs", "snips", "scalars"]:
                store = getattr(data, store_type, None)
                if store is not None:
                    for name in dir(store):
                        if name.startswith("_"):
                            continue
                        item = getattr(store, name, None)
                        if item is not None and hasattr(item, "fs"):
                            fs = float(item.fs)
                            if fs > 0:
                                streams[name] = StreamInfo(
                                    name=name,
                                    num_channels=1,
                                    sample_rate=fs,
                                    duration=duration,
                                    num_samples=int(duration * fs),
                                    dtype="float32",
                                )

        if not streams:
            raise ValueError(
                "No valid streams found in TDT block. "
                "Ensure the folder contains valid TDT recording data."
            )

        self._block_info = TDTBlock(
            path=str(folder),
            name=block_name,
            start_time=start_time,
            stop_time=stop_time,
            duration=duration,
            streams=streams,
        )

        return self._block_info

    def get_stream_data(
        self,
        stream_name: str,
        channels: Optional[List[int]] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Get stream data for specified channels and time range.

        Args:
            stream_name: Name of the stream
            channels: List of channel indices (0-based). None = all channels.
            start_time: Start time in seconds. None = beginning.
            end_time: End time in seconds. None = end.

        Returns:
            Tuple of (data, time_axis) where:
                data: ndarray of shape (n_channels, n_samples)
                time_axis: ndarray of time values in seconds
        """
        if self._block_path is None:
            raise ValueError("No block loaded. Call load_block first.")

        if stream_name not in self._block_info.streams:
            raise ValueError(f"Stream '{stream_name}' not found in block")

        stream_info = self._block_info.streams[stream_name]
        fs = stream_info.sample_rate

        # Calculate sample indices
        if start_time is None:
            start_time = 0.0
        if end_time is None:
            end_time = stream_info.duration

        start_time = max(0.0, start_time)
        end_time = min(stream_info.duration, end_time)

        start_sample = int(start_time * fs)
        end_sample = int(end_time * fs)

        # Reload data for the specific time range if needed
        try:
            data = tdt.read_block(
                self._block_path,
                store=stream_name,
                t1=start_time,
                t2=end_time,
            )

            stream = getattr(data.streams, stream_name, None)
            if stream is None:
                raise ValueError(f"Could not read stream '{stream_name}'")

            stream_data = stream.data

            # Ensure 2D array (channels x samples)
            if stream_data.ndim == 1:
                stream_data = stream_data.reshape(1, -1)

            # Select channels
            if channels is not None:
                valid_channels = [c for c in channels if 0 <= c < stream_data.shape[0]]
                if not valid_channels:
                    raise ValueError(f"No valid channels in selection: {channels}")
                stream_data = stream_data[valid_channels, :]

            # Create time axis
            n_samples = stream_data.shape[1]
            time_axis = np.linspace(start_time, start_time + n_samples / fs, n_samples)

            return stream_data.astype(np.float64), time_axis

        except Exception as e:
            raise ValueError(f"Failed to read stream data: {e}")

    def get_block_info(self) -> Optional[TDTBlock]:
        """Return current block info."""
        return self._block_info

    def close(self):
        """Clear cached data."""
        self._block_path = None
        self._block_info = None
        self._raw_data = None
