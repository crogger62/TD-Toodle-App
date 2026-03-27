import unittest
from datetime import date
from tempfile import NamedTemporaryFile
from unittest.mock import patch

from td import cli
from td import tasks


class NormalizeAddTaskInputTests(unittest.TestCase):
    @patch("td.tasks.date")
    def test_applies_defaults_for_missing_optional_fields(self, mock_date) -> None:
        mock_date.today.return_value = date(2026, 3, 25)

        normalized = tasks.normalize_add_task_input({"title": "Buy batteries"})

        self.assertEqual(normalized["title"], "Buy batteries")
        self.assertEqual(normalized["due"], date(2026, 3, 25))
        self.assertEqual(normalized["priority"], 0)
        self.assertEqual(normalized["folder"], "Personal")
        self.assertEqual(normalized["tags"], "claw")
        self.assertEqual(normalized["star"], 0)
        self.assertEqual(normalized["note"], "")

    def test_normalizes_llm_payload(self) -> None:
        payload = {
            "title": "Buy batteries",
            "due": "2026-03-28",
            "priority": "2",
            "folder": "Personal",
            "tags": ["home", "Errands", "home"],
            "star": True,
            "note": "AA batteries",
        }

        normalized = tasks.normalize_add_task_input(payload)

        self.assertEqual(normalized["title"], "Buy batteries")
        self.assertEqual(normalized["due"], date(2026, 3, 28))
        self.assertEqual(normalized["priority"], 2)
        self.assertEqual(normalized["folder"], "Personal")
        self.assertEqual(normalized["tags"], "home,Errands")
        self.assertEqual(normalized["star"], 1)
        self.assertEqual(normalized["note"], "AA batteries")

    def test_rejects_invalid_priority(self) -> None:
        with self.assertRaisesRegex(ValueError, "Priority must be one of"):
            tasks.normalize_add_task_input({"title": "x", "priority": 5})

    def test_rejects_conflicting_tag_keys(self) -> None:
        with self.assertRaisesRegex(ValueError, "Use either 'tags' or 'tag'"):
            tasks.normalize_add_task_input(
                {"title": "x", "tags": ["a"], "tag": "a,b"}
            )


class ResolveFolderValueTests(unittest.TestCase):
    @patch("td.tasks.get_folders")
    def test_resolves_exact_folder_name(self, mock_get_folders) -> None:
        mock_get_folders.return_value = [{"id": "123", "name": "Personal"}]

        resolved = tasks.resolve_folder_value("token", "Personal")

        self.assertEqual(
            resolved,
            {
                "id": 123,
                "name": "Personal",
                "input": "Personal",
                "match_type": "exact_name",
            },
        )

    @patch("td.tasks.get_folders")
    def test_resolves_case_insensitive_folder_name(self, mock_get_folders) -> None:
        mock_get_folders.return_value = [{"id": "123", "name": "Personal"}]

        resolved = tasks.resolve_folder_value("token", "personal")

        self.assertEqual(resolved["id"], 123)
        self.assertEqual(resolved["match_type"], "case_insensitive_name")

    @patch("td.tasks.get_folders")
    def test_rejects_unknown_folder(self, mock_get_folders) -> None:
        mock_get_folders.return_value = [{"id": "123", "name": "Personal"}]

        with self.assertRaisesRegex(ValueError, "Unknown folder: Work"):
            tasks.resolve_folder_value("token", "Work")

    @patch("td.tasks.get_folders")
    def test_rejects_ambiguous_casefold_match(self, mock_get_folders) -> None:
        mock_get_folders.return_value = [
            {"id": "123", "name": "Personal"},
            {"id": "124", "name": "PERSONAL"},
        ]

        with self.assertRaisesRegex(ValueError, "Ambiguous folder: personal"):
            tasks.resolve_folder_value("token", "personal")


class BuildAddTaskPayloadTests(unittest.TestCase):
    def test_builds_wire_payload(self) -> None:
        normalized = {
            "title": "Buy batteries",
            "due": date(2026, 3, 28),
            "priority": 2,
            "tags": "home,Errands",
            "star": 1,
            "note": "AA batteries",
        }
        folder_info = {"id": 123, "name": "Personal", "input": "Personal", "match_type": "exact_name"}

        payload = tasks.build_add_task_payload(normalized, folder_info)

        self.assertEqual(payload["title"], "Buy batteries")
        self.assertEqual(payload["priority"], 2)
        self.assertEqual(payload["folder"], 123)
        self.assertEqual(payload["tag"], "home,Errands")
        self.assertEqual(payload["star"], 1)
        self.assertEqual(payload["note"], "AA batteries")
        self.assertIn("duedate", payload)


class LoadAddPayloadTests(unittest.TestCase):
    def test_loads_payload_from_json_file(self) -> None:
        with NamedTemporaryFile("w+", encoding="utf-8") as handle:
            handle.write('{"title":"Buy batteries","folder":"Personal"}')
            handle.flush()
            args = type(
                "Args",
                (),
                {"stdin_json": False, "json": None, "json_file": handle.name},
            )()

            payload = cli._load_add_payload(args)

        self.assertEqual(
            payload,
            {"title": "Buy batteries", "folder": "Personal"},
        )


if __name__ == "__main__":
    unittest.main()
