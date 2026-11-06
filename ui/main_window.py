"""Application shell, portability actions, and persistent workspace preferences."""

import json
import os
import sqlite3
import tempfile
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QMainWindow, QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from ui.dialogs import ContactDialog
from ui.library import LibraryScreen


class ProDashMainWindow(QMainWindow):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.settings = QSettings(str(Path(db.db_path).resolve().parent / 'preferences.ini'), QSettings.IniFormat)
        self.setWindowTitle('Pro Dash — Developer workspace')
        self.resize(1280, 820)
        self.setMinimumSize(1080, 680)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.sidebar = self.build_sidebar()
        layout.addWidget(self.sidebar)
        self.stack = QStackedWidget()
        self.screens = [LibraryScreen(db, item_type) for item_type in ('cmd', 'prompt', 'link')]
        self.cmd_screen, self.prompt_screen, self.links_screen = self.screens
        for screen in self.screens:
            screen.changed.connect(self.refresh_all)
            screen.notification.connect(self.show_toast)
            self.stack.addWidget(screen)
        layout.addWidget(self.stack, 1)
        self.statusBar().showMessage('Ready · Your library is saved locally')
        local_label = QLabel('LOCAL WORKSPACE')
        local_label.setObjectName('MutedLabel')
        local_label.setToolTip(f'Database: {db.db_path}')
        self.statusBar().addPermanentWidget(local_label)
        self.create_actions()
        self.restore_preferences()
        self.refresh_sidebar_stats()

    def build_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName('Sidebar')
        sidebar.setFixedWidth(238)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 22, 18, 16)
        layout.setSpacing(8)
        brand = QLabel('PRO DASH')
        brand.setObjectName('BrandTitle')
        layout.addWidget(brand)
        subtitle = QLabel('YOUR DEVELOPER WORKSPACE')
        subtitle.setObjectName('BrandSubtitle')
        layout.addWidget(subtitle)
        layout.addSpacing(14)
        heading = QLabel('LIBRARIES')
        heading.setObjectName('SectionHeader')
        layout.addWidget(heading)
        self.nav_group = QButtonGroup(self)
        for index, title in enumerate(('>_  Commands', '✦   AI prompts', '↗   Links & tutorials')):
            button = QPushButton(title)
            button.setProperty('class', 'NavButton')
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            self.nav_group.addButton(button, index)
            layout.addWidget(button)
        self.nav_group.idClicked.connect(self.switch_screen)
        layout.addStretch()
        self.stats_label = QLabel()
        self.stats_label.setObjectName('StatsLabel')
        layout.addWidget(self.stats_label)
        heading = QLabel('TAKE YOUR LIBRARY WITH YOU')
        heading.setObjectName('SectionHeader')
        layout.addWidget(heading)
        self.btn_import = QPushButton('Import pack')
        self.btn_import.clicked.connect(self.import_pack)
        self.btn_export = QPushButton('Export library')
        self.btn_export.clicked.connect(self.export_pack)
        layout.addWidget(self.btn_import)
        layout.addWidget(self.btn_export)
        shortcuts = QLabel('Ctrl+N  New item\nCtrl+F  Search library\nCtrl+Shift+C  Copy item')
        shortcuts.setObjectName('MutedLabel')
        layout.addSpacing(8)
        layout.addWidget(shortcuts)
        layout.addSpacing(6)
        contact_card = QLabel(
            '<span style="color: #6B7280; font-size: 10px; font-weight: 700; letter-spacing: 1px;">REACH US</span><br>'
            '🌐 <a href="https://team.qrtoba.com" style="color: #10B981; text-decoration: none;">team.qrtoba.com</a><br>'
            '🎨 <a href="https://www.patreon.com/c/altohamy" style="color: #10B981; text-decoration: none;">Patreon / altohamy</a><br>'
            '✉️ <a href="mailto:qrtobacom@gmail.com" style="color: #9CA3AF; text-decoration: none;">qrtobacom@gmail.com</a>'
        )
        contact_card.setOpenExternalLinks(True)
        contact_card.setTextFormat(Qt.RichText)
        contact_card.setObjectName('SidebarContact')
        layout.addWidget(contact_card)
        return sidebar

    def create_actions(self):
        def action(menu, text, shortcut=None, callback=None, status_tip=None):
            item = QAction(text, self)
            if shortcut:
                item.setShortcut(QKeySequence(shortcut))
            if status_tip:
                item.setStatusTip(status_tip)
            if callback:
                item.triggered.connect(callback)
            menu.addAction(item)
            return item

        # File Menu
        file_menu = self.menuBar().addMenu('&File')
        action(file_menu, '&New item', 'Ctrl+N', lambda: self.stack.currentWidget().new_item(), 'Create a new item in the current library')
        file_menu.addSeparator()
        action(file_menu, '&Import pack…', 'Ctrl+O', self.import_pack, 'Import library items from a JSON pack')
        action(file_menu, '&Export library…', 'Ctrl+Shift+S', self.export_pack, 'Export the entire library to a portable JSON pack')
        file_menu.addSeparator()
        action(file_menu, 'E&xit', 'Ctrl+Q', self.close, 'Exit Pro Dash')

        # Edit Menu
        edit_menu = self.menuBar().addMenu('&Edit')
        action(edit_menu, '&Search', 'Ctrl+F', self.focus_search, 'Jump to search filter')
        edit_menu.addSeparator()
        action(edit_menu, '&Edit selected item', 'Ctrl+E', lambda: self.stack.currentWidget().edit_item(), 'Edit the selected library item')
        action(edit_menu, '&Duplicate selected item', 'Ctrl+D', lambda: self.stack.currentWidget().duplicate_item(), 'Duplicate the selected item')
        action(edit_menu, '&Copy selected content', 'Ctrl+Shift+C', lambda: self.stack.currentWidget().copy_item(), 'Copy item content to clipboard')
        action(edit_menu, 'Toggle &favorite', 'Ctrl+B', lambda: self.stack.currentWidget().toggle_favorite(), 'Toggle favorite status on selected item')
        action(edit_menu, '&Delete selected item', 'Delete', lambda: self.stack.currentWidget().delete_item(), 'Delete the selected item')
        edit_menu.addSeparator()
        action(edit_menu, 'Manage &categories…', None, lambda: self.stack.currentWidget().manage_categories(), 'Create, rename, or delete categories')

        # View Menu
        view_menu = self.menuBar().addMenu('&View')
        for index, name in enumerate(('Commands', 'AI prompts', 'Links & tutorials')):
            action(view_menu, name, f'Ctrl+{index + 1}', lambda checked=False, i=index: self.switch_screen(i), f'Switch to {name} library')
        view_menu.addSeparator()
        action(view_menu, '&Refresh library', 'F5', self.refresh_all, 'Refresh items and recalculate library statistics')

        # Help Menu
        help_menu = self.menuBar().addMenu('&Help')
        action(help_menu, 'Visit &Website (team.qrtoba.com)', None, self.open_website, 'Open team.qrtoba.com in your default browser')
        action(help_menu, '&Support on Patreon (Kamel Altohamy)', None, self.open_patreon, 'Visit Kamel Altohamy Patreon page')
        action(help_menu, '&Email Support (qrtobacom@gmail.com)', None, self.open_email, 'Send an email to qrtobacom@gmail.com')
        action(help_menu, '&Copy Support Email', None, self.copy_support_email, 'Copy qrtobacom@gmail.com to clipboard')
        help_menu.addSeparator()
        action(help_menu, '&Contact & Support…', None, self.contact_us, 'How to reach us: website, Patreon, and email')
        help_menu.addSeparator()
        action(help_menu, '&About Pro Dash', None, self.about, 'About Pro Dash and support contact details')

    def focus_search(self):
        self.stack.currentWidget().search.setFocus()
        self.stack.currentWidget().search.selectAll()

    def switch_screen(self, index):
        self.stack.setCurrentIndex(index)
        self.nav_group.button(index).setChecked(True)

    def refresh_sidebar_stats(self):
        stats = self.db.get_stats()
        self.stats_label.setText(f"YOUR LIBRARY\n\n{stats.get('cmd', 0)} commands · {stats.get('prompt', 0)} prompts\n"
                                 f"{stats.get('link', 0)} links · {stats['categories']} categories")
        self.stats_label.setMinimumHeight(self.stats_label.sizeHint().height())

    def refresh_all(self):
        for screen in self.screens:
            screen.refresh()
        self.refresh_sidebar_stats()

    def show_toast(self, message, duration_ms=4000):
        self.statusBar().showMessage(message, duration_ms)

    def export_pack(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Export your complete library', 'pro-dash-library.json', 'Pro Dash packs (*.json)')
        if not path:
            return
        if not Path(path).suffix:
            path += '.json'
        temporary = None
        try:
            pack = self.db.export_pack()
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=Path(path).parent,
                                             prefix='.pro-dash-', suffix='.tmp', delete=False) as handle:
                temporary = handle.name
                json.dump(pack, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except (OSError, sqlite3.Error) as error:
            QMessageBox.warning(self, 'Export failed', str(error))
            return
        finally:
            if temporary and os.path.exists(temporary):
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
        self.show_toast(f"Exported {len(pack['items'])} items to {Path(path).name}")

    def import_pack(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Import a Pro Dash pack', '', 'Pro Dash packs (*.json)')
        if not path:
            return
        try:
            with open(path, 'rb') as handle:
                data = handle.read(20 * 1024 * 1024 + 1)
            if len(data) > 20 * 1024 * 1024:
                raise ValueError('This pack exceeds the 20 MB import limit.')
            imported, skipped = self.db.import_pack(json.loads(data.decode('utf-8-sig')))
        except (OSError, ValueError, sqlite3.Error, RecursionError) as error:
            QMessageBox.warning(self, 'Import failed', f'No items were imported.\n\n{error}')
            return
        self.refresh_all()
        QMessageBox.information(self, 'Import complete',
                                f'Added {imported} items.\nKept {skipped} existing items unchanged (matching IDs).')
        self.show_toast(f'Imported {imported} items')

    def restore_preferences(self):
        geometry = self.settings.value('window/geometry')
        if geometry:
            self.restoreGeometry(geometry)
        try:
            index = int(self.settings.value('window/library', 0))
        except (ValueError, TypeError):
            index = 0
        self.switch_screen(index if index in range(3) else 0)
        for screen in self.screens:
            state = self.settings.value(f'{screen.item_type}/splitter')
            if state:
                screen.splitter.restoreState(state)

    def closeEvent(self, event):
        self.settings.setValue('window/geometry', self.saveGeometry())
        self.settings.setValue('window/library', self.stack.currentIndex())
        for screen in self.screens:
            self.settings.setValue(f'{screen.item_type}/splitter', screen.splitter.saveState())
        self.settings.sync()
        super().closeEvent(event)

    def open_website(self):
        url = QUrl('https://team.qrtoba.com')
        if not QDesktopServices.openUrl(url):
            QApplication.clipboard().setText('https://team.qrtoba.com')
            self.show_toast('Browser could not open URL. Copied https://team.qrtoba.com to clipboard')
        else:
            self.show_toast('Opening team.qrtoba.com in browser…')

    def open_email(self):
        url = QUrl('mailto:qrtobacom@gmail.com?subject=Pro%20Dash%20Inquiry')
        if not QDesktopServices.openUrl(url):
            QApplication.clipboard().setText('qrtobacom@gmail.com')
            self.show_toast('No email client found. Copied qrtobacom@gmail.com to clipboard')
        else:
            self.show_toast('Opening email client for qrtobacom@gmail.com…')

    def copy_support_email(self):
        QApplication.clipboard().setText('qrtobacom@gmail.com')
        self.show_toast('Copied support email to clipboard: qrtobacom@gmail.com')

    def open_patreon(self):
        url = QUrl('https://www.patreon.com/c/altohamy')
        if not QDesktopServices.openUrl(url):
            QApplication.clipboard().setText('https://www.patreon.com/c/altohamy')
            self.show_toast('Browser could not open URL. Copied https://www.patreon.com/c/altohamy to clipboard')
        else:
            self.show_toast('Opening Kamel Altohamy Patreon in browser…')

    def contact_us(self):
        dialog = ContactDialog(self)
        dialog.exec()

    def about(self):
        QMessageBox.about(
            self,
            'About Pro Dash',
            '<b>Pro Dash 1.0</b><br><br>'
            'Your local command, prompt, and bookmark library.<br>'
            'Commands are stored and copied; they are never executed by this app.<br><br>'
            '<b>How to reach us & support:</b><br>'
            '• Website: <a href="https://team.qrtoba.com" style="color: #10B981;">team.qrtoba.com</a><br>'
            '• Patreon: <a href="https://www.patreon.com/c/altohamy" style="color: #10B981;">kamel altohamy</a><br>'
            '• Email: <a href="mailto:qrtobacom@gmail.com" style="color: #10B981;">qrtobacom@gmail.com</a><br><br>'
            'Export your library regularly to keep a portable backup.<br><br>'
            f'<small style="color: #9CA3AF;">Database: {self.db.db_path}</small>'
        )
