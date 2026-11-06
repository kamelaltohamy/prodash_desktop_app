import sys
from pathlib import Path

PRO_DASH_STYLE = """
/* ==========================================
   GLOBAL APPLICATION DEFAULTS
   ========================================== */
QMainWindow, QWidget {
    background-color: #121212;
    color: #F9FAFB;
    font-family: 'Segoe UI', -apple-system, sans-serif;
    font-size: 14px;
}

/* ==========================================
   LEFT SIDEBAR NAVIGATION
   ========================================== */
QFrame#Sidebar {
    background-color: #18181B;
    border-right: 1px solid #27272A;
}

QLabel#BrandTitle {
    color: #10B981;
    font-size: 22px;
    font-weight: 800;
    letter-spacing: 1px;
}

QLabel#BrandSubtitle {
    color: #9CA3AF;
    font-size: 11px;
    font-weight: 600;
}

QLabel#SectionHeader {
    color: #6B7280;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.2px;
    padding-left: 10px;
    margin-top: 12px;
    margin-bottom: 4px;
}

QPushButton.NavButton {
    background-color: transparent;
    color: #D1D5DB;
    border: none;
    border-radius: 8px;
    padding: 12px 16px;
    text-align: left;
    font-size: 14px;
    font-weight: 600;
}

QPushButton.NavButton:hover {
    background-color: #27272A;
    color: #FFFFFF;
}

QPushButton.NavButton:checked {
    background-color: rgba(16, 185, 129, 0.14);
    color: #10B981;
    border-left: 4px solid #10B981;
}

/* ==========================================
   ACTION & UTILITY BUTTONS
   ========================================== */
QPushButton#PrimaryButton {
    background-color: #10B981;
    color: #06281E;
    border: none;
    border-radius: 8px;
    padding: 10px 18px;
    font-weight: 700;
    font-size: 13px;
}

QPushButton#PrimaryButton:hover {
    background-color: #34D399;
}

QPushButton#PrimaryButton:pressed {
    background-color: #059669;
}

QPushButton#SecondaryButton {
    background-color: #27272A;
    color: #E5E7EB;
    border: 1px solid #3F3F46;
    border-radius: 8px;
    padding: 9px 14px;
    font-weight: 600;
    font-size: 12px;
}

QPushButton#SecondaryButton:hover {
    background-color: #3F3F46;
    border-color: #10B981;
    color: #10B981;
}

/* ==========================================
   INPUTS, SEARCH BARS & TEXT AREAS
   ========================================== */
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {
    background-color: #18181B;
    color: #F9FAFB;
    border: 1px solid #27272A;
    border-radius: 8px;
    padding: 10px 14px;
    selection-background-color: #10B981;
    selection-color: #06281E;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #10B981;
    background-color: #1E1E24;
}

/* ==========================================
   CARDS & CONTAINERS
   ========================================== */
QFrame#ContentCard {
    background-color: #18181B;
    border: 1px solid #27272A;
    border-radius: 12px;
}

QFrame#ContentCard:hover {
    border: 1px solid #10B981;
}

/* ==========================================
   SCROLLBARS
   ========================================== */
QScrollArea {
    border: none;
    background-color: transparent;
}

QScrollBar:vertical {
    background: #121212;
    width: 8px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #27272A;
    min-height: 30px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #10B981;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QLabel { background: transparent; }
QLabel#PageTitle { font-size: 27px; font-weight: 700; }
QLabel#DetailTitle { font-size: 21px; font-weight: 600; }
QLabel#MutedLabel { color: #9CA3AF; font-size: 12px; }
QLabel#TagLabel { color: #34D399; font-size: 12px; }
QLabel#ErrorLabel { color: #FCA5A5; }
QLabel#StatsLabel { background: #121212; border: 1px solid #27272A; border-radius: 10px; padding: 14px; color: #A1A1AA; font-size: 12px; }
QFrame#DetailPanel { background: #18181B; border: 1px solid #27272A; border-radius: 12px; }
QPlainTextEdit#CodeEditor { font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 13px; background: #101214; selection-background-color: #065F46; selection-color: #FFFFFF; }
QListWidget { background: #121212; border: 1px solid #27272A; border-radius: 8px; outline: none; padding: 5px; }
QListWidget::item { padding: 12px 10px; border-radius: 6px; }
QListWidget::item:hover { background: #202326; }
QListWidget::item:selected { background: #17392F; color: #ECFDF5; }
QPushButton { background: #27272A; border: 1px solid #3F3F46; border-radius: 7px; padding: 8px 12px; }
QPushButton:hover { border-color: #10B981; background: #303036; }
QPushButton:focus { border-color: #34D399; }
QPushButton:disabled { color: #62626C; background: #202024; border-color: #27272A; }
QPushButton#DangerButton { color: #FCA5A5; }
QPushButton#DangerButton:hover { border-color: #F87171; background: #3A2024; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox::down-arrow { image: url(ASSET_ROOT/chevron.svg); width: 12px; height: 12px; }
QComboBox QAbstractItemView { background: #18181B; color: #F9FAFB; selection-background-color: #065F46; }
QCheckBox { spacing: 8px; background: transparent; }
QCheckBox::indicator, QListWidget::indicator { width: 16px; height: 16px; border: 1px solid #71717A; border-radius: 3px; background: #18181B; }
QCheckBox::indicator:checked, QListWidget::indicator:checked { background: #10B981; border-color: #10B981; image: url(ASSET_ROOT/check.svg); }
QSplitter::handle { background: #27272A; width: 2px; margin: 10px 5px; }
QMenuBar {
    background-color: #18181B;
    color: #E4E4E7;
    border-bottom: 1px solid #27272A;
    padding: 2px 6px;
    font-size: 13px;
}
QMenuBar::item {
    background-color: transparent;
    padding: 6px 12px;
    border-radius: 4px;
}
QMenuBar::item:selected {
    background-color: #27272A;
    color: #10B981;
}
QMenuBar::item:pressed {
    background-color: #10B981;
    color: #06281E;
}
QMenu {
    background-color: #18181B;
    color: #F4F4F5;
    border: 1px solid #27272A;
    border-radius: 8px;
    padding: 6px 0px;
}
QMenu::item {
    padding: 8px 26px 8px 20px;
    border-radius: 4px;
    margin: 2px 6px;
}
QMenu::item:selected {
    background-color: #065F46;
    color: #FFFFFF;
}
QMenu::item:disabled {
    color: #52525B;
}
QMenu::separator {
    height: 1px;
    background-color: #27272A;
    margin: 4px 8px;
}
QStatusBar {
    background-color: #18181B;
    color: #9CA3AF;
    border-top: 1px solid #27272A;
}
QLabel#SidebarContact {
    background: #141416;
    border: 1px solid #27272A;
    border-radius: 8px;
    padding: 10px;
    font-size: 11px;
}
QToolTip { background: #27272A; color: #F9FAFB; border: 1px solid #52525B; padding: 6px; }
""".replace('ASSET_ROOT', ((Path(sys._MEIPASS) / 'assets').as_posix() if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS') else (Path(__file__).resolve().parent.parent / 'assets').as_posix()))
