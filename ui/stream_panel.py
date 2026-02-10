"""Stream list panel widget."""
from typing import Optional

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QGroupBox,
)

from tdt_io import TDTBlock


class StreamPanel(QWidget):
    """
    Panel showing available streams in the loaded TDT block.

    Displays:
    - Block name and info
    - Tree of streams with channel counts and sample rates
    """

    # Signals
    stream_selected = Signal(str)  # stream name

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._block: Optional[TDTBlock] = None

    def _setup_ui(self):
        """Set up the widget layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Block info group
        self._block_group = QGroupBox("Block Info")
        block_layout = QVBoxLayout(self._block_group)

        self._block_name_label = QLabel("No block loaded")
        self._block_name_label.setWordWrap(True)
        block_layout.addWidget(self._block_name_label)

        self._duration_label = QLabel("")
        block_layout.addWidget(self._duration_label)

        layout.addWidget(self._block_group)

        # Streams tree
        streams_group = QGroupBox("Streams")
        streams_layout = QVBoxLayout(streams_group)

        self._streams_tree = QTreeWidget()
        self._streams_tree.setHeaderLabels(["Stream", "Channels", "Rate (Hz)"])
        self._streams_tree.setColumnWidth(0, 100)
        self._streams_tree.setColumnWidth(1, 60)
        self._streams_tree.setColumnWidth(2, 80)
        self._streams_tree.itemClicked.connect(self._on_item_clicked)
        streams_layout.addWidget(self._streams_tree)

        layout.addWidget(streams_group)
        layout.addStretch()

    def set_block(self, block: TDTBlock):
        """Set the TDT block to display."""
        self._block = block

        # Update block info
        self._block_name_label.setText(f"<b>{block.name}</b>")

        duration_str = self._format_duration(block.duration)
        self._duration_label.setText(
            f"Duration: {duration_str}\n"
            f"Streams: {len(block.streams)}"
        )

        # Populate streams tree
        self._streams_tree.clear()

        for name, info in sorted(block.streams.items()):
            item = QTreeWidgetItem([
                name,
                str(info.num_channels),
                f"{info.sample_rate:.0f}",
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, name)
            self._streams_tree.addTopLevelItem(item)

        # Select first stream
        if self._streams_tree.topLevelItemCount() > 0:
            self._streams_tree.setCurrentItem(
                self._streams_tree.topLevelItem(0)
            )

    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable form."""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = seconds % 60
            return f"{minutes}m {secs:.1f}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = seconds % 60
            return f"{hours}h {minutes}m {secs:.0f}s"

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle stream item click."""
        stream_name = item.data(0, Qt.ItemDataRole.UserRole)
        if stream_name:
            self.stream_selected.emit(stream_name)

    def select_stream(self, stream_name: str):
        """Programmatically select a stream."""
        for i in range(self._streams_tree.topLevelItemCount()):
            item = self._streams_tree.topLevelItem(i)
            if item.data(0, Qt.ItemDataRole.UserRole) == stream_name:
                self._streams_tree.setCurrentItem(item)
                break

    def get_selected_stream(self) -> Optional[str]:
        """Get currently selected stream name."""
        item = self._streams_tree.currentItem()
        if item:
            return item.data(0, Qt.ItemDataRole.UserRole)
        return None

    def clear(self):
        """Clear the panel."""
        self._block = None
        self._block_name_label.setText("No block loaded")
        self._duration_label.setText("")
        self._streams_tree.clear()
