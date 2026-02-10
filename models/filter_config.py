"""Filter configuration models."""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
import uuid


class FilterType(Enum):
    LOWPASS = "lowpass"
    HIGHPASS = "highpass"
    BANDPASS = "bandpass"
    NOTCH = "notch"
    CAR = "car"
    CMR = "cmr"
    VRMS_THRESHOLD = "vrms_threshold"


@dataclass
class FilterConfig:
    """Configuration for a single filter in the chain."""

    filter_type: FilterType
    order: int = 4
    cutoff_low: Optional[float] = None  # Hz
    cutoff_high: Optional[float] = None  # Hz
    notch_freq: Optional[float] = None  # Hz (for notch filter)
    notch_q: float = 30.0  # Quality factor for notch
    bypassed: bool = False
    uid: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    # CAR/CMR: list of channel subgroups (0-indexed)
    channel_groups: Optional[List[List[int]]] = None

    # Vrms threshold: multiplier
    vrms_multiplier: float = 3.0

    def __post_init__(self):
        """Validate filter parameters."""
        if self.filter_type == FilterType.LOWPASS and self.cutoff_high is None:
            raise ValueError("Lowpass filter requires cutoff_high")
        if self.filter_type == FilterType.HIGHPASS and self.cutoff_low is None:
            raise ValueError("Highpass filter requires cutoff_low")
        if self.filter_type == FilterType.BANDPASS:
            if self.cutoff_low is None or self.cutoff_high is None:
                raise ValueError("Bandpass filter requires both cutoffs")
        if self.filter_type == FilterType.NOTCH and self.notch_freq is None:
            raise ValueError("Notch filter requires notch_freq")
        if self.filter_type in (FilterType.CAR, FilterType.CMR):
            if not self.channel_groups or not any(
                len(g) >= 2 for g in self.channel_groups
            ):
                raise ValueError(
                    "CAR/CMR requires channel_groups with at least one group of 2+ channels"
                )
        if self.filter_type == FilterType.VRMS_THRESHOLD:
            if self.vrms_multiplier <= 0:
                raise ValueError("Vrms multiplier must be > 0")

    def get_display_name(self) -> str:
        """Return human-readable filter description."""
        if self.filter_type == FilterType.LOWPASS:
            return f"LP {self.cutoff_high:.0f} Hz (order {self.order})"
        elif self.filter_type == FilterType.HIGHPASS:
            return f"HP {self.cutoff_low:.0f} Hz (order {self.order})"
        elif self.filter_type == FilterType.BANDPASS:
            return f"BP {self.cutoff_low:.0f}-{self.cutoff_high:.0f} Hz (order {self.order})"
        elif self.filter_type == FilterType.NOTCH:
            return f"Notch {self.notch_freq:.0f} Hz (Q={self.notch_q:.0f})"
        elif self.filter_type == FilterType.CAR:
            n = len(self.channel_groups) if self.channel_groups else 0
            return f"CAR ({n} groups)"
        elif self.filter_type == FilterType.CMR:
            n = len(self.channel_groups) if self.channel_groups else 0
            return f"CMR ({n} groups)"
        elif self.filter_type == FilterType.VRMS_THRESHOLD:
            return f"Vrms Thresh {self.vrms_multiplier:.1f}x"
        return "Unknown"

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "filter_type": self.filter_type.value,
            "order": self.order,
            "cutoff_low": self.cutoff_low,
            "cutoff_high": self.cutoff_high,
            "notch_freq": self.notch_freq,
            "notch_q": self.notch_q,
            "bypassed": self.bypassed,
            "uid": self.uid,
            "channel_groups": self.channel_groups,
            "vrms_multiplier": self.vrms_multiplier,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FilterConfig":
        """Deserialize from dictionary."""
        return cls(
            filter_type=FilterType(data["filter_type"]),
            order=data.get("order", 4),
            cutoff_low=data.get("cutoff_low"),
            cutoff_high=data.get("cutoff_high"),
            notch_freq=data.get("notch_freq"),
            notch_q=data.get("notch_q", 30.0),
            bypassed=data.get("bypassed", False),
            uid=data.get("uid", str(uuid.uuid4())[:8]),
            channel_groups=data.get("channel_groups"),
            vrms_multiplier=data.get("vrms_multiplier", 3.0),
        )
