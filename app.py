"""
PhonexTrade - Paper Trading & Portfolio Analytics Platform
Entry point for the application.
"""

import sys
import os

# Ensure project root is on path so relative imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from data.database import initialize_database
from ui.main_window import MainWindow


def main():
    """Initialize the application and show the main window."""
    # Highdpi support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("PhonexTrade")
    app.setOrganizationName("PhonexTrade")
    app.setApplicationVersion("1.0.0")

    # Set default font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Initialize database tables
    initialize_database()

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()