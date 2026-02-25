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

# Suppress Qt font-alias warning (pyqtgraph requests "Monospace" which doesn't
# exist by that name on macOS/Windows, causing a slow lookup + noisy log line)
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.fonts=false")


def main():
    """Main entry point."""
    # Check PySide6 first — needed before anything else
    try:
        from PySide6.QtWidgets import QApplication, QSplashScreen
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPixmap, QColor, QPainter, QFont
    except ImportError:
        print("Error: PySide6 is required. Install with: pip install PySide6")
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

    # Create application first so macOS registers it as a GUI app immediately
    app = QApplication(sys.argv)
    app.setApplicationName("TDT Multi-Channel Viewer")
    app.setOrganizationName("TDT Viewer")
    app.setApplicationVersion("1.0.0")
    app.setStyle("Fusion")

    # Show a splash screen while pyqtgraph (slow ~4s import) loads
    splash_pix = QPixmap(420, 120)
    splash_pix.fill(QColor("#1e1e2e"))
    painter = QPainter(splash_pix)
    painter.setPen(QColor("#cdd6f4"))
    font = QFont()
    font.setPointSize(16)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(splash_pix.rect(), Qt.AlignmentFlag.AlignCenter, "TDT Multi-Channel Viewer\nLoading…")
    painter.end()

    splash = QSplashScreen(splash_pix)
    splash.show()
    app.processEvents()

    # Now do the slow pyqtgraph import (while splash is visible)
    try:
        import pyqtgraph
    except ImportError:
        splash.close()
        print("Error: pyqtgraph is required. Install with: pip install pyqtgraph")
        sys.exit(1)

    # Import and create main window
    from ui import MainWindow

    window = MainWindow()
    splash.finish(window)
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
