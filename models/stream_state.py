"""Stream state model for per-stream persistence."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
from .filter_config import FilterConfig


class ChannelMode(Enum):
    SINGLE = "single"
    OVERLAY = "overlay"


@dataclass
class StreamState:
    """State for a single stream, persisted when switching streams."""

    stream_name: str
    num_channels: int
    sample_rate: float
    duration: float  # seconds

    # Channel selection
    channel_mode: ChannelMode = ChannelMode.SINGLE
    selected_channel: int = 0  # For single mode
    overlay_channels: List[int] = field(default_factory=list)  # For overlay mode
    max_overlay_channels: int = 8

    # View state
    view_start: float = 0.0  # seconds
    view_end: float = 10.0  # seconds (default 10s window)

    # Filter chain (ordered)
    filters: List[FilterConfig] = field(default_factory=list)
    global_bypass: bool = False

    # Display mode
    scatter_mode: bool = False

    # Vrms (transient, not persisted)
    vrms_values: Dict[int, float] = field(default_factory=dict)

    # FFT/PSD settings
    fft_start: Optional[float] = None
    fft_end: Optional[float] = None
    fft_channels: List[int] = field(default_factory=list)
    psd_nperseg: int = 1024
    psd_overlap: float = 0.5

    def __post_init__(self):
        """Initialize view_end based on duration if needed."""
        if self.view_end > self.duration:
            self.view_end = min(10.0, self.duration)
        if not self.overlay_channels and self.num_channels > 0:
            self.overlay_channels = [0]

    def get_active_channels(self) -> List[int]:
        """Return list of currently active channel indices."""
        if self.channel_mode == ChannelMode.SINGLE:
            return [self.selected_channel]
        return self.overlay_channels.copy()

    def add_overlay_channel(self, channel: int) -> bool:
        """Add channel to overlay. Returns True if added."""
        if channel in self.overlay_channels:
            return False
        if len(self.overlay_channels) >= self.max_overlay_channels:
            return False
        if channel < 0 or channel >= self.num_channels:
            return False
        self.overlay_channels.append(channel)
        return True

    def remove_overlay_channel(self, channel: int) -> bool:
        """Remove channel from overlay. Returns True if removed."""
        if channel in self.overlay_channels:
            self.overlay_channels.remove(channel)
            return True
        return False

    def move_filter(self, from_idx: int, to_idx: int):
        """Move a filter in the chain."""
        if 0 <= from_idx < len(self.filters) and 0 <= to_idx < len(self.filters):
            filt = self.filters.pop(from_idx)
            self.filters.insert(to_idx, filt)

    def add_filter(self, filt: FilterConfig):
        """Add a filter to the end of the chain."""
        self.filters.append(filt)

    def remove_filter(self, uid: str):
        """Remove a filter by its UID."""
        self.filters = [f for f in self.filters if f.uid != uid]

    def get_view_range(self) -> Tuple[float, float]:
        """Return current view range in seconds."""
        return (self.view_start, self.view_end)

    def set_view_range(self, start: float, end: float):
        """Set view range, clamping to valid bounds."""
        self.view_start = max(0.0, min(start, self.duration))
        self.view_end = max(self.view_start + 0.001, min(end, self.duration))

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON export."""
        return {
            "stream_name": self.stream_name,
            "num_channels": self.num_channels,
            "sample_rate": self.sample_rate,
            "duration": self.duration,
            "channel_mode": self.channel_mode.value,
            "selected_channel": self.selected_channel,
            "overlay_channels": self.overlay_channels,
            "view_start": self.view_start,
            "view_end": self.view_end,
            "filters": [f.to_dict() for f in self.filters],
            "global_bypass": self.global_bypass,
            "scatter_mode": self.scatter_mode,
            "fft_start": self.fft_start,
            "fft_end": self.fft_end,
            "fft_channels": self.fft_channels,
            "psd_nperseg": self.psd_nperseg,
            "psd_overlap": self.psd_overlap,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StreamState":
        """Deserialize from dictionary."""
        state = cls(
            stream_name=data["stream_name"],
            num_channels=data["num_channels"],
            sample_rate=data["sample_rate"],
            duration=data["duration"],
        )
        state.channel_mode = ChannelMode(data.get("channel_mode", "single"))
        state.selected_channel = data.get("selected_channel", 0)
        state.overlay_channels = data.get("overlay_channels", [0])
        state.view_start = data.get("view_start", 0.0)
        state.view_end = data.get("view_end", 10.0)
        state.filters = [FilterConfig.from_dict(f) for f in data.get("filters", [])]
        state.global_bypass = data.get("global_bypass", False)
        state.scatter_mode = data.get("scatter_mode", False)
        state.fft_start = data.get("fft_start")
        state.fft_end = data.get("fft_end")
        state.fft_channels = data.get("fft_channels", [])
        state.psd_nperseg = data.get("psd_nperseg", 1024)
        state.psd_overlap = data.get("psd_overlap", 0.5)
        return state
