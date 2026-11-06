# main.py

import sys
import argparse
import sqlite3
from pathlib import Path
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt
import PySide6.QtSvg  # Ensures QtSvg plugins are bundled by PyInstaller
from core.database import DatabaseManager
from ui.theme import PRO_DASH_STYLE
from ui.main_window import ProDashMainWindow


def main():
    parser = argparse.ArgumentParser(description='Pro Dash — local developer library')
    parser.add_argument('--database', type=Path, help='Use a separate SQLite library file')
    args = parser.parse_args()
    # High-DPI scaling support for crisp fonts on Windows
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Pro Dash")
    app.setOrganizationName('ProDash')
    app.setApplicationVersion('1.0.0')
    app.setStyle('Fusion')
    bundle_dir = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS') else Path(__file__).resolve().parent
    icon_file = bundle_dir / 'assets' / 'pro-dash.ico'
    if not icon_file.exists():
        icon_file = bundle_dir / 'assets' / 'pro-dash.svg'
    app.setWindowIcon(QIcon(str(icon_file)))
    app.setStyleSheet(PRO_DASH_STYLE)

    # Initialize SQLite Engine & Seed Starter Data
    try:
        db = DatabaseManager(str(args.database.resolve()) if args.database else None)
        db.seed_initial_data()
        window = ProDashMainWindow(db)
    except (OSError, sqlite3.Error) as error:
        QMessageBox.critical(None, 'Could not open Pro Dash',
                             f'The library could not be opened. Check the database location and permissions.\n\n{error}')
        return 1
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
