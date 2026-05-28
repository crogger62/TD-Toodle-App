# Add Task

This guide covers the `td add` workflow for creating tasks in Toodledo from structured JSON or CSV input.

This command is designed for both manual CLI use and LLM/tool-driven workflows.

## Prerequisites

- a valid `config.json` with Toodledo client credentials
- a valid token file, or the ability to complete the OAuth browser flow

Configuration details are documented in [configuration.md](/Volumes/riprcrog/Projects/ToodleAPI/docs/configuration.md).

## Command Forms

Exactly one input mode is required.

### Inline JSON

```bash
python3 -m td add --json '{"title":"Buy batteries","due":"2026-03-28","priority":2,"folder":"Personal","tags":["home","errands"],"star":true,"note":"AA batteries for thermostat"}'
```

### JSON file

```bash
python3 -m td add --json-file test.json
```

### JSON from stdin

```bash
cat test.json | python3 -m td add --stdin-json
```

### CSV file

The CLI also accepts headerless CSV for batch task creation.

Default mapping:

- first column: `title`
- second column: `tag`

```bash
python3 -m td add --csv-file movies.csv
```

Example `movies.csv`:

```csv
8½,criterion
Ugetsu,unknown
"Paris, Texas",unknown
```

### CSV from stdin

```bash
cat movies.csv | python3 -m td add --stdin-csv
```

### Custom CSV mapping

Use `--csv-columns` to override the default `title,tag` mapping.

```bash
python3 -m td add --csv-file tasks.csv --csv-columns title,folder,tags
```

## Supported Fields

- `title` required
- `due` as `YYYY-MM-DD`
- `priority` as `-1`, `0`, `1`, `2`, or `3`
- `folder` as a folder name or numeric ID
- `tags` as a comma-separated string or array of strings
- `star` as `true` / `false` or `1` / `0`
- `note` as a string

Example JSON:

```json
{
  "title": "Buy batteries",
  "due": "2026-03-28",
  "priority": 2,
  "folder": "Personal",
  "tags": [
    "home",
    "errands"
  ],
  "star": true,
  "note": "AA batteries for thermostat"
}
```

## CSV Scheme

Behavior:

- CSV input is headerless
- the default column mapping is `title,tag`
- supported CSV columns are `title`, `due`, `priority`, `folder`, `tags`, `tag`, `star`, and `note`
- the column mapping must include `title`
- `tags` and `tag` may not both appear in the same column mapping
- blank cells are treated as omitted fields
- each non-empty CSV row creates one task

### Important CSV quoting rule

If a field contains a comma, quote it using normal CSV quoting rules.

Example:

```csv
"Paris, Texas",unknown
```

Without quotes, that row will be parsed as three fields instead of two.

## Folder Lookup

Folder lookup is part of task creation.

Behavior:

- if `folder` is numeric, it is treated as a direct folder ID
- if `folder` is a string, the CLI fetches folders and resolves by name
- exact name match is attempted first
- case-insensitive exact match is attempted next
- if no match exists, the command fails
- if the folder name is ambiguous, the command fails

This adds a little latency but avoids tasks being created in the wrong folder.

## Output

`td add` returns JSON in both success and failure cases.

### Success

Single-task success:

```json
{
  "ok": true,
  "task": {
    "id": 123456789,
    "title": "Buy batteries",
    "due": "2026-03-28",
    "priority": 2,
    "folder": {
      "input": "Personal",
      "resolved_id": 12345,
      "resolved_name": "Personal",
      "match_type": "exact_name"
    },
    "tags": [
      "home",
      "errands"
    ],
    "star": true,
    "note": "AA batteries for thermostat"
  }
}
```

Batch CSV success:

```json
{
  "ok": true,
  "count": 3,
  "tasks": [
    {
      "id": 123456789,
      "title": "8½",
      "due": "2026-03-28",
      "priority": 0,
      "tags": ["criterion"]
    }
  ]
}
```

### Failure

```json
{
  "ok": false,
  "error": "Unknown folder: Personal"
}
```

## Example LLM Workflow

An LLM can produce a JSON object, write it to a file, and then call:

```bash
python3 -m td add --json-file task.json
```

or stream it directly:

```bash
python3 -m td add --stdin-json
```

This makes `td add` a stable tool boundary for Openclaw, Claude, ChatGPT, Gemini, or similar workflows.

An LLM can also construct a CSV file for simple title/tag imports and call:

```bash
python3 -m td add --csv-file movies.csv
```

## Notes

- If `td` is not installed as a shell command, `python3 -m td ...` works from the repo.
- The command uses the same credential and token setup as `td login` and `td bump-overdue`.
