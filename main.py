#!/usr/bin/env python3
"""
TDT Multi-Channel Viewer

A cross-platform application for viewing and analyzing
Tucker-Davis Technologies neural recording data.
"""
import sys
import os

# Add the app directory to path for imports
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


def main():
    """Main entry point."""
    # Check dependencies
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
    except ImportError:
        print("Error: PySide6 is required. Install with: pip install PySide6")
        sys.exit(1)

    try:
        import pyqtgraph
    except ImportError:
        print("Error: pyqtgraph is required. Install with: pip install pyqtgraph")
        sys.exit(1)

    try:
        import numpy
        import scipy
    except ImportError:
        print("Error: numpy and scipy are required. Install with: pip install numpy scipy")
        sys.exit(1)

    try:
        import tdt
    except ImportError:
        print("Warning: tdt package not installed. Install with: pip install tdt")
        print("The application will run but won't be able to load TDT files.")

    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("TDT Multi-Channel Viewer")
    app.setOrganizationName("TDT Viewer")
    app.setApplicationVersion("1.0.0")

    # Set style
    app.setStyle("Fusion")

    # Import and create main window
    from ui import MainWindow

    window = MainWindow()
    window.show()

    # Handle command line argument (folder path)
    if len(sys.argv) > 1:
        folder_path = sys.argv[1]
        if os.path.isdir(folder_path):
            window._load_block(folder_path)

    # Run event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
