import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from td import mirror


def sample_export() -> dict:
    return {
        "fetched_at": "2026-06-07T12:00:00+00:00",
        "task_fields": mirror.TASK_FIELDS,
        "folders": [
            {
                "id": "10",
                "name": "Personal",
                "private": "0",
                "archived": "0",
                "ord": "1",
            }
        ],
        "tasks": [
            {
                "id": "100",
                "title": "Plan mirror",
                "folder": "10",
                "priority": "2",
                "completed": "0",
                "duedate": "1780000000",
                "modified": "1770000000",
                "tag": "Data Science, reference, data science",
                "note": "Keep raw fields and normalized tags.",
                "star": "1",
            }
        ],
    }


class MirrorImportTests(unittest.TestCase):
    def test_build_database_imports_raw_and_normalized_tags(self) -> None:
        conn_path = ":memory:"
        with sqlite3.connect(conn_path) as conn:
            mirror.create_schema(conn)
            self.assertEqual(mirror.insert_folders(conn, sample_export()["folders"]), 1)
            self.assertEqual(mirror.insert_tasks(conn, sample_export()["tasks"]), 1)

            task = conn.execute(
                """
                SELECT title, folder_id, priority, completed, duedate, modified, tag, note, star
                FROM tasks
                WHERE id = 100
                """
            ).fetchone()
            self.assertEqual(
                task,
                (
                    "Plan mirror",
                    10,
                    2,
                    0,
                    1780000000,
                    1770000000,
                    "Data Science, reference, data science",
                    "Keep raw fields and normalized tags.",
                    1,
                ),
            )

            tags = conn.execute(
                """
                SELECT tags.name
                FROM tags
                JOIN task_tags ON task_tags.tag_id = tags.id
                WHERE task_tags.task_id = 100
                ORDER BY tags.normalized_name
                """
            ).fetchall()
            self.assertEqual([row[0] for row in tags], ["Data Science", "reference"])

    def test_import_replaces_database_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            export_path = os.path.join(temp_dir, "toodledo_export_test.json")
            db_path = os.path.join(temp_dir, "toodledo.db")
            with open(export_path, "w", encoding="utf-8") as handle:
                json.dump(sample_export(), handle)

            result = mirror.import_export(
                export_file=export_path,
                db_path=db_path,
                log_path=os.path.join(temp_dir, "sync.log"),
            )

            self.assertEqual(result["folders_count"], 1)
            self.assertEqual(result["tasks_count"], 1)
            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute("SELECT title FROM tasks WHERE id = 100").fetchone()
            finally:
                conn.close()
            self.assertEqual(row[0], "Plan mirror")

    def test_import_failure_leaves_prior_database_intact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            export_path = os.path.join(temp_dir, "bad_export.json")
            db_path = os.path.join(temp_dir, "toodledo.db")
            with open(export_path, "w", encoding="utf-8") as handle:
                json.dump({"folders": [], "tasks": []}, handle)
            conn = sqlite3.connect(db_path)
            try:
                conn.execute("CREATE TABLE marker (value TEXT)")
                conn.execute("INSERT INTO marker (value) VALUES ('old')")
                conn.commit()
            finally:
                conn.close()

            with patch("td.mirror.build_database", side_effect=RuntimeError("boom")):
                with self.assertRaisesRegex(RuntimeError, "boom"):
                    mirror.import_export(
                        export_file=export_path,
                        db_path=db_path,
                        log_path=os.path.join(temp_dir, "sync.log"),
                    )

            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute("SELECT value FROM marker").fetchone()
            finally:
                conn.close()
            self.assertEqual(row[0], "old")

    def test_latest_export_path_uses_most_recent_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            older = os.path.join(temp_dir, "toodledo_export_older.json")
            newer = os.path.join(temp_dir, "toodledo_export_newer.json")
            for path in (older, newer):
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write("{}")
            os.utime(older, (1, 1))
            os.utime(newer, (2, 2))

            self.assertEqual(mirror.latest_export_path(temp_dir), newer)


class MirrorFetchTests(unittest.TestCase):
    @patch("td.mirror.tasks.fetch_tasks")
    @patch("td.mirror.tasks.get_folders")
    @patch("td.mirror.auth.ensure_tokens")
    def test_fetch_payload_uses_incomplete_task_fields(
        self,
        mock_ensure_tokens,
        mock_get_folders,
        mock_fetch_tasks,
    ) -> None:
        mock_ensure_tokens.return_value = {"access_token": "token"}
        mock_get_folders.return_value = [{"id": 10, "name": "Personal"}]
        mock_fetch_tasks.return_value = [{"id": 100, "title": "Task"}]

        payload = mirror.fetch_payload()

        mock_fetch_tasks.assert_called_once_with("token", mirror.TASK_FIELDS)
        self.assertEqual(payload["folders"], [{"id": 10, "name": "Personal"}])
        self.assertEqual(payload["tasks"], [{"id": 100, "title": "Task"}])


if __name__ == "__main__":
    unittest.main()
