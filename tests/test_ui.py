import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from core.database import DatabaseManager
from ui.dialogs import ItemDialog, ContactDialog
from ui.main_window import ProDashMainWindow
from ui.theme import PRO_DASH_STYLE


class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')
        cls.app.setStyleSheet(PRO_DASH_STYLE)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = DatabaseManager(str(Path(self.tmp.name) / 'test.db'))
        self.db.seed_initial_data()
        self.window = ProDashMainWindow(self.db)
        self.window.show()
        self.app.processEvents()
        self.addCleanup(self.window.close)

    def test_search_navigation_copy_favorite_and_duplicate(self):
        screen = self.window.cmd_screen
        self.assertEqual(screen.items_list.count(), 3)
        screen.search.setText('8000')
        QTest.qWait(250)
        self.assertEqual(screen.items_list.count(), 1)
        QTest.mouseClick(screen.copy_button, Qt.LeftButton)
        self.assertEqual(self.app.clipboard().text(), 'sudo lsof -i :8000')
        QTest.mouseClick(screen.favorite_button, Qt.LeftButton)
        self.assertTrue(screen.current_item['is_favorite'])
        QTest.mouseClick(screen.duplicate_button, Qt.LeftButton)
        self.assertEqual(screen.items_list.count(), 2)
        QTest.mouseClick(self.window.nav_group.button(2), Qt.LeftButton)
        self.assertEqual(self.window.stack.currentIndex(), 2)
        self.assertFalse(self.window.links_screen.copy_button.isEnabled())

    def test_editor_validation_save_and_exact_categories(self):
        shared = self.db.add_category('Python', 'global')
        scoped = self.db.add_category('Python', 'prompt')
        identifier = self.db.add_item('prompt', 'Test', '  content\n', category_ids=[shared])
        item = next(i for i in self.db.get_items('prompt') if i['uuid'] == identifier)
        dialog = ItemDialog(self.db, 'prompt', self.window, item)
        dialog.title_input.setText(' ')
        dialog.save()
        self.assertEqual(dialog.result(), QDialog.Rejected)
        self.assertTrue(dialog.error_label.text())
        dialog.title_input.setText('Edited')
        dialog.save()
        self.assertEqual(dialog.result(), QDialog.Accepted)
        saved = next(i for i in self.db.get_items('prompt') if i['uuid'] == identifier)
        self.assertEqual([c['id'] for c in saved['categories']], [shared])
        self.assertNotEqual(shared, scoped)
        self.assertEqual(saved['content'], '  content\n')

    def test_new_link_validation_and_browser_action(self):
        dialog = ItemDialog(self.db, 'link', self.window)
        dialog.title_input.setText('Docs')
        dialog.content_input.setPlainText('javascript:alert(1)')
        dialog.save()
        self.assertTrue(dialog.error_label.text())
        dialog.content_input.setPlainText('https://example.com/docs')
        dialog.category_input.setText('Resources')
        dialog.save()
        self.assertEqual(dialog.result(), QDialog.Accepted)
        self.window.refresh_all()
        with patch('ui.library.QDesktopServices.openUrl', return_value=True) as opened:
            self.window.links_screen.open_link()
        self.assertEqual(opened.call_args.args[0].toString(), 'https://example.com/docs')

    def test_unsaved_edits_and_delete_require_explicit_choice(self):
        dialog = ItemDialog(self.db, 'cmd', self.window)
        dialog.show()
        dialog.title_input.setText('Unsaved')
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Cancel):
            dialog.reject()
        self.assertTrue(dialog.isVisible())
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Discard):
            dialog.reject()
        self.assertFalse(dialog.isVisible())
        screen = self.window.cmd_screen
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.No):
            screen.delete_item()
        self.assertEqual(len(self.db.get_items('cmd')), 3)
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            screen.delete_item()
        self.assertEqual(len(self.db.get_items('cmd')), 2)

    def test_export_import_and_invalid_file(self):
        target = str(Path(self.tmp.name) / 'backup.json')
        with patch('ui.main_window.QFileDialog.getSaveFileName', return_value=(target, '')):
            self.window.export_pack()
        pack = json.loads(Path(target).read_text(encoding='utf-8'))
        self.assertEqual(len(pack['items']), 5)
        for item in pack['items']:
            self.db.delete_item(item['uuid'])
        with patch('ui.main_window.QFileDialog.getOpenFileName', return_value=(target, '')), \
             patch.object(QMessageBox, 'information'):
            self.window.import_pack()
        self.assertEqual(len(self.db.export_pack()['items']), 5)
        Path(target).write_text('{broken', encoding='utf-8')
        with patch('ui.main_window.QFileDialog.getOpenFileName', return_value=(target, '')), \
             patch.object(QMessageBox, 'warning') as warning:
            self.window.import_pack()
        warning.assert_called_once()
        self.assertEqual(len(self.db.export_pack()['items']), 5)

    def test_window_preferences(self):
        self.window.switch_screen(1)
        self.window.close()
        reopened = ProDashMainWindow(self.db)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.stack.currentIndex(), 1)

    def test_reach_us_menu_actions_and_links(self):
        # Verify Help menu actions
        menus = {m.title(): m for m in self.window.menuBar().findChildren(unittest.mock.MagicMock)}
        help_actions = [a.text() for a in self.window.menuBar().actions() if a.menu() and a.text() == '&Help'][0]
        # Test website opening and fallback
        with patch('PySide6.QtGui.QDesktopServices.openUrl', return_value=True) as opened:
            self.window.open_website()
        self.assertEqual(opened.call_args[0][0].toString(), 'https://team.qrtoba.com')

        with patch('PySide6.QtGui.QDesktopServices.openUrl', return_value=False):
            self.window.open_website()
        self.assertEqual(self.app.clipboard().text(), 'https://team.qrtoba.com')

        # Test email opening and fallback
        with patch('PySide6.QtGui.QDesktopServices.openUrl', return_value=True) as opened:
            self.window.open_email()
        self.assertTrue(opened.call_args[0][0].toString().startswith('mailto:qrtobacom@gmail.com'))

        with patch('PySide6.QtGui.QDesktopServices.openUrl', return_value=False):
            self.window.open_email()
        self.assertEqual(self.app.clipboard().text(), 'qrtobacom@gmail.com')

        # Test direct copy support email
        self.window.copy_support_email()
        self.assertEqual(self.app.clipboard().text(), 'qrtobacom@gmail.com')

        # Test About dialog contains all links
        with patch.object(QMessageBox, 'about') as mock_about:
            self.window.about()
        mock_about.assert_called_once()
        about_body = mock_about.call_args[0][2]
        self.assertIn('team.qrtoba.com', about_body)
        self.assertIn('qrtobacom@gmail.com', about_body)
        self.assertIn('patreon.com/c/altohamy', about_body)

        # Test open patreon
        with patch('PySide6.QtGui.QDesktopServices.openUrl', return_value=True) as opened:
            self.window.open_patreon()
        self.assertEqual(opened.call_args[0][0].toString(), 'https://www.patreon.com/c/altohamy')

    def test_contact_dialog(self):
        dialog = ContactDialog(self.window)
        dialog.show()

        dialog.copy_website()
        self.assertEqual(self.app.clipboard().text(), 'https://team.qrtoba.com')
        self.assertIn('team.qrtoba.com', dialog.status_label.text())

        dialog.copy_email()
        self.assertEqual(self.app.clipboard().text(), 'qrtobacom@gmail.com')
        self.assertIn('qrtobacom@gmail.com', dialog.status_label.text())

        dialog.copy_patreon()
        self.assertEqual(self.app.clipboard().text(), 'https://www.patreon.com/c/altohamy')
        self.assertIn('patreon.com/c/altohamy', dialog.status_label.text())

        with patch('PySide6.QtGui.QDesktopServices.openUrl', return_value=True) as opened:
            dialog.open_website()
        self.assertEqual(opened.call_args[0][0].toString(), 'https://team.qrtoba.com')

        with patch('PySide6.QtGui.QDesktopServices.openUrl', return_value=True) as opened:
            dialog.send_email()
        self.assertTrue(opened.call_args[0][0].toString().startswith('mailto:qrtobacom@gmail.com'))

        with patch('PySide6.QtGui.QDesktopServices.openUrl', return_value=True) as opened:
            dialog.open_patreon()
        self.assertEqual(opened.call_args[0][0].toString(), 'https://www.patreon.com/c/altohamy')
        dialog.close()


if __name__ == '__main__':
    unittest.main()
