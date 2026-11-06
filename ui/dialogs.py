"""Editors shared by the three libraries."""

import sqlite3

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout,
)


class ItemDialog(QDialog):
    def __init__(self, db, item_type, parent=None, item=None):
        super().__init__(parent)
        self.db, self.item_type, self.item = db, item_type, item
        self.saved_uuid = None
        noun = {'cmd': 'command', 'prompt': 'prompt', 'link': 'link'}[item_type]
        self.setWindowTitle(f"{'Edit' if item else 'New'} {noun}")
        self.resize(680, 720)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        form = QFormLayout()
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText('Give this a clear, memorable title')
        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText('When is this useful? (optional)')
        self.content_input = QPlainTextEdit()
        self.content_input.setMinimumHeight(180)
        self.content_input.setPlaceholderText('https://example.com' if item_type == 'link' else 'Paste your reusable content here…')
        self.content_input.setObjectName('CodeEditor')
        self.content_input.setTabChangesFocus(True)
        form.addRow('Title', self.title_input)
        form.addRow('Description', self.description_input)
        form.addRow('URL' if item_type == 'link' else 'Content', self.content_input)
        layout.addLayout(form)
        layout.addWidget(QLabel('Categories'))
        self.categories = QListWidget()
        self.categories.setMaximumHeight(130)
        selected = {c['id'] for c in item['categories']} if item else set()
        for cat in db.get_categories(item_type):
            self.add_category_row(cat['name'], cat['id'] in selected, cat['id'], cat['scope'])
        layout.addWidget(self.categories)
        row = QHBoxLayout()
        self.category_input = QLineEdit()
        self.category_input.setPlaceholderText('New category')
        add = QPushButton('Add category')
        add.clicked.connect(self.add_category)
        row.addWidget(self.category_input)
        row.addWidget(add)
        layout.addLayout(row)
        self.favorite = QCheckBox('Add to favorites')
        layout.addWidget(self.favorite)
        self.error_label = QLabel()
        self.error_label.setObjectName('ErrorLabel')
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setObjectName('PrimaryButton')
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if item:
            self.title_input.setText(item['title'])
            self.description_input.setText(item['description'])
            self.content_input.setPlainText(item['content'])
            self.favorite.setChecked(bool(item['is_favorite']))
        self.initial_state = self.state()
        self.title_input.setFocus()

    def add_category_row(self, name, checked, category_id=None, scope=None):
        entry = QListWidgetItem(name + (' · shared' if scope == 'global' else ''))
        entry.setData(Qt.UserRole, (category_id, name))
        entry.setFlags(entry.flags() | Qt.ItemIsUserCheckable)
        entry.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.categories.addItem(entry)

    def add_category(self):
        name = self.category_input.text().strip()
        if not name:
            return
        for i in range(self.categories.count()):
            entry = self.categories.item(i)
            if entry.data(Qt.UserRole)[1].casefold() == name.casefold():
                entry.setCheckState(Qt.Checked)
                self.category_input.clear()
                return
        self.add_category_row(name, True)
        self.category_input.clear()

    def state(self):
        names = [self.categories.item(i).data(Qt.UserRole) for i in range(self.categories.count())
                 if self.categories.item(i).checkState() == Qt.Checked]
        return (self.title_input.text(), self.content_input.toPlainText(),
                self.description_input.text(), names, self.favorite.isChecked(), self.category_input.text())

    def save(self):
        self.add_category()
        title, content, description, categories, favorite, _ = self.state()
        names = [name for identifier, name in categories if identifier is None]
        ids = [identifier for identifier, name in categories if identifier is not None]
        try:
            if self.item:
                self.db.update_item(self.item['uuid'], title, content, description, names, favorite, category_ids=ids)
                self.saved_uuid = self.item['uuid']
            else:
                self.saved_uuid = self.db.add_item(self.item_type, title, content, description, names, favorite, category_ids=ids)
        except (ValueError, sqlite3.Error) as error:
            self.error_label.setText(str(error))
            return
        self.accept()

    def reject(self):
        if self.state() != self.initial_state:
            answer = QMessageBox.question(self, 'Discard changes?', 'Your unsaved changes will be lost.',
                                          QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel)
            if answer != QMessageBox.Discard:
                return
        super().reject()


