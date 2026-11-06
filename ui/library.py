"""Searchable library and selectable, copyable item detail view."""

import sqlite3
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QPlainTextEdit, QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from core.database import validate_item
from ui.dialogs import CategoryDialog, ItemDialog


LIBRARIES = {
    'cmd': ('Terminal commands', 'Keep the commands you trust, ready to copy.', 'command'),
    'prompt': ('AI prompts', 'Your best instructions, ready for the next conversation.', 'prompt'),
    'link': ('Links & tutorials', 'A personal index of useful documentation and videos.', 'link'),
}


class LibraryScreen(QWidget):
    changed = Signal()
    notification = Signal(str)

    def __init__(self, db, item_type, parent=None):
        super().__init__(parent)
        self.db, self.item_type = db, item_type
        self.current_item = None
        title, subtitle, self.noun = LIBRARIES[item_type]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 20)
        layout.setSpacing(16)
        header = QHBoxLayout()
        headings = QVBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName('PageTitle')
        headings.addWidget(title_label)
        sub = QLabel(subtitle)
        sub.setObjectName('MutedLabel')
        sub.setWordWrap(True)
        headings.addWidget(sub)
        header.addLayout(headings, 1)
        self.new_button = QPushButton(f'+ New {self.noun}')
        self.new_button.setObjectName('PrimaryButton')
        self.new_button.setToolTip('Create an item (Ctrl+N)')
        self.new_button.clicked.connect(self.new_item)
        header.addWidget(self.new_button)
        layout.addLayout(header)

        self.search = QLineEdit()
        self.search.setPlaceholderText('Search titles, content, descriptions, and categories…')
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName('Search library')
        layout.addWidget(self.search)
        filters = QHBoxLayout()
        self.category_filter = QComboBox()
        self.category_filter.setMinimumWidth(160)
        self.category_filter.setAccessibleName('Filter by category')
        self.favorites = QCheckBox('Favorites only')
        self.sort = QComboBox()
        self.sort.addItems(['Favorites first', 'Recently updated', 'Title A–Z'])
        self.sort.setAccessibleName('Sort items')
        self.manage_button = QPushButton('Categories')
        self.manage_button.clicked.connect(self.manage_categories)
        filters.addWidget(self.category_filter, 1)
        filters.addWidget(self.favorites)
        filters.addWidget(self.sort)
        filters.addWidget(self.manage_button)
        layout.addLayout(filters)
        self.result_label = QLabel()
        self.result_label.setObjectName('MutedLabel')
        layout.addWidget(self.result_label)

        self.splitter = QSplitter(Qt.Horizontal)
        self.items_list = QListWidget()
        self.items_list.setObjectName('ItemList')
        self.items_list.setMinimumWidth(210)
        self.items_list.setWordWrap(True)
        self.items_list.setSpacing(4)
        self.items_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.items_list.setAccessibleName('Saved items')
        self.items_list.currentItemChanged.connect(self.select_item)
        self.items_list.itemDoubleClicked.connect(lambda _: self.edit_item())
        self.splitter.addWidget(self.items_list)
        self.detail = QFrame()
        self.detail.setObjectName('DetailPanel')
        detail_layout = QVBoxLayout(self.detail)
        detail_layout.setContentsMargins(20, 20, 20, 20)
        detail_layout.setSpacing(12)
        self.detail_title = QLabel()
        self.detail_title.setObjectName('DetailTitle')
        self.detail_title.setWordWrap(True)
        self.detail_title.setTextFormat(Qt.PlainText)
        self.detail_title.setTextInteractionFlags(Qt.TextSelectableByMouse)
        detail_layout.addWidget(self.detail_title)
        self.detail_description = QLabel()
        self.detail_description.setWordWrap(True)
        self.detail_description.setTextFormat(Qt.PlainText)
        self.detail_description.setObjectName('MutedLabel')
        detail_layout.addWidget(self.detail_description)
        self.tags = QLabel()
        self.tags.setTextFormat(Qt.PlainText)
        self.tags.setWordWrap(True)
        self.tags.setObjectName('TagLabel')
        detail_layout.addWidget(self.tags)
        self.content = QPlainTextEdit()
        self.content.setReadOnly(True)
        self.content.setObjectName('CodeEditor')
        self.content.setAccessibleName('Item content')
        detail_layout.addWidget(self.content, 1)
        self.updated_label = QLabel()
        self.updated_label.setObjectName('MutedLabel')
        detail_layout.addWidget(self.updated_label)
        primary_actions = QHBoxLayout()
        self.copy_button = QPushButton('Copy content')
        self.copy_button.setObjectName('PrimaryButton')
        self.copy_button.clicked.connect(self.copy_item)
        self.favorite_button = QPushButton('Favorite')
        self.favorite_button.clicked.connect(self.toggle_favorite)
        self.open_button = QPushButton('Open link')
        self.open_button.clicked.connect(self.open_link)
        self.open_button.setVisible(item_type == 'link')
        primary_actions.addWidget(self.copy_button)
        primary_actions.addWidget(self.favorite_button)
        primary_actions.addWidget(self.open_button)
        primary_actions.addStretch()
        detail_layout.addLayout(primary_actions)
        actions = QHBoxLayout()
        self.edit_button = QPushButton('Edit')
        self.edit_button.clicked.connect(self.edit_item)
        self.duplicate_button = QPushButton('Duplicate')
        self.duplicate_button.clicked.connect(self.duplicate_item)
        self.delete_button = QPushButton('Delete')
        self.delete_button.setObjectName('DangerButton')
        self.delete_button.clicked.connect(self.delete_item)
        actions.addWidget(self.edit_button)
        actions.addWidget(self.duplicate_button)
        actions.addStretch()
        actions.addWidget(self.delete_button)
        detail_layout.addLayout(actions)
        self.splitter.addWidget(self.detail)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setSizes([340, 580])
        layout.addWidget(self.splitter, 1)

        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(180)
        self.search_timer.timeout.connect(self.refresh_items)
        self.search.textChanged.connect(lambda: self.search_timer.start())
        self.category_filter.currentIndexChanged.connect(self.refresh_items)
        self.favorites.toggled.connect(self.refresh_items)
        self.sort.currentIndexChanged.connect(self.refresh_items)
        self.refresh()

    def refresh(self, selected_uuid=None):
        category_id = self.category_filter.currentData()
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem('All categories', None)
        for cat in self.db.get_categories(self.item_type):
            suffix = ' · shared' if cat['scope'] == 'global' else ''
            self.category_filter.addItem(f"{cat['name']}{suffix} ({cat['item_count']})", cat['id'])
        self.category_filter.setCurrentIndex(max(0, self.category_filter.findData(category_id)))
        self.category_filter.blockSignals(False)
        self.refresh_items(selected_uuid=selected_uuid)

    def refresh_items(self, *_, selected_uuid=None):
        selected_uuid = selected_uuid or (self.current_item['uuid'] if self.current_item else None)
        cat = self.category_filter.currentData()
        try:
            items = self.db.get_items(self.item_type, self.search.text(), [cat] if cat is not None else None, self.favorites.isChecked())
        except sqlite3.Error as error:
            QMessageBox.warning(self, 'Could not load library', str(error))
            return
        if self.sort.currentIndex() == 1:
            items.sort(key=lambda item: datetime.fromisoformat(item['updated_at']).timestamp(), reverse=True)
        elif self.sort.currentIndex() == 2:
            items.sort(key=lambda item: item['title'].casefold())
        self.items_list.clear()
        selected_row = 0
        for index, item in enumerate(items):
            prefix = '★  ' if item['is_favorite'] else ''
            preview = ' '.join((item['description'] or item['content']).split())
            entry = QListWidgetItem(f"{prefix}{item['title']}\n{preview[:90]}{'…' if len(preview) > 90 else ''}")
            entry.setData(Qt.UserRole, item)
            entry.setToolTip(item['title'])
            self.items_list.addItem(entry)
            if item['uuid'] == selected_uuid:
                selected_row = index
        self.result_label.setText(f"{len(items)} {'item' if len(items) == 1 else 'items'} · Double-click to edit")
        if items:
            self.items_list.setCurrentRow(selected_row)
        else:
            self.select_item(None)

    def select_item(self, entry, *_):
        self.current_item = entry.data(Qt.UserRole) if entry else None
        for button in (self.copy_button, self.favorite_button, self.edit_button, self.duplicate_button, self.delete_button, self.open_button):
            button.setEnabled(bool(entry))
        self.content.setVisible(bool(entry))
        if not entry:
            filtered = self.search.text().strip() or self.category_filter.currentData() is not None or self.favorites.isChecked()
            self.detail_title.setText('No matching items' if filtered else f'Your {self.noun} library starts here')
            self.detail_description.setText('Try another search or clear the filters.' if filtered else f'Use “New {self.noun}” to save your first item.')
            self.tags.clear()
            self.content.clear()
            self.updated_label.clear()
            return
        item = self.current_item
        self.detail_title.setText(item['title'])
        self.detail_description.setText(item['description'])
        self.tags.setText('  ·  '.join(c['name'] for c in item['categories']) or 'Uncategorized')
        self.content.setPlainText(item['content'])
        self.favorite_button.setText('★ Favorited' if item['is_favorite'] else '☆ Favorite')
        try:
            updated = datetime.fromisoformat(item['updated_at']).astimezone().strftime('%d %b %Y, %H:%M')
        except ValueError:
            updated = item['updated_at']
        self.updated_label.setText(f'Updated {updated}')

    def after_change(self, message, selected_uuid=None):
        self.changed.emit()
        self.refresh(selected_uuid)
        self.notification.emit(message)

    def edit_dialog(self, item=None):
        dialog = ItemDialog(self.db, self.item_type, self, item)
        if dialog.exec() == QDialog.Accepted:
            self.search.clear()
            self.favorites.setChecked(False)
            self.category_filter.setCurrentIndex(0)
            self.after_change('Item saved', dialog.saved_uuid)

    def new_item(self):
        self.edit_dialog()

    def edit_item(self):
        if self.current_item:
            self.edit_dialog(self.current_item)

    def copy_item(self):
        if self.current_item:
            QApplication.clipboard().setText(self.current_item['content'])
            self.notification.emit('Copied to clipboard')

    def perform(self, action, message):
        try:
            result = action()
        except (ValueError, sqlite3.Error) as error:
            QMessageBox.warning(self, 'Could not save change', str(error))
            return
        self.after_change(message, result if isinstance(result, str) else None)

    def toggle_favorite(self):
        if self.current_item:
            self.perform(lambda: self.db.toggle_favorite(self.current_item['uuid']), 'Favorite updated')

    def duplicate_item(self):
        if self.current_item:
            item = self.current_item
            self.perform(lambda: self.db.add_item(self.item_type, item['title'] + ' (copy)', item['content'],
                         item['description'], is_favorite=bool(item['is_favorite']),
                         category_ids=[c['id'] for c in item['categories']]), 'Item duplicated')

    def delete_item(self):
        if not self.current_item:
            return
        if QMessageBox.question(self, 'Delete item?', f"Permanently delete “{self.current_item['title']}”?",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.perform(lambda: self.db.delete_item(self.current_item['uuid']), 'Item deleted')

    def open_link(self):
        if not self.current_item:
            return
        try:
            validate_item('link', self.current_item['title'], self.current_item['content'])
        except ValueError as error:
            QMessageBox.warning(self, 'Invalid link', str(error))
            return
        if not QDesktopServices.openUrl(QUrl(self.current_item['content'].strip())):
            QMessageBox.warning(self, 'Could not open link', 'Your browser could not open this URL. You can copy it instead.')

    def manage_categories(self):
        dialog = CategoryDialog(self.db, self.item_type, self)
        dialog.changed.connect(lambda: self.after_change('Categories updated'))
        dialog.exec()
