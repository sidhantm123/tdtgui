"""Probe geometry model for electrode arrays (probeinterface format)."""
import json
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np


@dataclass
class ProbeContact:
    """Single electrode contact on a probe."""

    channel_idx: int   # 0-indexed (device_channel_indices[i] - 1)
    contact_id: str    # string ID from probe file
    x_um: float        # x-position in µm
    y_um: float        # y-position in µm
    shank_id: str      # shank identifier string
    radius_um: float   # electrode radius in µm

    @property
    def area_um2(self) -> float:
        """Electrode area in µm²."""
        return math.pi * self.radius_um ** 2


@dataclass
class ProbeGeometry:
    """Spatial layout of a multi-electrode probe array."""

    contacts: List[ProbeContact] = field(default_factory=list)
    si_units: str = "µm"

    @classmethod
    def from_probeinterface_dict(cls, data: dict) -> "ProbeGeometry":
        """Parse from a probeinterface JSON dict (reads first probe entry)."""
        probes = data.get("probes", [])
        if not probes:
            raise ValueError("No probes found in probeinterface data")

        probe = probes[0]
        positions = probe.get("contact_positions", [])
        device_ch = probe.get("device_channel_indices", [])
        contact_ids = probe.get("contact_ids", [])
        shank_ids = probe.get("shank_ids", [])
        shape_params = probe.get("contact_shape_params", [])
        si_units = probe.get("si_units", "µm")

        contacts: List[ProbeContact] = []
        for i, pos in enumerate(positions):
            ch_idx = int(device_ch[i]) - 1 if i < len(device_ch) else i
            c_id = str(contact_ids[i]) if i < len(contact_ids) else str(i + 1)
            shank = str(shank_ids[i]) if i < len(shank_ids) else "0"
            radius = (
                float(shape_params[i].get("radius", 10.0))
                if i < len(shape_params)
                else 10.0
            )
            contacts.append(
                ProbeContact(
                    channel_idx=ch_idx,
                    contact_id=c_id,
                    x_um=float(pos[0]),
                    y_um=float(pos[1]),
                    shank_id=shank,
                    radius_um=radius,
                )
            )

        return cls(contacts=contacts, si_units=si_units)

    @classmethod
    def from_probeinterface_file(cls, path: str) -> "ProbeGeometry":
        """Load from a probeinterface JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_probeinterface_dict(data)

    def to_probeinterface_dict(self) -> dict:
        """Serialize to probeinterface JSON format."""
        return {
            "specification": "probeinterface",
            "version": "0.2.28",
            "probes": [
                {
                    "ndim": 2,
                    "si_units": self.si_units,
                    "annotations": {},
                    "contact_annotations": {},
                    "contact_positions": [[c.x_um, c.y_um] for c in self.contacts],
                    "contact_plane_axes": [
                        [[1.0, 0.0], [0.0, 1.0]] for _ in self.contacts
                    ],
                    "contact_shapes": ["circle"] * len(self.contacts),
                    "contact_shape_params": [
                        {"radius": c.radius_um} for c in self.contacts
                    ],
                    "device_channel_indices": [
                        c.channel_idx + 1 for c in self.contacts
                    ],
                    "contact_ids": [c.contact_id for c in self.contacts],
                    "shank_ids": [c.shank_id for c in self.contacts],
                }
            ],
        }

    # ── Queries ──────────────────────────────────────────────────────────────

    def get_shank_groups(self) -> Dict[str, List[int]]:
        """Return shank_id → sorted list of 0-indexed channel indices."""
        groups: Dict[str, List[int]] = {}
        for c in self.contacts:
            groups.setdefault(c.shank_id, []).append(c.channel_idx)
        return {k: sorted(v) for k, v in sorted(groups.items())}

    def get_channel_positions(self) -> np.ndarray:
        """Return (n_contacts, 2) array of [x_um, y_um]."""
        return np.array([[c.x_um, c.y_um] for c in self.contacts], dtype=float)

    def get_contact_areas_um2(self) -> np.ndarray:
        """Return (n_contacts,) array of electrode areas in µm²."""
        return np.array([c.area_um2 for c in self.contacts], dtype=float)

    def get_contact_by_channel(self, ch_idx: int) -> Optional[ProbeContact]:
        """Find contact by 0-indexed channel index. Returns None if not found."""
        for c in self.contacts:
            if c.channel_idx == ch_idx:
                return c
        return None

    def channel_count(self) -> int:
        """Number of electrode contacts."""
        return len(self.contacts)
