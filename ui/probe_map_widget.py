"""Probe map widget — 2D electrode layout colored by Vrms."""
from typing import Dict, Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from models.probe import ProbeGeometry


class ProbeMapWidget(QWidget):
    """
    Live 2D visualization of a multi-electrode probe.

    Electrode contacts are drawn as circles at their (x, y) positions in µm,
    sized by electrode radius (pxMode=False so circles scale with zoom).
    Colors:
        - Gray  → no Vrms data available
        - Blue  → low Vrms
        - Red   → high Vrms  (linear scale within the observed range)
    A white ring marks the currently selected channel.
    Hovering over a contact shows a tooltip with metadata.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._probe: Optional[ProbeGeometry] = None
        self._vrms_dict: Dict[int, float] = {}
        self._selected_ch: int = -1

        self._setup_ui()

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Placeholder shown when no probe is loaded
        self._placeholder = QLabel("No probe loaded\n(File › Load Probe...)")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self._placeholder)

        # pyqtgraph plot (hidden until a probe is loaded)
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setBackground("w")
        self._plot_widget.setAspectLocked(True)
        self._plot_widget.setLabel("bottom", "X (µm)")
        self._plot_widget.setLabel("left", "Y (µm)")
        self._plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self._plot_widget.setVisible(False)
        layout.addWidget(self._plot_widget)

        # ScatterPlotItem for contacts (pxMode=False → sizes in data units / µm)
        self._scatter = pg.ScatterPlotItem(pxMode=False)
        self._plot_widget.addItem(self._scatter)

        # Separate item for the selection ring (transparent fill, white outline)
        self._sel_scatter = pg.ScatterPlotItem(pxMode=False)
        self._plot_widget.addItem(self._sel_scatter)

        # Tooltip via mouse-move on the scene
        self._plot_widget.scene().sigMouseMoved.connect(self._on_mouse_moved)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_probe(self, probe: Optional[ProbeGeometry]):
        """Load probe geometry and render the layout."""
        self._probe = probe
        self._vrms_dict = {}
        self._selected_ch = -1

        if probe is None:
            self._placeholder.setVisible(True)
            self._plot_widget.setVisible(False)
            return

        self._placeholder.setVisible(False)
        self._plot_widget.setVisible(True)
        self._rebuild_spots()

    def update_vrms(self, vrms_dict: Dict[int, float]):
        """Recolor contacts based on updated Vrms values."""
        self._vrms_dict = vrms_dict or {}
        if self._probe is not None:
            self._rebuild_spots()

    def set_selected_channel(self, ch_idx: int):
        """Highlight the contact for the given 0-indexed channel with a white ring."""
        self._selected_ch = ch_idx
        if self._probe is not None:
            self._rebuild_spots()

    def clear(self):
        """Remove probe and reset widget."""
        self.set_probe(None)

    # ── Internal ─────────────────────────────────────────────────────────────

    def _rebuild_spots(self):
        """Recompute and push spot data to the scatter plot items."""
        if self._probe is None:
            return

        # ── Compute per-contact Vrms color ──────────────────────────────────
        vrms_list = [
            self._vrms_dict.get(c.channel_idx) for c in self._probe.contacts
        ]
        valid = [v for v in vrms_list if v is not None]
        vmin = min(valid) if valid else 0.0
        vmax = max(valid) if valid else 1.0
        if vmax <= vmin:
            vmax = vmin + 1e-12

        # ── Build spot dicts ─────────────────────────────────────────────────
        spots = []
        sel_spots = []

        for c, v in zip(self._probe.contacts, vrms_list):
            # Color: gray if no data, else blue→red
            if v is not None:
                norm = (v - vmin) / (vmax - vmin)
                r = int(255 * norm)
                b = int(255 * (1.0 - norm))
                brush = pg.mkBrush(r, 0, b, 210)
            else:
                brush = pg.mkBrush(160, 160, 160, 180)

            # Diameter in µm (minimum 15 µm so tiny contacts stay visible)
            diam = max(2.0 * c.radius_um, 15.0)

            spots.append(
                {
                    "pos": (c.x_um, c.y_um),
                    "size": diam,
                    "brush": brush,
                    "pen": pg.mkPen("k", width=0.5),
                    "data": c.channel_idx,
                }
            )

            if c.channel_idx == self._selected_ch:
                # White ring, slightly larger than the contact
                sel_spots.append(
                    {
                        "pos": (c.x_um, c.y_um),
                        "size": diam + 8.0,
                        "brush": pg.mkBrush(0, 0, 0, 0),  # transparent fill
                        "pen": pg.mkPen("w", width=2.5),
                        "data": c.channel_idx,
                    }
                )

        self._scatter.setData(spots)
        self._sel_scatter.setData(sel_spots)

    def _on_mouse_moved(self, scene_pos):
        """Show a tooltip for the contact nearest to the mouse cursor."""
        if self._probe is None:
            return

        vb = self._plot_widget.getViewBox()
        if not self._plot_widget.sceneBoundingRect().contains(scene_pos):
            from PySide6.QtWidgets import QToolTip
            QToolTip.hideText()
            return

        pt = vb.mapSceneToView(scene_pos)
        mx, my = pt.x(), pt.y()

        nearest = None
        min_d2 = float("inf")
        for c in self._probe.contacts:
            d2 = (c.x_um - mx) ** 2 + (c.y_um - my) ** 2
            threshold = max(c.radius_um * 2.5, 20.0) ** 2
            if d2 < threshold and d2 < min_d2:
                min_d2 = d2
                nearest = c

        from PySide6.QtWidgets import QToolTip

        if nearest is not None:
            vrms = self._vrms_dict.get(nearest.channel_idx)
            vrms_str = (
                f" | Vrms: {vrms * 1e6:.1f} µV" if vrms is not None else ""
            )
            tip = (
                f"Ch {nearest.channel_idx + 1}  |  Shank {nearest.shank_id}  |  "
                f"r={nearest.radius_um:.1f} µm  |  A={nearest.area_um2:.0f} µm²"
                f"{vrms_str}"
            )
            global_pos = self._plot_widget.mapToGlobal(
                self._plot_widget.mapFromScene(scene_pos)
            )
            QToolTip.showText(global_pos, tip)
        else:
            QToolTip.hideText()
