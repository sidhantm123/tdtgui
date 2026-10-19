"""Blackrock (.nsX) file reading with windowed loading support."""
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np

from models.recording import StreamInfo, RecordingBlock
from .ccf_reader import read_ccf, ccf_labels, find_ccf

try:
    from neo.rawio import BlackrockRawIO
    NEO_AVAILABLE = True
except ImportError:
    NEO_AVAILABLE = False


# Multipliers that convert Blackrock's per-channel units to volts
_UNIT_TO_VOLTS = {"uv": 1e-6, "µv": 1e-6, "μv": 1e-6, "mv": 1e-3, "v": 1.0, "nv": 1e-9}

# Timestamp gaps larger than this split a recording into separate segments
# (only applies to PTP-timestamped files; older files mark pauses explicitly)
GAP_TOLERANCE_MS = 1.0


class _NsxStream:
    """One continuous segment of one .nsX file."""

    def __init__(self, rawio, seg_index: int, sample_rate: float, num_samples: int, to_volts: np.ndarray):
        self.rawio = rawio
        self.seg_index = seg_index
        self.sample_rate = sample_rate
        self.num_samples = num_samples
        self.to_volts = to_volts


class BlackrockReader:
    """Reader for Blackrock continuous (.ns1-.ns6) recordings with windowed loading."""

    NSX_EXTENSIONS = {f".ns{i}" for i in range(1, 7)}

    def __init__(self):
        self._block_path: Optional[str] = None
        self._block_info: Optional[RecordingBlock] = None
        self._streams: Dict[str, _NsxStream] = {}

    @staticmethod
    def is_blackrock_folder(folder_path: str) -> bool:
        """Check if folder contains Blackrock continuous data files."""
        folder = Path(folder_path)
        if not folder.is_dir():
            return False

        return any(
            f.suffix.lower() in BlackrockReader.NSX_EXTENSIONS for f in folder.iterdir()
        )

    def load_block(self, folder_path: str, headers_only: bool = True) -> RecordingBlock:
        """
        Load all .nsX files in a folder.

        Data is memory-mapped, so headers_only is accepted for interface
        compatibility with TDTReader but has no effect.

        Each .nsX file becomes a stream named "ns5", or "<basename>.ns5" when the
        folder holds several recordings. Recordings with pauses are split into one
        stream per segment ("ns5_seg2").

        Raises:
            ImportError: If neo package not available
            FileNotFoundError: If folder doesn't exist
            ValueError: If no readable .nsX data found
        """
        if not NEO_AVAILABLE:
            raise ImportError(
                "neo package not installed. Install with: pip install neo"
            )

        folder = Path(folder_path)
        if not folder.exists():
            raise FileNotFoundError(f"Folder not found: {folder_path}")

        self.close()

        # Group .nsX files by basename: {"rec001": [2, 5], ...}
        nsx_by_base: Dict[str, List[int]] = defaultdict(list)
        for f in sorted(folder.iterdir()):
            if f.suffix.lower() in self.NSX_EXTENSIONS:
                nsx_by_base[f.stem].append(int(f.suffix[-1]))

        if not nsx_by_base:
            raise ValueError("No .ns1-.ns6 files found in folder.")

        multiple_bases = len(nsx_by_base) > 1
        main_base = next(iter(nsx_by_base))

        # Channel labels from the .ccf override the .nsX header labels
        ccf_path = find_ccf(folder, main_base)
        ccf = read_ccf(str(ccf_path)) if ccf_path else None
        ccf_label_map = ccf_labels(ccf) if ccf else {}

        streams: Dict[str, StreamInfo] = {}
        t_starts: List[float] = []
        t_stops: List[float] = []

        for base, nsx_numbers in nsx_by_base.items():
            # Highest nsX first so the raw/broadband stream (ns5/ns6) is selected by default
            for nb in sorted(nsx_numbers, reverse=True):
                file_label = f"{base}.ns{nb}"
                try:
                    rawio = BlackrockRawIO(
                        filename=str(folder / base),
                        nsx_to_load=[nb],
                        load_nev=False,
                        gap_tolerance_ms=GAP_TOLERANCE_MS,
                    )
                    rawio.parse_header()
                except Exception as e:
                    raise ValueError(f"Failed to read {file_label}: {e}")

                if rawio.signal_streams_count() == 0:
                    continue

                channels = rawio.header["signal_channels"]
                labels = [
                    ccf_label_map.get(_int_or_none(ch_id), name) or name
                    for name, ch_id in zip(channels["name"], channels["id"])
                ]
                to_volts = np.array(
                    [_UNIT_TO_VOLTS.get(str(u).strip().lower(), 1.0) for u in channels["units"]]
                )
                fs = float(rawio.get_signal_sampling_rate(0))
                stream_base = file_label if multiple_bases else f"ns{nb}"
                n_segments = rawio.segment_count(0)

                for seg in range(n_segments):
                    n_samples = int(rawio.get_signal_size(0, seg, 0))
                    if n_samples < 1:
                        continue

                    name = stream_base if n_segments == 1 else f"{stream_base}_seg{seg + 1}"
                    self._streams[name] = _NsxStream(rawio, seg, fs, n_samples, to_volts)

                    duration = n_samples / fs
                    t_start = float(rawio.get_signal_t_start(0, seg, 0))
                    t_starts.append(t_start)
                    t_stops.append(t_start + duration)

                    streams[name] = StreamInfo(
                        name=name,
                        num_channels=len(channels),
                        sample_rate=fs,
                        duration=duration,
                        num_samples=n_samples,
                        dtype="int16",
                        channel_labels=list(labels),
                    )

        if not streams:
            raise ValueError(
                "No continuous data found in the .nsX files. "
                "Ensure the folder contains valid Blackrock recording data."
            )

        start_time = min(t_starts)
        stop_time = max(t_stops)

        self._block_path = str(folder)
        self._block_info = RecordingBlock(
            path=str(folder),
            name=folder.name if multiple_bases else main_base,
            start_time=start_time,
            stop_time=stop_time,
            duration=max(s.duration for s in streams.values()),
            streams=streams,
            source="blackrock",
            metadata={
                "ccf": ccf,
                "files": [f"{b}.ns{nb}" for b, nbs in nsx_by_base.items() for nb in nbs],
            },
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
            start_time: Start time in seconds from the stream start. None = beginning.
            end_time: End time in seconds. None = end.

        Returns:
            Tuple of (data, time_axis) where:
                data: ndarray of shape (n_channels, n_samples), in volts
                time_axis: ndarray of time values in seconds
        """
        if self._block_path is None:
            raise ValueError("No block loaded. Call load_block first.")

        if stream_name not in self._streams:
            raise ValueError(f"Stream '{stream_name}' not found in block")

        stream = self._streams[stream_name]
        fs = stream.sample_rate
        n_channels = len(stream.to_volts)

        if start_time is None:
            start_time = 0.0
        if end_time is None:
            end_time = stream.num_samples / fs

        i_start = min(max(0, int(start_time * fs)), stream.num_samples)
        i_stop = min(max(i_start, int(end_time * fs)), stream.num_samples)

        if channels is None:
            valid_channels = list(range(n_channels))
        else:
            valid_channels = [c for c in channels if 0 <= c < n_channels]
            if not valid_channels:
                raise ValueError(f"No valid channels in selection: {channels}")

        try:
            raw = stream.rawio.get_analogsignal_chunk(
                block_index=0,
                seg_index=stream.seg_index,
                i_start=i_start,
                i_stop=i_stop,
                stream_index=0,
                channel_indexes=valid_channels,
            )
            data = stream.rawio.rescale_signal_raw_to_float(
                raw, dtype="float64", stream_index=0, channel_indexes=valid_channels
            )
        except Exception as e:
            raise ValueError(f"Failed to read stream data: {e}")

        # neo returns (samples, channels) in the file's units; convert to (channels, samples) volts
        data = (data * stream.to_volts[valid_channels]).T
        time_axis = (i_start + np.arange(data.shape[1])) / fs

        return np.ascontiguousarray(data), time_axis

    def get_block_info(self) -> Optional[RecordingBlock]:
        """Return current block info."""
        return self._block_info

    def close(self):
        """Release file handles and clear cached data."""
        self._streams.clear()
        self._block_path = None
        self._block_info = None


def _int_or_none(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
