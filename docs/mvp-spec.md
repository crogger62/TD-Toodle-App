Toodledo CLI (Python) — MVP Specification

This document defines the complete, final MVP for a cross-platform Python CLI that authenticates with Toodledo, retrieves tasks live from the API, and supports client-side filtering and listing.

This document is authoritative.
If implementation questions arise, follow this document.

Goals

The MVP SHALL:

Authenticate a user via Toodledo OAuth2

Retrieve tasks from Toodledo

Do not persist tasks locally

List and filter tasks via a CLI using live API calls

Run unchanged on:

macOS

Linux

WSL

Windows (PowerShell and cmd.exe)

Non-Goals (Explicit)

The MVP SHALL NOT include:

Creating or deleting tasks

Notes, outlines, lists, or habits

Executing Toodledo saved searches

Any GUI or TUI

OS keychain / credential manager integration

Async or concurrent networking

Local task cache or sync state

Technology Choices
Language

Python ≥ 3.9

Third-Party Dependencies (MVP)

Exactly one external dependency:

requests ≥ 2.31

All other functionality uses the Python standard library.

Standard Library Modules Used

argparse

datetime

http.server

json

logging

os

secrets

sys

time

urllib.parse

webbrowser

zoneinfo

Installation / Environment

Dependencies should be declared explicitly, e.g.:

requirements.txt:

requests>=2.31

or

pyproject.toml (PEP 621):

requires-python = ">=3.9"

dependencies = ["requests>=2.31"]

CLI Overview

Executable name: td

Commands

td login

td whoami

td list [filters] [--sort FIELD] [--desc] [--limit N] [--format table|json|csv]

td bump-overdue [--date YYYY-MM-DD] [--apply]

td logout

td help

Notes

td whoami and td list will invoke the OAuth flow if no valid access token is available.

td list fetches tasks live from the API and applies filters client-side in memory.

OAuth
Scopes

Request exactly:

basic tasks write

(space-separated)

No other scopes.

State Parameter

Generate a cryptographically random state

Store in memory only

Validate on callback

If the process exits mid-login, the user must re-run td login

Redirect / Callback Server

Bind to 127.0.0.1 only

Default redirect port is 8765

Optional override via environment variable:

TOODLEDO_REDIRECT_PORT

Redirect URI format:

http://127.0.0.1:{PORT}/

Windows firewall prompts are unlikely for loopback binding; if prompted, allow Private networks only.

Token Handling

Storage

Tokens are stored on disk in a per-user app data directory and reused across commands.

Environment variables, if set, take precedence over the token file.

Logout

td logout deletes the token file (if present).

Token file location:

Windows: %APPDATA%\toodledo-cli\tokens.json

macOS: ~/Library/Application Support/toodledo-cli/tokens.json

Linux/WSL: ${XDG_CONFIG_HOME:-~/.config}/toodledo-cli/tokens.json

Token file format (JSON):

access_token

refresh_token

expires_at (epoch seconds)

scope (optional)

File permissions:

On Unix-like systems, set to 0600.

If tokens are provided via environment variables, the CLI uses them without invoking OAuth.

Optional env vars:

TOODLEDO_ACCESS_TOKEN

TOODLEDO_REFRESH_TOKEN

TOODLEDO_EXPIRES_AT (epoch seconds)

Refresh Strategy

Proactively refresh if access token expires within 5 minutes

Also refresh on authentication failure

Refresh tokens are single-use; always replace the in-memory refresh token

Account Info

whoami Behavior

Do not assume any identity field exists

Display best available identifier:

email if present

else userid if present

else a generic “Authenticated” message

Never fail due to missing identity fields

Local Storage

Only the token file is stored locally; task data is never stored on disk.

Tasks API

Fetch Tasks

Endpoint:

/3/tasks/get.php

Usage:

Use pagination with page size 1000

Request only required fields

Fetch all tasks for the current command and apply filters client-side in memory

If --limit is provided, stop pagination once enough matching tasks are collected

Cached Task Fields (MVP)

The CLI SHALL materialize these fields in memory for filtering and output:

id

title

completed

folder

context

priority

star

duedate

duetime (optional)

modified

tags

Due Dates and Timezones
Interpretation

All CLI date filters are interpreted in the local timezone

Example:

--due-before 2026-02-01

Normalization

duedate:

stored as either local-midnight epoch or ISO YYYY-MM-DD

choice must be consistent

duetime:

stored as epoch seconds

Tasks with no due date:

Never match due-date filters

Sort as null

Tags
Storage

Store normalized tags as:
,tag1,tag2,

All tags lowercased

Matching

Case-insensitive

Match via substring semantics equivalent to:
LIKE '%,tag,%'

Pagination

Page size fixed at 1000 (API maximum)

No dynamic resizing in MVP

Sorting
Stability

Sorting must be stable

Use id as secondary sort key

Default Sort Order

duedate ascending (nulls last)

priority descending

id ascending

Filters (td list)

Supported filters (MVP):

--completed yes|no

--folder ID_OR_NAME

--context ID_OR_NAME

--tag TAG

--priority INT (exact match only)

--starred yes|no

--due-before YYYY-MM-DD

--due-after YYYY-MM-DD

--modified-since YYYY-MM-DD

--search SUBSTRING

Priority Filters

Exact integer only

No ranges in MVP

Rate Limits

No retry or backoff logic in MVP

On rate limit or API exhaustion:

Stop immediately

Emit a clear error message

Do not continue pagination

Output Formats

table (default)

json

csv

Portability Rules

No OS-specific shell calls

Identical behavior across all supported platforms

Definition of “Done”

The MVP is complete when:

td login authenticates successfully

td whoami confirms authentication

td list filters and displays tasks correctly

The tool runs unchanged on macOS, Linux, WSL, and Windows

Bump Overdue (td bump-overdue)

Purpose

Identify incomplete tasks with due dates earlier than today (local date) and optionally move those due dates to today or a specified date.

Behavior

Default action is dry-run: list tasks that would be updated.

Apply changes only when --apply is provided.

--date accepts YYYY-MM-DD and sets the target due date; default is today (local date).

Optional testing flags:

--limit N updates only the first N matching tasks.

--debug prints the edit payload and response for troubleshooting.

Only incomplete tasks are considered.

Tasks without due dates are ignored.

Tasks with a due time are ignored.

Repeating tasks are ignored.

Scope of edits is limited to bump-overdue due date updates only.

Update Endpoint

Use /3/tasks/edit.php

Send updates in batches (<= 50 tasks per request).

Due date updates must send duedate as a GMT Unix timestamp at noon UTC.

Client Credentials

Client ID and Client Secret must be provided via environment variables:

TOODLEDO_CLIENT_ID

TOODLEDO_CLIENT_SECRET

PowerShell helper script (local only):

set-td-env.ps1

Scheduler helper (no secrets):

run-bump-overdue.ps1

Daily run guide:

docs/how-to-bump-daily.md
