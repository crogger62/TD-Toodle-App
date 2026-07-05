# Toodledo SQL Examples

This repository can maintain a local SQLite mirror of incomplete Toodledo tasks
at:

```text
mirror/toodledo.db
```

You can open that file in DB Browser for SQLite and run read-only queries
against the mirrored task data. The mirror is rebuilt by:

```powershell
python -m td mirror sync
```

The mirror is a local snapshot, not the source of truth. Changes made directly
to the SQLite database will not update Toodledo and may be overwritten the next
time the mirror is rebuilt.

## Schema Overview

The mirror has five main tables:

```sql
folders (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  private INTEGER NOT NULL DEFAULT 0,
  archived INTEGER NOT NULL DEFAULT 0,
  ord INTEGER NOT NULL DEFAULT 0
);

tasks (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  folder_id INTEGER REFERENCES folders(id),
  priority INTEGER NOT NULL DEFAULT 0,
  completed INTEGER NOT NULL DEFAULT 0,
  duedate INTEGER,
  modified INTEGER,
  tag TEXT,
  note TEXT,
  star INTEGER NOT NULL DEFAULT 0
);

tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  normalized_name TEXT NOT NULL UNIQUE
);

task_tags (
  task_id INTEGER NOT NULL REFERENCES tasks(id),
  tag_id INTEGER NOT NULL REFERENCES tags(id),
  PRIMARY KEY (task_id, tag_id)
);

sync_log (
  run_at INTEGER PRIMARY KEY,
  fetched_at TEXT,
  folders_count INTEGER NOT NULL,
  tasks_count INTEGER NOT NULL,
  status TEXT NOT NULL,
  detail TEXT
);
```

The `tasks.tag` column preserves Toodledo's raw comma-separated tag text. The
`tags` and `task_tags` tables provide a normalized tag lookup that is easier to
query.

Date-like fields such as `duedate`, `modified`, and `run_at` are stored as Unix
epoch seconds. Use SQLite's `datetime(..., 'unixepoch', 'localtime')` helper to
display them as local dates and times.

## Friendlier Views

If you are working in DB Browser for SQLite, you can create a view that hides the
common joins and date conversion. This gives you a nicer surface for everyday
queries.

Run this once against `mirror/toodledo.db`:

```sql
CREATE VIEW IF NOT EXISTS task_view AS
SELECT
  tasks.id,
  tasks.title,
  folders.name AS folder,
  tasks.priority,
  tasks.completed,
  datetime(tasks.duedate, 'unixepoch', 'localtime') AS due_local,
  datetime(tasks.modified, 'unixepoch', 'localtime') AS modified_local,
  tasks.duedate,
  tasks.modified,
  tasks.tag,
  tasks.note,
  tasks.star
FROM tasks
LEFT JOIN folders ON folders.id = tasks.folder_id;
```

After creating the view, common queries become much shorter:

```sql
SELECT *
FROM task_view
WHERE folder = 'Personal'
ORDER BY
  duedate IS NULL,
  duedate,
  priority DESC,
  title;
```

```sql
SELECT id, title, folder, due_local, priority, tag
FROM task_view
WHERE lower(title) LIKE lower('%linear%')
   OR lower(note) LIKE lower('%linear%')
ORDER BY title;
```

```sql
SELECT folder, COUNT(*) AS task_count
FROM task_view
GROUP BY folder
ORDER BY task_count DESC;
```

Views are stored inside the SQLite database. If `td mirror sync` rebuilds the
database, you may need to recreate the view afterward.

## All Tasks With Folder Names

```sql
SELECT
  tasks.id,
  tasks.title,
  folders.name AS folder,
  tasks.priority,
  tasks.duedate,
  tasks.modified,
  tasks.tag,
  tasks.star
FROM tasks
LEFT JOIN folders ON folders.id = tasks.folder_id
ORDER BY folders.name, tasks.title;
```

## Count Tasks By Folder

```sql
SELECT
  folders.name AS folder,
  COUNT(*) AS task_count
FROM tasks
LEFT JOIN folders ON folders.id = tasks.folder_id
GROUP BY folders.name
ORDER BY task_count DESC;
```

## Search Task Titles And Notes

Replace `linear` with the word or phrase you want to search for.

```sql
SELECT
  tasks.id,
  tasks.title,
  folders.name AS folder,
  tasks.tag,
  tasks.note
FROM tasks
LEFT JOIN folders ON folders.id = tasks.folder_id
WHERE lower(tasks.title) LIKE lower('%linear%')
   OR lower(tasks.note) LIKE lower('%linear%')
ORDER BY tasks.title;
```

## Tasks With A Specific Tag

Replace `data science` with the tag you want to match.

```sql
SELECT
  tasks.id,
  tasks.title,
  folders.name AS folder,
  tags.name AS tag
FROM tasks
JOIN task_tags ON task_tags.task_id = tasks.id
JOIN tags ON tags.id = task_tags.tag_id
LEFT JOIN folders ON folders.id = tasks.folder_id
WHERE tags.normalized_name = lower('data science')
ORDER BY tasks.title;
```

## Recently Modified Tasks

```sql
SELECT
  id,
  title,
  datetime(modified, 'unixepoch', 'localtime') AS modified_local,
  tag
FROM tasks
WHERE modified IS NOT NULL
ORDER BY modified DESC
LIMIT 100;
```

## Due Dates As Readable Dates

```sql
SELECT
  id,
  title,
  datetime(duedate, 'unixepoch', 'localtime') AS due_local,
  priority,
  tag
FROM tasks
WHERE duedate IS NOT NULL
ORDER BY duedate;
```

## Latest Mirror Sync Status

```sql
SELECT
  datetime(run_at, 'unixepoch', 'localtime') AS run_local,
  fetched_at,
  folders_count,
  tasks_count,
  status,
  detail
FROM sync_log
ORDER BY run_at DESC
LIMIT 5;
```
