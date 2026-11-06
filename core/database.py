# core/database.py

import sys
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any, Generator
from urllib.parse import urlsplit


def validate_item(item_type, title, content):
    if item_type not in ('cmd', 'prompt', 'link'):
        raise ValueError('Choose a valid item type.')
    if not isinstance(title, str) or not title.strip():
        raise ValueError('Enter a title.')
    if not isinstance(content, str) or not content.strip():
        raise ValueError('Enter content for this item.')
    if item_type == 'link':
        url = urlsplit(content.strip())
        if url.scheme not in ('http', 'https') or not url.hostname or any(c.isspace() for c in content.strip()):
            raise ValueError('Enter a complete http:// or https:// URL.')


class DatabaseManager:
    """
    SQLite Database Engine for Pro Dash.
    Supports Many-to-Many relationships between Items (cmd, prompt, link) and Categories.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base_dir = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent
            data_dir = base_dir / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = str(data_dir / "prodash.db")
        else:
            self.db_path = db_path

        self.init_db()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Context manager that opens a connection, enables Foreign Keys & WAL mode,
        commits automatically on success, rolls back on error, and ALWAYS closes the connection.
        """
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA journal_mode = WAL;")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _now_iso() -> str:
        """Returns timezone-aware UTC timestamp in ISO format."""
        return datetime.now(timezone.utc).isoformat()

    def init_db(self) -> None:
        """Creates the tables and indexes if they do not exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')

            # 1. Items Table (UUID as Primary Key for safe export/import between users)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    uuid TEXT PRIMARY KEY,
                    item_type TEXT NOT NULL CHECK(item_type IN ('cmd', 'prompt', 'link')),
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    is_favorite INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # 2. Categories Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    scope TEXT NOT NULL DEFAULT 'global',
                    color_hex TEXT DEFAULT '#10B981',
                    UNIQUE(name, scope)
                )
            """)

            # 3. Many-to-Many Junction Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS item_categories (
                    item_uuid TEXT NOT NULL,
                    category_id INTEGER NOT NULL,
                    PRIMARY KEY (item_uuid, category_id),
                    FOREIGN KEY (item_uuid) REFERENCES items(uuid) ON DELETE CASCADE,
                    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
                )
            """)

            # Indexes for fast searching and filtering
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_type ON items(item_type);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_categories_scope ON categories(scope);")

    # ==========================================
    # CATEGORY OPERATIONS
    # ==========================================

    def _get_or_create_category_id(
        self,
        cursor: sqlite3.Cursor,
        name: str,
        scope: str = "global",
        color_hex: str = "#10B981"
    ) -> int:
        """
        Internal helper that reuses an existing cursor inside an active transaction
        so we NEVER open a nested connection and lock SQLite.
        """
        clean_name = name.strip()
        if not clean_name:
            raise ValueError('Enter a category name.')
        if scope not in ('global', 'cmd', 'prompt', 'link'):
            raise ValueError('Invalid category scope.')
        cursor.execute(
            "SELECT id FROM categories WHERE LOWER(name) = LOWER(?) AND scope = ?",
            (clean_name, scope)
        )
        row = cursor.fetchone()
        if row:
            return row["id"]

        cursor.execute(
            "INSERT INTO categories (name, scope, color_hex) VALUES (?, ?, ?)",
            (clean_name, scope, color_hex)
        )
        return cursor.lastrowid

    def add_category(self, name: str, scope: str = "global", color_hex: str = "#10B981") -> int:
        """Public method to add a standalone category."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            return self._get_or_create_category_id(cursor, name, scope, color_hex)

    def get_categories(self, scope: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetches categories along with the count of items inside each category."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if scope:
                cursor.execute("""
                    SELECT c.*, COUNT(i.uuid) as item_count
                    FROM categories c
                    LEFT JOIN item_categories ic ON c.id = ic.category_id
                    LEFT JOIN items i ON i.uuid = ic.item_uuid AND i.item_type = ?
                    WHERE c.scope = ? OR c.scope = 'global'
                    GROUP BY c.id
                    ORDER BY c.name ASC
                """, (scope, scope))
            else:
                cursor.execute("""
                    SELECT c.*, COUNT(ic.item_uuid) as item_count
                    FROM categories c
                    LEFT JOIN item_categories ic ON c.id = ic.category_id
                    GROUP BY c.id
                    ORDER BY c.name ASC
                """)
            return [dict(row) for row in cursor.fetchall()]

    def delete_category(self, category_id: int) -> None:
        """Deletes a category (junction links auto-remove via ON DELETE CASCADE)."""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))

    # ==========================================
    # ITEM CRUD & MANY-TO-MANY LINKING
    # ==========================================

    def add_item(
        self,
        item_type: str,
        title: str,
        content: str,
        description: str = "",
        category_names: Optional[List[str]] = None,
        is_favorite: bool = False,
        custom_uuid: Optional[str] = None,
        category_ids: Optional[List[int]] = None
    ) -> str:
        """
        Creates a new Command, Prompt, or Link and links it to multiple categories
        using a single connection/transaction.
        """
        item_uuid = custom_uuid or str(uuid.uuid4())
        validate_item(item_type, title, content)
        now = self._now_iso()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO items 
                (uuid, item_type, title, content, description, is_favorite, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item_uuid,
                item_type,
                title.strip(),
                content,
                description.strip(),
                1 if is_favorite else 0,
                now,
                now
            ))

            # Clear old category links if replacing/updating
            cursor.execute("DELETE FROM item_categories WHERE item_uuid = ?", (item_uuid,))
            self._link_category_ids(cursor, item_uuid, item_type, category_ids)

            # Link all categories using the SAME cursor (no nested connection!)
            if category_names:
                for cat_name in category_names:
                    if not cat_name.strip():
                        continue
                    cat_id = self._category_for_item(cursor, cat_name, item_type)
                    cursor.execute("""
                        INSERT OR IGNORE INTO item_categories (item_uuid, category_id)
                        VALUES (?, ?)
                    """, (item_uuid, cat_id))

        return item_uuid

    def update_item(
        self,
        item_uuid: str,
        title: str,
        content: str,
        description: str = "",
        category_names: Optional[List[str]] = None,
        is_favorite: bool = False,
        category_ids: Optional[List[int]] = None
    ) -> None:
        """Updates an existing item and refreshes its Many-to-Many category tags."""
        now = self._now_iso()
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT item_type FROM items WHERE uuid = ?", (item_uuid,))
            row = cursor.fetchone()
            if not row:
                raise ValueError('This item no longer exists.')
            item_type = row["item_type"]
            validate_item(item_type, title, content)

            cursor.execute("""
                UPDATE items
                SET title = ?, content = ?, description = ?, is_favorite = ?, updated_at = ?
                WHERE uuid = ?
            """, (title.strip(), content, description.strip(), 1 if is_favorite else 0, now, item_uuid))

            # Rebuild category associations on the SAME cursor
            cursor.execute("DELETE FROM item_categories WHERE item_uuid = ?", (item_uuid,))
            self._link_category_ids(cursor, item_uuid, item_type, category_ids)
            if category_names:
                for cat_name in category_names:
                    if not cat_name.strip():
                        continue
                    cat_id = self._category_for_item(cursor, cat_name, item_type)
                    cursor.execute("""
                        INSERT OR IGNORE INTO item_categories (item_uuid, category_id)
                        VALUES (?, ?)
                    """, (item_uuid, cat_id))

    def toggle_favorite(self, item_uuid: str) -> bool:
        """Toggles the favorite status of an item and returns the new state."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_favorite FROM items WHERE uuid = ?", (item_uuid,))
            row = cursor.fetchone()
            if not row:
                return False
            new_val = 0 if row["is_favorite"] else 1
            cursor.execute("UPDATE items SET is_favorite = ?, updated_at = ? WHERE uuid = ?", (new_val, self._now_iso(), item_uuid))
            return bool(new_val)

    def delete_item(self, item_uuid: str) -> None:
        """Deletes an item by UUID."""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM items WHERE uuid = ?", (item_uuid,))

    def get_items(
        self,
        item_type: str,
        search_query: str = "",
        category_ids: Optional[List[int]] = None,
        favorites_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Fetches items for a screen ('cmd', 'prompt', or 'link') with attached categories list.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            query = "SELECT DISTINCT i.* FROM items i"
            params: List[Any] = []

            if category_ids:
                placeholders = ",".join("?" for _ in category_ids)
                query += f" JOIN item_categories ic ON i.uuid = ic.item_uuid AND ic.category_id IN ({placeholders})"
                params.extend(category_ids)

            query += " WHERE i.item_type = ?"
            params.append(item_type)

            if favorites_only:
                query += " AND i.is_favorite = 1"

            if search_query.strip():
                term = search_query.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
                q = f"%{term}%"
                query += """ AND (i.title LIKE ? ESCAPE '\\' OR i.content LIKE ? ESCAPE '\\'
                    OR i.description LIKE ? ESCAPE '\\' OR EXISTS (
                        SELECT 1 FROM item_categories tags JOIN categories c ON c.id = tags.category_id
                        WHERE tags.item_uuid = i.uuid AND c.name LIKE ? ESCAPE '\\'))"""
                params.extend([q, q, q, q])

            query += " ORDER BY i.is_favorite DESC, julianday(i.updated_at) DESC, i.title COLLATE NOCASE"

            cursor.execute(query, params)
            items = [dict(row) for row in cursor.fetchall()]

            for item in items:
                cursor.execute("""
                    SELECT c.id, c.name, c.color_hex, c.scope
                    FROM categories c
                    JOIN item_categories ic ON c.id = ic.category_id
                    WHERE ic.item_uuid = ?
                    ORDER BY c.name ASC
                """, (item["uuid"],))
                item["categories"] = [dict(cat) for cat in cursor.fetchall()]

            return items

    def _link_category_ids(self, cursor, item_uuid, item_type, category_ids):
        for category_id in category_ids or []:
            row = cursor.execute('SELECT scope FROM categories WHERE id = ?', (category_id,)).fetchone()
            if not row or row['scope'] not in ('global', item_type):
                raise ValueError('A selected category no longer exists in this library. Reopen the editor and try again.')
            cursor.execute('INSERT OR IGNORE INTO item_categories VALUES (?, ?)', (item_uuid, category_id))

    def _category_for_item(self, cursor, name, scope):
        row = cursor.execute(
            "SELECT id FROM categories WHERE LOWER(name) = LOWER(?) AND scope IN (?, 'global') "
            "ORDER BY CASE WHEN scope = ? THEN 0 ELSE 1 END LIMIT 1",
            (name.strip(), scope, scope),
        ).fetchone()
        return row['id'] if row else self._get_or_create_category_id(cursor, name, scope)

    def rename_category(self, category_id, name):
        name = name.strip()
        if not name:
            raise ValueError('Enter a category name.')
        with self.get_connection() as conn:
            row = conn.execute('SELECT scope FROM categories WHERE id = ?', (category_id,)).fetchone()
            if not row:
                raise ValueError('This category no longer exists.')
            if conn.execute('SELECT 1 FROM categories WHERE LOWER(name) = LOWER(?) AND scope = ? AND id != ?',
                            (name, row['scope'], category_id)).fetchone():
                raise ValueError('A category with that name already exists.')
            conn.execute('UPDATE categories SET name = ? WHERE id = ?', (name, category_id))

    def get_stats(self):
        with self.get_connection() as conn:
            counts = {row['item_type']: row['count'] for row in conn.execute(
                'SELECT item_type, COUNT(*) AS count FROM items GROUP BY item_type')}
            counts['categories'] = conn.execute('SELECT COUNT(*) FROM categories').fetchone()[0]
            return counts

    def export_pack(self):
        """Take a consistent snapshot, including empty categories and original timestamps."""
        with self.get_connection() as conn:
            conn.execute('BEGIN')
            categories = [dict(row) for row in conn.execute('SELECT * FROM categories ORDER BY id')]
            items = [dict(row) for row in conn.execute('SELECT * FROM items ORDER BY created_at, uuid')]
            links = {}
            for row in conn.execute('SELECT * FROM item_categories'):
                links.setdefault(row['item_uuid'], []).append(row['category_id'])
            for item in items:
                item['is_favorite'] = bool(item['is_favorite'])
                item['category_ids'] = links.get(item['uuid'], [])
        return {'format': 'pro_dash', 'version': 1, 'exported_at': self._now_iso(),
                'categories': categories, 'items': items}

    def import_pack(self, pack):
        """Validate the complete pack before merging it in one transaction; keep existing UUIDs."""
        import re
        if not isinstance(pack, dict) or pack.get('format') != 'pro_dash' or type(pack.get('version')) is not int or pack['version'] != 1:
            raise ValueError('This is not a supported Pro Dash pack (version 1).')
        categories, items = pack.get('categories'), pack.get('items')
        if not isinstance(categories, list) or not isinstance(items, list):
            raise ValueError('The pack must contain items and categories lists.')
        category_ids, item_ids, category_keys = set(), set(), set()
        for cat in categories:
            if not isinstance(cat, dict) or type(cat.get('id')) is not int or cat['id'] in category_ids:
                raise ValueError('Invalid or duplicate category ID.')
            if not isinstance(cat.get('name'), str) or not cat['name'].strip() or cat.get('scope') not in ('global', 'cmd', 'prompt', 'link'):
                raise ValueError('Invalid category name or scope.')
            if not isinstance(cat.get('color_hex'), str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', cat['color_hex']):
                raise ValueError('Invalid category color.')
            key = (cat['name'].strip().lower(), cat['scope'])
            if key in category_keys:
                raise ValueError('Duplicate category name and scope.')
            category_keys.add(key)
            category_ids.add(cat['id'])
        scopes = {cat['id']: cat['scope'] for cat in categories}
        for item in items:
            if not isinstance(item, dict):
                raise ValueError('Invalid item record.')
            identifier = item.get('uuid')
            if not isinstance(identifier, str) or not identifier.strip() or identifier in item_ids:
                raise ValueError('Invalid or duplicate item ID.')
            item_ids.add(identifier)
            validate_item(item.get('item_type'), item.get('title'), item.get('content'))
            if not isinstance(item.get('description'), str) or type(item.get('is_favorite')) not in (bool, int) or item['is_favorite'] not in (0, 1):
                raise ValueError('Invalid description or favorite value.')
            for field in ('created_at', 'updated_at'):
                try:
                    datetime.fromisoformat(item[field])
                except (KeyError, TypeError, ValueError):
                    raise ValueError('Invalid item timestamp.') from None
            ids = item.get('category_ids')
            if not isinstance(ids, list) or any(type(i) is not int or i not in category_ids for i in ids):
                raise ValueError('An item references an unknown category.')
            if any(scopes[i] not in ('global', item['item_type']) for i in ids):
                raise ValueError('A category does not belong to the item library.')
        imported = skipped = 0
        with self.get_connection() as conn:
            cursor = conn.cursor()
            mapping = {cat['id']: self._get_or_create_category_id(cursor, cat['name'], cat['scope'], cat['color_hex']) for cat in categories}
            for item in items:
                if cursor.execute('SELECT 1 FROM items WHERE uuid = ?', (item['uuid'],)).fetchone():
                    skipped += 1
                    continue
                cursor.execute('''INSERT INTO items
                    (uuid, item_type, title, content, description, is_favorite, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                    tuple(item[k] for k in ('uuid', 'item_type', 'title', 'content', 'description', 'is_favorite', 'created_at', 'updated_at')))
                for cat_id in item['category_ids']:
                    cursor.execute('INSERT OR IGNORE INTO item_categories VALUES (?, ?)', (item['uuid'], mapping[cat_id]))
                imported += 1
            cursor.execute("INSERT OR IGNORE INTO metadata VALUES ('seeded', '1')")
        return imported, skipped

    # ==========================================
    # INITIAL SEED DATA FOR FIRST RUN
    # ==========================================

    def seed_initial_data(self) -> None:
        """Populates starter commands and AI prompts if the database is completely empty."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if cursor.execute("SELECT 1 FROM metadata WHERE key = 'seeded'").fetchone():
                return
            cursor.execute("INSERT INTO metadata (key, value) VALUES ('seeded', '1')")
            cursor.execute("SELECT COUNT(*) as cnt FROM items")
            if cursor.fetchone()["cnt"] > 0:
                return

        self.add_item(
            item_type="cmd",
            title="PostgreSQL Database Dump (Compressed)",
            content="pg_dump -U postgres -F c -b -v -f backup.dump my_database",
            description="Creates a custom-format compressed backup of a PostgreSQL database on Linux.",
            category_names=["Linux", "PostgreSQL", "Database"],
            is_favorite=True
        )
        self.add_item(
            item_type="cmd",
            title="Restart Gunicorn & Check Nginx Config",
            content="sudo systemctl restart gunicorn && sudo nginx -t && sudo systemctl reload nginx",
            description="Restarts the Gunicorn daemon and reloads Nginx only if the syntax test passes.",
            category_names=["Linux", "Nginx", "Django", "VPS"],
            is_favorite=True
        )
        self.add_item(
            item_type="cmd",
            title="Find Process Using Port 8000",
            content="sudo lsof -i :8000",
            description="Lists any process currently listening on port 8000.",
            category_names=["Linux", "Networking"]
        )

        self.add_item(
            item_type="prompt",
            title="Senior Python Code Reviewer & Refactor",
            content=(
                "Act as a Principal Python Software Engineer. Review the following code for:\n"
                "1. Performance bottlenecks and memory leaks.\n"
                "2. Edge cases and exception handling.\n"
                "3. Clean architecture and PEP-8 compliance.\n\n"
                "Provide the refactored code with brief inline explanations:\n\n[PASTE CODE HERE]"
            ),
            description="Use before committing major backend modules or database queries.",
            category_names=["Python", "Code Review", "Architecture"],
            is_favorite=True
        )
        self.add_item(
            item_type="prompt",
            title="SQL Query Optimizer",
            content=(
                "Analyze this SQL query and schema. Rewrite the query to eliminate N+1 issues, "
                "suggest composite indexes, and explain the execution plan improvements:\n\n[PASTE SQL HERE]"
            ),
            description="Optimizes slow PostgreSQL or SQLite queries.",
            category_names=["Database", "PostgreSQL", "Performance"]
        )


if __name__ == "__main__":
    db = DatabaseManager()
    db.seed_initial_data()

    cmds = db.get_items("cmd")
    prompts = db.get_items("prompt")

    print(f"[OK] Database created at: {db.db_path}")
    print(f"[OK] Loaded {len(cmds)} Terminal Commands and {len(prompts)} AI Prompts.\n")

    for c in cmds:
        tags = ", ".join(cat["name"] for cat in c["categories"])
        print(f" -> CMD: {c['title']} | Tags: [{tags}]")