class CategoryDialog(QDialog):
    changed = Signal()

    def __init__(self, db, item_type, parent=None):
        super().__init__(parent)
        self.db, self.item_type = db, item_type
        self.setWindowTitle('Manage categories')
        self.resize(540, 460)
        layout = QVBoxLayout(self)
        hint = QLabel('Categories organize your library. Removing a category keeps its saved items.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.list = QListWidget()
        layout.addWidget(self.list)
        row = QHBoxLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText('Category name')
        self.scope = QComboBox()
        self.scope.addItem('This library', item_type)
        self.scope.addItem('All libraries', 'global')
        add = QPushButton('Add')
        add.clicked.connect(self.add)
        row.addWidget(self.name_input)
        row.addWidget(self.scope)
        row.addWidget(add)
        layout.addLayout(row)
        actions = QHBoxLayout()
        self.rename_button = QPushButton('Rename')
        self.delete_button = QPushButton('Remove')
        self.rename_button.clicked.connect(self.rename)
        self.delete_button.clicked.connect(self.delete)
        actions.addWidget(self.rename_button)
        actions.addWidget(self.delete_button)
        actions.addStretch()
        close = QPushButton('Done')
        close.clicked.connect(self.accept)
        actions.addWidget(close)
        layout.addLayout(actions)
        self.list.currentItemChanged.connect(self.update_actions)
        self.refresh()

    def refresh(self):
        self.list.clear()
        for cat in self.db.get_categories(self.item_type):
            scope = 'all libraries' if cat['scope'] == 'global' else 'this library'
            entry = QListWidgetItem(f"{cat['name']}  ·  {cat['item_count']} items  ·  {scope}")
            entry.setData(Qt.UserRole, cat)
            self.list.addItem(entry)
        self.update_actions()

    def update_actions(self, *_):
        enabled = self.list.currentItem() is not None
        self.rename_button.setEnabled(enabled)
        self.delete_button.setEnabled(enabled)

    def perform(self, action):
        try:
            action()
        except (ValueError, sqlite3.Error) as error:
            QMessageBox.warning(self, 'Could not update category', str(error))
            return
        self.refresh()
        self.changed.emit()

    def add(self):
        self.perform(lambda: self.db.add_category(self.name_input.text(), self.scope.currentData()))
        self.name_input.clear()

    def rename(self):
        entry = self.list.currentItem()
        if not entry:
            return
        cat = entry.data(Qt.UserRole)
        name, ok = QInputDialog.getText(self, 'Rename category', 'Name', text=cat['name'])
        if ok:
            self.perform(lambda: self.db.rename_category(cat['id'], name))

    def delete(self):
        entry = self.list.currentItem()
        if not entry:
            return
        cat = entry.data(Qt.UserRole)
        if QMessageBox.question(self, 'Remove category?', f"Remove “{cat['name']}” from all associated items? The items will be kept.",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.perform(lambda: self.db.delete_category(cat['id']))


class ContactDialog(QDialog):
    """Dialog providing reach-out channels (official website and email)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Contact & Support — Pro Dash')
        self.resize(520, 500)
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        header_title = QLabel('How to Reach Us')
        header_title.setObjectName('DetailTitle')
        layout.addWidget(header_title)

        header_desc = QLabel(
            'Need help, want to suggest a feature, or have feedback? '
            'Connect with our team via our website or direct email.'
        )
        header_desc.setObjectName('MutedLabel')
        header_desc.setWordWrap(True)
        layout.addWidget(header_desc)

        # Website card
        site_card = QFrame()
        site_card.setObjectName('ContentCard')
        site_layout = QVBoxLayout(site_card)
        site_layout.setContentsMargins(16, 14, 16, 14)
        site_layout.setSpacing(8)

        site_label = QLabel('🌐  OFFICIAL WEBSITE')
        site_label.setObjectName('SectionHeader')
        site_layout.addWidget(site_label)

        site_link = QLabel('<a href="https://team.qrtoba.com" style="color: #10B981; font-size: 15px; font-weight: 600; text-decoration: none;">team.qrtoba.com</a>')
        site_link.setOpenExternalLinks(True)
        site_layout.addWidget(site_link)

        site_buttons = QHBoxLayout()
        self.btn_open_site = QPushButton('Open website')
        self.btn_open_site.setObjectName('SecondaryButton')
        self.btn_open_site.clicked.connect(self.open_website)
        self.btn_copy_site = QPushButton('Copy URL')
        self.btn_copy_site.setObjectName('SecondaryButton')
        self.btn_copy_site.clicked.connect(self.copy_website)
        site_buttons.addWidget(self.btn_open_site)
        site_buttons.addWidget(self.btn_copy_site)
        site_buttons.addStretch()
        site_layout.addLayout(site_buttons)
        layout.addWidget(site_card)

        # Email card
        email_card = QFrame()
        email_card.setObjectName('ContentCard')
        email_layout = QVBoxLayout(email_card)
        email_layout.setContentsMargins(16, 14, 16, 14)
        email_layout.setSpacing(8)

        email_label = QLabel('✉️  SUPPORT EMAIL')
        email_label.setObjectName('SectionHeader')
        email_layout.addWidget(email_label)

        email_link = QLabel('<a href="mailto:qrtobacom@gmail.com?subject=Pro%20Dash%20Inquiry" style="color: #10B981; font-size: 15px; font-weight: 600; text-decoration: none;">qrtobacom@gmail.com</a>')
        email_link.setOpenExternalLinks(True)
        email_layout.addWidget(email_link)

        email_buttons = QHBoxLayout()
        self.btn_send_email = QPushButton('Send email')
        self.btn_send_email.setObjectName('SecondaryButton')
        self.btn_send_email.clicked.connect(self.send_email)
        self.btn_copy_email = QPushButton('Copy email')
        self.btn_copy_email.setObjectName('SecondaryButton')
        self.btn_copy_email.clicked.connect(self.copy_email)
        email_buttons.addWidget(self.btn_send_email)
        email_buttons.addWidget(self.btn_copy_email)
        email_buttons.addStretch()
        email_layout.addLayout(email_buttons)
        layout.addWidget(email_card)

        # Patreon card
        patreon_card = QFrame()
        patreon_card.setObjectName('ContentCard')
        patreon_layout = QVBoxLayout(patreon_card)
        patreon_layout.setContentsMargins(16, 14, 16, 14)
        patreon_layout.setSpacing(8)

        patreon_label = QLabel('🎨  PATREON & CREATOR')
        patreon_label.setObjectName('SectionHeader')
        patreon_layout.addWidget(patreon_label)

        patreon_link = QLabel('<a href="https://www.patreon.com/c/altohamy" style="color: #10B981; font-size: 15px; font-weight: 600; text-decoration: none;">kamel altohamy | Patreon</a>')
        patreon_link.setOpenExternalLinks(True)
        patreon_layout.addWidget(patreon_link)

        patreon_buttons = QHBoxLayout()
        self.btn_open_patreon = QPushButton('Open Patreon')
        self.btn_open_patreon.setObjectName('SecondaryButton')
        self.btn_open_patreon.clicked.connect(self.open_patreon)
        self.btn_copy_patreon = QPushButton('Copy Patreon URL')
        self.btn_copy_patreon.setObjectName('SecondaryButton')
        self.btn_copy_patreon.clicked.connect(self.copy_patreon)
        patreon_buttons.addWidget(self.btn_open_patreon)
        patreon_buttons.addWidget(self.btn_copy_patreon)
        patreon_buttons.addStretch()
        patreon_layout.addLayout(patreon_buttons)
        layout.addWidget(patreon_card)

        # Status feedback label
        self.status_label = QLabel()
        self.status_label.setObjectName('TagLabel')
        layout.addWidget(self.status_label)

        layout.addStretch()
        bottom_bar = QHBoxLayout()
        bottom_bar.addStretch()
        close_btn = QPushButton('Close')
        close_btn.setObjectName('PrimaryButton')
        close_btn.clicked.connect(self.accept)
        bottom_bar.addWidget(close_btn)
        layout.addLayout(bottom_bar)

    def open_website(self):
        if not QDesktopServices.openUrl(QUrl('https://team.qrtoba.com')):
            self.copy_website()
            self.status_label.setText('Browser could not be opened. Copied https://team.qrtoba.com to clipboard.')
        else:
            self.status_label.setText('Opening team.qrtoba.com in your browser…')

    def copy_website(self):
        app = QApplication.instance()
        if app:
            app.clipboard().setText('https://team.qrtoba.com')
        self.status_label.setText('✓ Copied https://team.qrtoba.com to clipboard')

    def send_email(self):
        if not QDesktopServices.openUrl(QUrl('mailto:qrtobacom@gmail.com?subject=Pro%20Dash%20Inquiry')):
            self.copy_email()
            self.status_label.setText('Email client not found. Copied qrtobacom@gmail.com to clipboard.')
        else:
            self.status_label.setText('Opening email client for qrtobacom@gmail.com…')

    def copy_email(self):
        app = QApplication.instance()
        if app:
            app.clipboard().setText('qrtobacom@gmail.com')
        self.status_label.setText('✓ Copied qrtobacom@gmail.com to clipboard')

    def open_patreon(self):
        if not QDesktopServices.openUrl(QUrl('https://www.patreon.com/c/altohamy')):
            self.copy_patreon()
            self.status_label.setText('Browser could not be opened. Copied Patreon link to clipboard.')
        else:
            self.status_label.setText('Opening Kamel Altohamy Patreon in your browser…')

    def copy_patreon(self):
        app = QApplication.instance()
        if app:
            app.clipboard().setText('https://www.patreon.com/c/altohamy')
        self.status_label.setText('✓ Copied https://www.patreon.com/c/altohamy to clipboard')

