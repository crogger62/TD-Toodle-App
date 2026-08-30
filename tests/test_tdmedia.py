import sqlite3
import unittest
from contextlib import nullcontext, redirect_stderr
from datetime import datetime
from io import StringIO
from unittest.mock import patch

from tdmedia import db
from tdmedia import query
from tdmedia import sync
from tdmedia import web


class DbTests(unittest.TestCase):
    def test_normalizes_first_tag_as_service(self) -> None:
        self.assertEqual(db.normalize_service(" Netflix , comedy "), "netflix")
        self.assertEqual(db.normalize_service("Prime   Video"), "prime video")
        self.assertEqual(db.normalize_service("shuddder, horror"), "shudder")
        self.assertIsNone(db.normalize_service("watch list, netflix"))
        self.assertIsNone(db.normalize_service("unknown"))
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
        self.assertEqual(row["service"], "netflix")
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
        self.assertEqual(row["service"], "hulu")
        self.assertEqual(row["imported_at"], "second")

    def test_records_and_reads_last_successful_sync(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        db.ensure_schema(conn)

        db.record_successful_sync(
            conn,
            "2026-08-28T18:30:00+00:00",
            {"fetched": 4, "imported": 4, "added": 2, "deleted": 1},
        )

        self.assertEqual(
            db.last_successful_sync(conn), "2026-08-28T18:30:00+00:00"
        )
        sync_run = db.latest_sync_run(conn)
        self.assertEqual(dict(sync_run), {
            "completed_at": "2026-08-28T18:30:00+00:00",
            "fetched": 4,
            "imported": 4,
            "added": 2,
            "deleted": 1,
        })

    def test_replace_folder_items_counts_additions_and_deletions(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        db.ensure_schema(conn)
        db.upsert_items(
            conn,
            [
                db.row_from_task({"id": 1, "title": "Removed"}, 10, "now"),
                db.row_from_task({"id": 2, "title": "Other folder"}, 11, "now"),
            ],
        )

        stats = db.replace_folder_items(
            conn,
            [db.row_from_task({"id": 3, "title": "Added"}, 10, "now")],
            folder_id=10,
        )

        self.assertEqual(stats, {"imported": 1, "added": 1, "deleted": 1})
        rows = conn.execute(
            "SELECT toodledo_id FROM watch_items ORDER BY toodledo_id"
        ).fetchall()
        self.assertEqual([row["toodledo_id"] for row in rows], [2, 3])


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
            [("hulu", 1), ("netflix", 1)],
        )

    def test_browse_items_supports_uncategorized_and_has_notes(self) -> None:
        db.upsert_items(
            self.conn,
            [
                db.row_from_task(
                    {
                        "id": 4,
                        "title": "Mystery Queue",
                        "tag": "watch list",
                        "note": "needs sorting",
                    },
                    10,
                    "now",
                )
            ],
        )

        rows = query.browse_items(
            self.conn,
            uncategorized_only=True,
            has_notes=True,
        )

        self.assertEqual([row["toodledo_id"] for row in rows], [4])


class SyncTests(unittest.TestCase):
    @patch("tdmedia.sync.auth.ensure_tokens")
    def test_sync_failure_is_logged_with_redacted_credentials(
        self, mock_ensure_tokens
    ) -> None:
        mock_ensure_tokens.side_effect = RuntimeError(
            "429 for url: https://example.test?access_token=secret"
        )
        stderr = StringIO()

        with redirect_stderr(stderr), self.assertRaises(RuntimeError):
            sync.sync_watchlist(":memory:")

        output = stderr.getvalue()
        self.assertIn("tdmedia sync failed:", output)
        self.assertIn("access_token=[REDACTED]", output)
        self.assertNotIn("secret", output)

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
        self.assertEqual(result["added"], 1)
        self.assertEqual(result["deleted"], 0)
        self.assertEqual(db.last_successful_sync(conn), result["completed_at"])
        row = conn.execute("SELECT title, service FROM watch_items").fetchone()
        self.assertEqual((row["title"], row["service"]), ("Keep", "netflix"))


class WebTests(unittest.TestCase):
    def test_page_shows_last_successful_sync(self) -> None:
        with patch("tdmedia.web.db.connect") as mock_connect:
            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            db.ensure_schema(conn)
            db.record_successful_sync(
                conn,
                "2026-08-28T18:30:00+00:00",
                {"fetched": 12, "imported": 12, "added": 3, "deleted": 1},
            )
            mock_connect.return_value = nullcontext(conn)

            page = web._render_page(":memory:", {})
            stale_error_page = web._render_page(
                ":memory:", {"message": ["Sync failed: old rate limit"]}
            )
            current_error_page = web._render_page(
                ":memory:",
                {
                    "message": ["Sync failed: current rate limit"],
                    "message_type": ["error"],
                },
            )

        local_timestamp = datetime.fromisoformat(
            "2026-08-28T18:30:00+00:00"
        ).astimezone()
        expected_sync_status = (
            f"Last successful sync: {local_timestamp.strftime('%b')} "
            f"{local_timestamp.day}, {local_timestamp.year} at "
            f"{local_timestamp.strftime('%I:%M %p').lstrip('0')} "
            f"{local_timestamp.tzname()}."
        )
        self.assertIn(expected_sync_status, page)
        self.assertIn('aria-label="Last sync metrics"', page)
        self.assertIn("Fetched</dt><dd>12", page)
        self.assertIn("Added</dt><dd>3", page)
        self.assertIn("Deleted</dt><dd>1", page)
        self.assertIn("Net change</dt><dd>+2", page)
        self.assertIn('id="sync-form"', page)
        self.assertIn("Updating from Toodledo...", page)
        self.assertIn('syncForm.classList.add("is-syncing")', page)
        self.assertIn('url.searchParams.delete("message")', page)
        self.assertNotIn("Sync failed: old rate limit", stale_error_page)
        self.assertIn("Sync failed: current rate limit", current_error_page)
        self.assertIn("#5b7553", page)
        self.assertIn("tdmedia v1.1.0", page)


if __name__ == "__main__":
    unittest.main()
