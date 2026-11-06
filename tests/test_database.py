import copy
import sqlite3
import tempfile
import unittest
from pathlib import Path

from core.database import DatabaseManager


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = DatabaseManager(str(Path(self.tmp.name) / 'library.db'))

    def test_crud_preserves_whitespace_and_creation_time(self):
        identifier = self.db.add_item('cmd', '  Test  ', '  echo hello\n', category_names=['Shell'])
        original = self.db.get_items('cmd')[0]
        self.assertEqual(original['content'], '  echo hello\n')
        self.db.update_item(identifier, 'Edited', '\n  echo goodbye\n', category_names=['New'], is_favorite=True)
        item = self.db.get_items('cmd')[0]
        self.assertEqual(item['created_at'], original['created_at'])
        self.assertEqual(item['content'], '\n  echo goodbye\n')
        self.assertEqual([c['name'] for c in item['categories']], ['New'])
        self.assertFalse(self.db.toggle_favorite(identifier))
        self.db.delete_item(identifier)
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM item_categories').fetchone()[0], 0)

    def test_duplicate_uuid_does_not_replace_data(self):
        identifier = self.db.add_item('cmd', 'Original', 'one', category_names=['Keep'])
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.add_item('cmd', 'Replacement', 'two', custom_uuid=identifier)
        self.assertEqual(self.db.get_items('cmd')[0]['title'], 'Original')
        self.assertEqual(len(self.db.get_items('cmd')[0]['categories']), 1)

    def test_search_literal_wildcards_tags_and_combined_filters(self):
        identifier = self.db.add_item('cmd', '100% done', 'file_name', category_names=['Deployment'], is_favorite=True)
        self.db.add_item('cmd', 'Other', 'filename')
        for query in ('%', '_', 'Deployment'):
            self.assertEqual([i['uuid'] for i in self.db.get_items('cmd', query)], [identifier])
        cat = self.db.get_categories('cmd')[0]
        self.assertEqual(len(self.db.get_items('cmd', '100', [cat['id']], True)), 1)
        self.assertEqual(self.db.get_items('prompt', '100'), [])

    def test_categories_keep_items_and_counts_respect_scope(self):
        shared = self.db.add_category('Shared')
        self.db.add_item('cmd', 'Command', 'echo 1', category_names=['Shared'])
        self.db.add_item('prompt', 'Prompt', 'Explain', category_names=['Shared'])
        self.assertEqual(self.db.get_categories('cmd')[0]['item_count'], 1)
        self.assertEqual(self.db.get_categories()[0]['item_count'], 2)
        self.db.rename_category(shared, 'Renamed')
        self.assertEqual(self.db.get_items('cmd')[0]['categories'][0]['name'], 'Renamed')
        self.db.delete_category(shared)
        self.assertEqual(len(self.db.get_items('cmd')), 1)
        self.assertEqual(self.db.get_items('cmd')[0]['categories'], [])

    def test_invalid_edit_rolls_back_categories(self):
        identifier = self.db.add_item('cmd', 'Test', 'echo 1', category_names=['Keep'])
        with self.assertRaises(ValueError):
            self.db.update_item(identifier, 'Bad', 'echo 2', category_ids=[999])
        item = self.db.get_items('cmd')[0]
        self.assertEqual(item['title'], 'Test')
        self.assertEqual(item['categories'][0]['name'], 'Keep')

    def test_seed_only_once_even_after_deleting_everything(self):
        self.db.seed_initial_data()
        self.assertEqual(len(self.db.export_pack()['items']), 5)
        for item in self.db.export_pack()['items']:
            self.db.delete_item(item['uuid'])
        self.db.seed_initial_data()
        self.assertEqual(self.db.export_pack()['items'], [])

    def test_pack_roundtrip_preserves_data_and_skips_existing_ids(self):
        self.db.add_category('Empty', 'prompt')
        self.db.add_item('prompt', 'مرحبا 🐍', '\n  Explain this\n', category_names=['Python'], is_favorite=True)
        pack = self.db.export_pack()
        restored = DatabaseManager(str(Path(self.tmp.name) / 'restored.db'))
        self.assertEqual(restored.import_pack(pack), (1, 0))
        self.assertEqual(restored.export_pack()['items'], pack['items'])
        self.assertEqual(restored.export_pack()['categories'], pack['categories'])
        modified = copy.deepcopy(pack)
        modified['items'][0]['title'] = 'Do not overwrite'
        self.assertEqual(restored.import_pack(modified), (0, 1))
        self.assertEqual(restored.get_items('prompt')[0]['title'], 'مرحبا 🐍')

    def test_malformed_pack_never_partially_imports(self):
        self.db.add_item('cmd', 'One', 'one')
        self.db.add_item('cmd', 'Two', 'two')
        pack = self.db.export_pack()
        restored = DatabaseManager(str(Path(self.tmp.name) / 'restored.db'))
        for mutate in (
            lambda p: p['items'][1].update(content=''),
            lambda p: p['items'][1].update(category_ids=[123]),
            lambda p: p['items'][1].update(is_favorite='false'),
            lambda p: p.update(version=2),
            lambda p: p['items'][1].update(created_at='bad'),
        ):
            invalid = copy.deepcopy(pack)
            mutate(invalid)
            with self.assertRaises(ValueError):
                restored.import_pack(invalid)
            self.assertEqual(restored.export_pack()['items'], [])

    def test_validation(self):
        for kind, title, content in [('bad', 'Title', 'Text'), ('cmd', ' ', 'Text'),
                                     ('prompt', 'Title', ' '), ('link', 'Title', 'file:///tmp/test'),
                                     ('link', 'Title', 'https://')]:
            with self.assertRaises(ValueError):
                self.db.add_item(kind, title, content)
        self.db.add_item('link', 'Docs', 'https://example.com/docs')
        with self.assertRaises(ValueError):
            self.db.add_category(' ')


if __name__ == '__main__':
    unittest.main()
