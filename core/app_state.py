"""Application state management."""
import json
from pathlib import Path
from typing import Dict, Optional, List, Callable
from dataclasses import dataclass, field

from models import StreamState
from models.probe import ProbeGeometry
from tdt_io import TDTReader, TDTBlock


@dataclass
class AppState:
    """
    Global application state.

    Manages:
    - Current TDT block
    - Stream states (one per stream)
    - Current selection
    """

    # TDT data
    reader: TDTReader = field(default_factory=TDTReader)
    block: Optional[TDTBlock] = None

    # Probe geometry (optional; loaded independently of the TDT block)
    probe: Optional[ProbeGeometry] = None

    # Per-stream state
    stream_states: Dict[str, StreamState] = field(default_factory=dict)

    # Current selection
    current_stream: Optional[str] = None

    # Callbacks for state changes
    _on_block_loaded: List[Callable] = field(default_factory=list)
    _on_stream_changed: List[Callable] = field(default_factory=list)
    _on_state_updated: List[Callable] = field(default_factory=list)

    def load_block(self, folder_path: str) -> TDTBlock:
        """
        Load a TDT block from folder.

        Args:
            folder_path: Path to TDT block folder

        Returns:
            TDTBlock with metadata

        Raises:
            Various exceptions on failure
        """
        # Clear previous state
        self.close()

        # Load new block
        self.block = self.reader.load_block(folder_path, headers_only=False)

        # Create stream states
        for name, info in self.block.streams.items():
            self.stream_states[name] = StreamState(
                stream_name=name,
                num_channels=info.num_channels,
                sample_rate=info.sample_rate,
                duration=info.duration,
            )

        # Select first stream by default
        if self.block.streams:
            self.current_stream = list(self.block.streams.keys())[0]

        # Notify listeners
        for callback in self._on_block_loaded:
            callback(self.block)

        return self.block

    def select_stream(self, stream_name: str):
        """Select a stream as current."""
        if stream_name not in self.stream_states:
            raise ValueError(f"Unknown stream: {stream_name}")

        self.current_stream = stream_name

        # Notify listeners
        for callback in self._on_stream_changed:
            callback(stream_name)

    def get_current_state(self) -> Optional[StreamState]:
        """Get state for currently selected stream."""
        if self.current_stream is None:
            return None
        return self.stream_states.get(self.current_stream)

    def get_stream_state(self, stream_name: str) -> Optional[StreamState]:
        """Get state for a specific stream."""
        return self.stream_states.get(stream_name)

    def notify_state_updated(self):
        """Notify listeners that state has changed."""
        for callback in self._on_state_updated:
            callback()

    def on_block_loaded(self, callback: Callable):
        """Register callback for block loaded event."""
        self._on_block_loaded.append(callback)

    def on_stream_changed(self, callback: Callable):
        """Register callback for stream selection change."""
        self._on_stream_changed.append(callback)

    def on_state_updated(self, callback: Callable):
        """Register callback for state updates."""
        self._on_state_updated.append(callback)

    def set_probe(self, geometry: Optional[ProbeGeometry]):
        """Store probe geometry and notify listeners."""
        self.probe = geometry
        for callback in self._on_state_updated:
            callback()

    def close(self):
        """Close current block and clear state."""
        self.reader.close()
        self.block = None
        self.probe = None
        self.stream_states.clear()
        self.current_stream = None

    def save_session(self, filepath: str):
        """
        Save current session to JSON file.

        Args:
            filepath: Path to save session file
        """
        if self.block is None:
            raise ValueError("No block loaded to save")

        session = {
            "block_path": self.block.path,
            "current_stream": self.current_stream,
            "probe": self.probe.to_probeinterface_dict() if self.probe else None,
            "stream_states": {
                name: state.to_dict()
                for name, state in self.stream_states.items()
            },
        }

        with open(filepath, "w") as f:
            json.dump(session, f, indent=2)

    def load_session(self, filepath: str):
        """
        Load session from JSON file.

        Args:
            filepath: Path to session file
        """
        with open(filepath, "r") as f:
            session = json.load(f)

        # Load the block first
        block_path = session.get("block_path")
        if not block_path or not Path(block_path).exists():
            raise ValueError(f"Block path not found: {block_path}")

        self.load_block(block_path)

        # Restore stream states
        saved_states = session.get("stream_states", {})
        for name, state_dict in saved_states.items():
            if name in self.stream_states:
                # Merge saved state into loaded state
                saved = StreamState.from_dict(state_dict)
                current = self.stream_states[name]

                # Copy over user settings, keep hardware info from actual data
                current.channel_mode = saved.channel_mode
                current.selected_channel = min(
                    saved.selected_channel, current.num_channels - 1
                )
                current.overlay_channels = [
                    c for c in saved.overlay_channels
                    if c < current.num_channels
                ]
                if not current.overlay_channels:
                    current.overlay_channels = [0]
                current.view_start = saved.view_start
                current.view_end = min(saved.view_end, current.duration)
                current.filters = saved.filters
                current.global_bypass = saved.global_bypass
                current.scatter_mode = saved.scatter_mode
                current.fft_start = saved.fft_start
                current.fft_end = saved.fft_end
                current.fft_channels = [
                    c for c in saved.fft_channels
                    if c < current.num_channels
                ]
                current.psd_nperseg = saved.psd_nperseg
                current.psd_overlap = saved.psd_overlap

        # Restore probe geometry (optional — missing key or None is fine)
        probe_dict = session.get("probe")
        if probe_dict:
            try:
                self.probe = ProbeGeometry.from_probeinterface_dict(probe_dict)
            except Exception:
                self.probe = None

        # Restore selection
        if session.get("current_stream") in self.stream_states:
            self.select_stream(session["current_stream"])
