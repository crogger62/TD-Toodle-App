import sqlite3
import unittest
from contextlib import nullcontext
from unittest.mock import patch

from tdmedia import db
from tdmedia import query
from tdmedia import sync


class DbTests(unittest.TestCase):
    def test_normalizes_first_tag_as_service(self) -> None:
        self.assertEqual(db.normalize_service(" Netflix , comedy "), "Netflix")
        self.assertEqual(db.normalize_service("Prime   Video"), "Prime Video")
        self.assertIsNone(db.normalize_service(""))

    def test_row_from_task_maps_toodledo_fields(self) -> None:
        row = db.row_from_task(
            {
                "id": "123",
                "title": "  The Diplomat  ",
                "tag": "Netflix,politics",
                "note": "Season 2",
                "completed": "0",
                "modified": "1770000000",
            },
            folder_id=99,
            imported_at="2026-05-21T12:00:00+00:00",
        )

        self.assertEqual(row["toodledo_id"], 123)
        self.assertEqual(row["title"], "The Diplomat")
        self.assertEqual(row["service"], "Netflix")
        self.assertEqual(row["raw_tags"], "Netflix,politics")
        self.assertEqual(row["notes"], "Season 2")
        self.assertEqual(row["folder_id"], 99)
        self.assertEqual(row["completed"], 0)
        self.assertEqual(row["modified"], 1770000000)

    def test_upsert_replaces_existing_item(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        db.ensure_schema(conn)

        first = db.row_from_task(
            {"id": 1, "title": "Old", "tag": "Netflix"},
            folder_id=10,
            imported_at="first",
        )
        second = db.row_from_task(
            {"id": 1, "title": "New", "tag": "Hulu"},
            folder_id=10,
            imported_at="second",
        )

        self.assertEqual(db.upsert_items(conn, [first]), 1)
        self.assertEqual(db.upsert_items(conn, [second]), 1)
        row = conn.execute("SELECT * FROM watch_items WHERE toodledo_id = 1").fetchone()
        self.assertEqual(row["title"], "New")
        self.assertEqual(row["service"], "Hulu")
        self.assertEqual(row["imported_at"], "second")


class QueryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        db.ensure_schema(self.conn)
        db.upsert_items(
            self.conn,
            [
                db.row_from_task(
                    {
                        "id": 1,
                        "title": "The Diplomat",
                        "tag": "Netflix",
                        "note": "political drama",
                    },
                    10,
                    "now",
                ),
                db.row_from_task(
                    {
                        "id": 2,
                        "title": "Reservation Dogs",
                        "tag": "Hulu",
                        "note": "comedy",
                    },
                    10,
                    "now",
                ),
                db.row_from_task(
                    {
                        "id": 3,
                        "title": "Watched Item",
                        "tag": "Netflix",
                        "completed": "1770000000",
                    },
                    10,
                    "now",
                ),
            ],
        )

    def tearDown(self) -> None:
        self.conn.close()

    def test_list_filters_by_service_case_insensitively(self) -> None:
        rows = query.list_items(self.conn, service="netflix")
        self.assertEqual([row["toodledo_id"] for row in rows], [1])

    def test_search_checks_title_and_notes(self) -> None:
        rows = query.search_items(self.conn, "drama")
        self.assertEqual([row["title"] for row in rows], ["The Diplomat"])

    def test_service_counts_excludes_completed_by_default(self) -> None:
        rows = query.service_counts(self.conn)
        self.assertEqual(
            [(row["service"], row["count"]) for row in rows],
            [("Hulu", 1), ("Netflix", 1)],
        )


class SyncTests(unittest.TestCase):
    @patch("tdmedia.sync.db.connect")
    @patch("tdmedia.sync.tasks.fetch_tasks")
    @patch("tdmedia.sync.tasks.resolve_folder_value")
    @patch("tdmedia.sync.auth.ensure_tokens")
    def test_sync_imports_only_watchlist_folder(
        self,
        mock_ensure_tokens,
        mock_resolve_folder_value,
        mock_fetch_tasks,
        mock_connect,
    ) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        db.ensure_schema(conn)
        mock_connect.return_value = nullcontext(conn)
        mock_ensure_tokens.return_value = {"access_token": "token"}
        mock_resolve_folder_value.return_value = {"id": 10}
        mock_fetch_tasks.return_value = [
            {"id": 1, "title": "Keep", "folder": 10, "tag": "Netflix"},
            {"id": 2, "title": "Skip", "folder": 11, "tag": "Hulu"},
        ]

        result = sync.sync_watchlist(":memory:")

        self.assertEqual(result["fetched"], 1)
        self.assertEqual(result["imported"], 1)
        row = conn.execute("SELECT title, service FROM watch_items").fetchone()
        self.assertEqual((row["title"], row["service"]), ("Keep", "Netflix"))


if __name__ == "__main__":
    unittest.main()
