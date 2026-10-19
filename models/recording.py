"""Format-independent recording metadata shared by all readers."""
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class StreamInfo:
    """Information about a continuous stream."""

    name: str
    num_channels: int
    sample_rate: float
    duration: float  # seconds
    num_samples: int
    dtype: str
    channel_labels: Optional[List[str]] = None  # One per channel, if the format provides them


@dataclass
class RecordingBlock:
    """Represents a loaded recording (TDT block or Blackrock file set) with metadata."""

    path: str
    name: str
    start_time: float
    stop_time: float
    duration: float
    streams: Dict[str, StreamInfo]
    source: str = "tdt"  # "tdt" or "blackrock"
    metadata: dict = field(default_factory=dict)  # Format-specific extras (e.g. parsed .ccf)

    def get_stream_names(self) -> List[str]:
        """Return list of stream names."""
        return list(self.streams.keys())
