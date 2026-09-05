import html
import json
import secrets
import socket
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse

from td import auth

from . import __version__
from . import db
from . import query as query_module
from .sync import complete_watch_item, sync_watchlist


DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8766
CSRF_TOKEN = secrets.token_urlsafe(32)


def _bool_param(params: dict, name: str) -> bool:
    value = (params.get(name) or [""])[0].strip().lower()
    return value in {"1", "true", "yes", "on"}


def _first_param(params: dict, name: str) -> str:
    return (params.get(name) or [""])[0].strip()


def _format_sync_timestamp(value: Optional[str]) -> str:
    if not value:
        return "No successful sync recorded yet."
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError:
        return value
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    local_timestamp = timestamp.astimezone()
    timezone_name = local_timestamp.tzname() or "local time"
    return (
        f"Last successful sync: {local_timestamp.strftime('%b')} "
        f"{local_timestamp.day}, {local_timestamp.year} at "
        f"{local_timestamp.strftime('%I:%M %p').lstrip('0')} "
        f"{timezone_name}."
    )


def _build_query_string(
    search: str,
    service: str,
    selected_id: Optional[int],
    include_completed: bool,
    uncategorized_only: bool,
    has_notes: bool,
    message: str = "",
    message_type: str = "",
) -> str:
    payload = {}
    if search:
        payload["q"] = search
    if service:
        payload["service"] = service
    if selected_id is not None:
        payload["id"] = str(selected_id)
    if include_completed:
        payload["completed"] = "1"
    if uncategorized_only:
        payload["uncategorized"] = "1"
    if has_notes:
        payload["notes"] = "1"
    if message:
        payload["message"] = message
    if message_type:
        payload["message_type"] = message_type
    return urlencode(payload)


def _service_link(
    label: str,
    service: str,
    search: str,
    selected_id: Optional[int],
    include_completed: bool,
    uncategorized_only: bool,
    has_notes: bool,
    active: bool,
) -> str:
    qs = _build_query_string(
        search=search,
        service=service,
        selected_id=selected_id,
        include_completed=include_completed,
        uncategorized_only=uncategorized_only,
        has_notes=has_notes,
    )
    class_name = "service-link active" if active else "service-link"
    href = "/"
    if qs:
        href += "?" + qs
    return (
        f'<a class="{class_name}" href="{html.escape(href, quote=True)}">'
        f"{html.escape(label)}</a>"
    )


def _render_page(db_path: Optional[str], params: dict) -> str:
    search = _first_param(params, "q")
    service = _first_param(params, "service")
    message = _first_param(params, "message")
    message_type = _first_param(params, "message_type")
    include_completed = _bool_param(params, "completed")
    uncategorized_only = _bool_param(params, "uncategorized")
    has_notes = _bool_param(params, "notes")
    selected_raw = _first_param(params, "id")
    selected_id = int(selected_raw) if selected_raw.isdigit() else None

    with db.connect(db_path) as conn:
        last_sync = db.last_successful_sync(conn)
        last_sync_run = db.latest_sync_run(conn)
        rows = query_module.browse_items(
            conn,
            service=service or None,
            include_completed=include_completed,
            query_text=search or None,
            uncategorized_only=uncategorized_only,
            has_notes=has_notes,
            limit=300,
        )
        services = query_module.service_counts(conn, include_completed=include_completed)
        selected_row = None
        if selected_id is not None:
            selected_row = query_module.get_item(conn, selected_id)
        if selected_row is None and rows:
            selected_row = rows[0]
            selected_id = int(selected_row["toodledo_id"])

    # Legacy error flashes did not include a type, so discard one when a later
    # successful sync is already recorded instead of showing stale failure text.
    if (
        message_type == ""
        and message.startswith("Sync failed:")
        and last_sync_run is not None
    ):
        message = ""

    list_items = []
    for row in rows:
        row_service = row["service"] or "(none)"
        row_id = int(row["toodledo_id"])
        href_qs = _build_query_string(
            search=search,
            service=service,
            selected_id=row_id,
            include_completed=include_completed,
            uncategorized_only=uncategorized_only,
            has_notes=has_notes,
        )
        selected_class = "result-card selected" if row_id == selected_id else "result-card"
        note = " ".join((row["notes"] or "").split())
        note_preview = note[:137].rstrip() + "..." if len(note) > 140 else note
        list_items.append(
            f"""
            <a class="{selected_class}" data-toodledo-id="{row_id}" href="/?{html.escape(href_qs, quote=True)}">
              <div class="result-title">{html.escape(row['title'])}</div>
              <div class="result-meta">
                <span>{html.escape(row_service)}</span>
                <span>#{row_id}</span>
                <span class="result-pending-label">Completion preview</span>
              </div>
              <div class="result-note">{html.escape(note_preview or "No notes")}</div>
            </a>
            """
        )

    sidebar_links = [
        _service_link(
            label="All services",
            service="",
            search=search,
            selected_id=selected_id,
            include_completed=include_completed,
            uncategorized_only=uncategorized_only,
            has_notes=has_notes,
            active=not service,
        )
    ]
    for row in services:
        raw_service = row["service"]
        link_service = "" if raw_service == "(none)" else raw_service
        label = f"{raw_service} ({row['count']})"
        sidebar_links.append(
            _service_link(
                label=label,
                service=link_service,
                search=search,
                selected_id=selected_id,
                include_completed=include_completed,
                uncategorized_only=uncategorized_only,
                has_notes=has_notes,
                active=service == link_service,
            )
        )

    detail_html = '<div class="empty-state">No item selected.</div>'
    if selected_row is not None:
        payload = {key: selected_row[key] for key in selected_row.keys()}
        completion_action_html = ""
        if not selected_row["completed"]:
            completion_action_html = f"""
            <form class="completion-action" data-toodledo-id="{selected_row['toodledo_id']}" method="post" action="/complete" id="complete-form">
              <input type="hidden" name="csrf_token" value="{CSRF_TOKEN}">
              <input type="hidden" name="toodledo_id" value="{selected_row['toodledo_id']}">
              <input type="hidden" name="q" value="{html.escape(search, quote=True)}">
              <input type="hidden" name="service" value="{html.escape(service, quote=True)}">
              <input type="hidden" name="completed" value="{1 if include_completed else 0}">
              <input type="hidden" name="uncategorized" value="{1 if uncategorized_only else 0}">
              <input type="hidden" name="notes" value="{1 if has_notes else 0}">
              <button class="complete-trigger" type="button" id="complete-trigger" aria-controls="complete-confirmation" aria-expanded="false">
                No longer needed
              </button>
              <div class="complete-confirmation" id="complete-confirmation" hidden>
                <p>Mark this task complete in Toodledo?</p>
                <p class="completion-preview-note">This item will disappear from the active listing after completion.</p>
                <div class="completion-actions">
                  <button class="secondary" type="button" id="complete-cancel">Cancel</button>
                  <button type="submit" id="complete-submit">
                    <span class="complete-submit-idle">Complete in Toodledo</span>
                    <span class="complete-submit-busy"><span class="sync-spinner" aria-hidden="true"></span>Completing...</span>
                  </button>
                </div>
                <span class="completion-progress" role="status" aria-live="polite">
                  <span class="sync-spinner" aria-hidden="true"></span>Updating Toodledo...
                </span>
              </div>
            </form>
            """
        detail_html = f"""
        <div class="detail-header">
          <h2>{html.escape(selected_row['title'])}</h2>
          <div class="detail-chip-row">
            <span class="detail-chip">service: {html.escape(selected_row['service'] or '(none)')}</span>
            <span class="detail-chip">id: {selected_row['toodledo_id']}</span>
            <span class="detail-chip">completed: {selected_row['completed']}</span>
          </div>
        </div>
        <dl class="detail-grid">
          <dt>Raw tags</dt>
          <dd>{html.escape(selected_row['raw_tags'] or '(none)')}</dd>
          <dt>Imported</dt>
          <dd>{html.escape(selected_row['imported_at'] or '(unknown)')}</dd>
          <dt>Modified</dt>
          <dd>{html.escape(str(selected_row['modified']) if selected_row['modified'] is not None else '(unknown)')}</dd>
          <dt>Folder ID</dt>
          <dd>{html.escape(str(selected_row['folder_id']))}</dd>
        </dl>
        {completion_action_html}
        <h3>Notes</h3>
        <pre class="detail-notes">{html.escape(selected_row['notes'] or '')}</pre>
        <h3>JSON</h3>
        <pre class="detail-json">{html.escape(json.dumps(payload, indent=2, sort_keys=True))}</pre>
        """

    results_heading = f"{len(rows)} item(s)"
    if search:
        results_heading += f" matching '{search}'"

    checked_completed = "checked" if include_completed else ""
    checked_uncategorized = "checked" if uncategorized_only else ""
    checked_notes = "checked" if has_notes else ""
    message_html = (
        f'<div class="flash">{html.escape(message)}</div>' if message else ""
    )
    sync_status = _format_sync_timestamp(last_sync)
    sync_metrics_html = ""
    if last_sync_run is not None:
        net_change = int(last_sync_run["added"]) - int(last_sync_run["deleted"])
        sync_metrics_html = f"""
        <dl class="sync-metrics" aria-label="Last sync metrics">
          <div><dt>Fetched</dt><dd>{last_sync_run['fetched']}</dd></div>
          <div><dt>Added</dt><dd>{last_sync_run['added']}</dd></div>
          <div><dt>Deleted</dt><dd>{last_sync_run['deleted']}</dd></div>
          <div><dt>Net change</dt><dd>{net_change:+d}</dd></div>
        </dl>
        """

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>tdmedia browser</title>
  <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%235b7553'/%3E%3Cpath d='M24 18 L46 32 L24 46 Z' fill='%23c3e8bd'/%3E%3C/svg%3E">
  <style>
    :root {{
      --bg: #c3e8bd;
      --panel: rgba(238, 250, 234, 0.9);
      --ink: #040403;
      --muted: #5b7553;
      --line: rgba(91, 117, 83, 0.24);
      --accent: #5b7553;
      --accent-soft: rgba(142, 184, 151, 0.42);
      --shadow: 0 20px 45px rgba(4, 4, 3, 0.14);
      --radius: 22px;
      --glow-1: rgba(157, 219, 173, 0.8);
      --glow-2: rgba(142, 184, 151, 0.46);
      --bg-grad-from: #c3e8bd;
      --bg-grad-to: #8eb897;
      --surface-soft: rgba(255, 255, 255, 0.42);
      --surface-mid: rgba(255, 255, 255, 0.55);
      --surface-strong: rgba(255, 255, 255, 0.7);
      --surface-border: rgba(255, 255, 255, 0.64);
      --hover-border: rgba(91, 117, 83, 0.55);
      --hover-bg: rgba(157, 219, 173, 0.5);
      --note-ink: #040403;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #040403;
        --panel: rgba(18, 27, 17, 0.88);
        --ink: #c3e8bd;
        --muted: #9ddbad;
        --line: rgba(195, 232, 189, 0.2);
        --accent: #8eb897;
        --accent-soft: rgba(91, 117, 83, 0.5);
        --shadow: 0 20px 45px rgba(0, 0, 0, 0.55);
        --glow-1: rgba(91, 117, 83, 0.34);
        --glow-2: rgba(142, 184, 151, 0.12);
        --bg-grad-from: #101510;
        --bg-grad-to: #040403;
        --surface-soft: rgba(195, 232, 189, 0.07);
        --surface-mid: rgba(195, 232, 189, 0.11);
        --surface-strong: rgba(195, 232, 189, 0.16);
        --surface-border: rgba(195, 232, 189, 0.16);
        --hover-border: rgba(157, 219, 173, 0.56);
        --hover-bg: rgba(91, 117, 83, 0.38);
        --note-ink: #c3e8bd;
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, var(--glow-1), transparent 34%),
        radial-gradient(circle at top right, var(--glow-2), transparent 28%),
        linear-gradient(180deg, var(--bg-grad-from) 0%, var(--bg-grad-to) 100%);
      font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
    }}
    .shell {{
      min-height: 100vh;
      padding: 24px;
    }}
    .topbar {{
      display: flex;
      gap: 16px;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 18px;
      flex-wrap: wrap;
    }}
    .brand h1 {{
      margin: 0;
      font-size: 2rem;
      letter-spacing: -0.03em;
    }}
    .brand p {{
      margin: 4px 0 0;
      color: var(--muted);
    }}
    .sync-status {{
      display: inline-flex;
      margin: 10px 0 0;
      padding: 7px 11px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--surface-soft);
      color: var(--muted);
      font-size: 0.9rem;
    }}
    .sync-metrics {{
      display: grid;
      grid-template-columns: repeat(4, minmax(76px, 1fr));
      gap: 8px;
      margin: 10px 0 0;
    }}
    .sync-metrics div {{
      padding: 8px 10px;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: var(--surface-soft);
    }}
    .sync-metrics dt {{
      color: var(--muted);
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .sync-metrics dd {{
      margin: 3px 0 0;
      font-size: 1.08rem;
      font-weight: bold;
    }}
    .actions {{
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }}
    .sync-form, .filter-form {{
      display: contents;
    }}
    .sync-button-busy, .sync-progress {{
      display: none;
    }}
    .sync-form.is-syncing .sync-button-idle {{
      display: none;
    }}
    .sync-form.is-syncing .sync-button-busy {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
    }}
    .sync-form.is-syncing .sync-progress {{
      display: inline-flex;
      align-items: center;
      gap: 7px;
      color: var(--muted);
      font-size: 0.9rem;
    }}
    .sync-spinner {{
      width: 0.9rem;
      height: 0.9rem;
      border: 2px solid currentColor;
      border-right-color: transparent;
      border-radius: 50%;
      animation: sync-spin 0.8s linear infinite;
    }}
    @keyframes sync-spin {{
      to {{ transform: rotate(360deg); }}
    }}
    button:disabled {{
      cursor: wait;
      opacity: 0.78;
    }}
    button, .button-link {{
      border: 0;
      border-radius: 999px;
      padding: 12px 16px;
      font: inherit;
      cursor: pointer;
      color: white;
      background: var(--accent);
      text-decoration: none;
      box-shadow: var(--shadow);
    }}
    .button-link.secondary, button.secondary {{
      color: var(--ink);
      background: var(--surface-strong);
    }}
    .flash {{
      margin-bottom: 14px;
      padding: 12px 16px;
      border-radius: 16px;
      background: var(--accent-soft);
      color: var(--ink);
    }}
    .controls {{
      display: grid;
      grid-template-columns: minmax(220px, 2fr) repeat(3, auto);
      gap: 12px;
      margin-bottom: 18px;
      align-items: center;
    }}
    .controls input[type="search"] {{
      width: 100%;
      padding: 14px 16px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: var(--surface-strong);
      font: inherit;
    }}
    .check {{
      display: flex;
      gap: 8px;
      align-items: center;
      color: var(--muted);
      font-size: 0.98rem;
    }}
    .layout {{
      display: grid;
      grid-template-columns: 250px minmax(320px, 1.2fr) minmax(320px, 1fr);
      gap: 18px;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--surface-border);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      backdrop-filter: blur(12px);
    }}
    .panel-head {{
      padding: 18px 20px 10px;
      border-bottom: 1px solid var(--line);
    }}
    .panel-head h2, .panel-head h3 {{
      margin: 0;
      font-size: 1.05rem;
    }}
    .panel-head p {{
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 0.95rem;
    }}
    .service-list {{
      display: flex;
      flex-direction: column;
      padding: 12px;
      max-height: calc(100vh - 240px);
      overflow: auto;
    }}
    .service-link {{
      color: var(--ink);
      text-decoration: none;
      border-radius: 16px;
      padding: 10px 12px;
      margin-bottom: 6px;
    }}
    .service-link:hover, .service-link.active {{
      background: var(--accent-soft);
    }}
    .results {{
      padding: 10px;
      max-height: calc(100vh - 240px);
      overflow: auto;
    }}
    .result-card {{
      display: block;
      text-decoration: none;
      color: inherit;
      border: 1px solid transparent;
      border-radius: 18px;
      padding: 14px;
      margin-bottom: 10px;
      background: var(--surface-soft);
    }}
    .result-card:hover, .result-card.selected {{
      border-color: var(--hover-border);
      background: var(--hover-bg);
    }}
    .result-card.is-completion-preview {{
      opacity: 0.58;
      border-style: dashed;
    }}
    .result-title {{
      font-size: 1.05rem;
      margin-bottom: 8px;
    }}
    .result-meta {{
      display: flex;
      gap: 10px;
      color: var(--muted);
      font-size: 0.92rem;
      margin-bottom: 8px;
      flex-wrap: wrap;
    }}
    .result-pending-label {{
      display: none;
      color: var(--accent);
      font-weight: bold;
    }}
    .result-card.is-completion-preview .result-pending-label {{
      display: inline;
    }}
    .result-note {{
      color: var(--note-ink);
      font-size: 0.95rem;
      line-height: 1.4;
    }}
    .detail {{
      padding: 18px 20px 22px;
      max-height: calc(100vh - 240px);
      overflow: auto;
    }}
    .detail-header h2 {{
      margin: 0 0 12px;
      font-size: 1.55rem;
      line-height: 1.15;
    }}
    .detail-chip-row {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 18px;
    }}
    .detail-chip {{
      border-radius: 999px;
      background: var(--accent-soft);
      padding: 7px 12px;
      color: var(--ink);
      font-size: 0.92rem;
    }}
    .detail-grid {{
      display: grid;
      grid-template-columns: 120px 1fr;
      gap: 8px 12px;
      margin: 0 0 20px;
    }}
    .detail-grid dt {{
      color: var(--muted);
    }}
    .detail-grid dd {{
      margin: 0;
      word-break: break-word;
    }}
    .completion-action {{
      margin: 0 0 20px;
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 18px;
      background: var(--surface-soft);
    }}
    .complete-trigger {{
      width: 100%;
    }}
    .complete-confirmation {{
      margin-top: 12px;
    }}
    .complete-confirmation p {{
      margin: 0;
    }}
    .completion-note {{
      margin-top: 5px !important;
      color: var(--muted);
      font-size: 0.9rem;
    }}
    .completion-preview-note {{
      margin-top: 9px !important;
      font-size: 0.9rem;
    }}
    .completion-actions {{
      display: flex;
      gap: 8px;
      margin-top: 12px;
      flex-wrap: wrap;
    }}
    .complete-submit-busy, .completion-progress {{
      display: none;
    }}
    .completion-action.is-completing .complete-submit-idle {{
      display: none;
    }}
    .completion-action.is-completing .complete-submit-busy, .completion-action.is-completing .completion-progress {{
      display: inline-flex;
      align-items: center;
      gap: 7px;
    }}
    .completion-progress {{
      margin-top: 12px;
      color: var(--muted);
      font-size: 0.9rem;
    }}
    .detail h3 {{
      margin: 20px 0 8px;
      font-size: 1rem;
    }}
    .detail-notes, .detail-json {{
      white-space: pre-wrap;
      word-break: break-word;
      background: var(--surface-mid);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 14px;
      margin: 0;
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
      font-size: 0.9rem;
    }}
    .empty-state {{
      color: var(--muted);
      padding: 18px 0;
    }}
    .app-version {{
      margin: 18px 4px 0;
      color: var(--muted);
      font-size: 0.82rem;
      text-align: right;
    }}
    @media (max-width: 1100px) {{
      .layout {{
        grid-template-columns: 1fr;
      }}
      .service-list, .results, .detail {{
        max-height: none;
      }}
      .controls {{
        grid-template-columns: 1fr;
      }}
      .sync-metrics {{
        grid-template-columns: repeat(2, minmax(110px, 1fr));
      }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <div class="topbar">
      <div class="brand">
        <h1>Watch List Browser</h1>
        <p>Browse your local tdmedia catalog without leaving the machine.</p>
        <div class="sync-status">{html.escape(sync_status)}</div>
        {sync_metrics_html}
      </div>
      <div class="actions">
        <form class="sync-form" method="post" action="/sync" id="sync-form">
          <input type="hidden" name="csrf_token" value="{CSRF_TOKEN}">
          <input type="hidden" name="q" value="{html.escape(search, quote=True)}">
          <input type="hidden" name="service" value="{html.escape(service, quote=True)}">
          <input type="hidden" name="id" value="{html.escape(str(selected_id or ''), quote=True)}">
          <input type="hidden" name="completed" value="{1 if include_completed else 0}">
          <input type="hidden" name="uncategorized" value="{1 if uncategorized_only else 0}">
          <input type="hidden" name="notes" value="{1 if has_notes else 0}">
          <button type="submit" id="sync-button">
            <span class="sync-button-idle">Sync Now</span>
            <span class="sync-button-busy"><span class="sync-spinner" aria-hidden="true"></span>Syncing...</span>
          </button>
          <span class="sync-progress" role="status" aria-live="polite">
            <span class="sync-spinner" aria-hidden="true"></span>Updating from Toodledo...
          </span>
        </form>
        <a class="button-link secondary" href="/export?format=json">Export JSON</a>
        <a class="button-link secondary" href="/export?format=csv">Export CSV</a>
      </div>
    </div>
    {message_html}
    <form class="filter-form" method="get" action="/">
      <div class="controls">
        <input type="search" name="q" value="{html.escape(search, quote=True)}" placeholder="Search title or notes">
        <label class="check"><input type="checkbox" name="uncategorized" value="1" {checked_uncategorized}> Uncategorized</label>
        <label class="check"><input type="checkbox" name="notes" value="1" {checked_notes}> Has notes</label>
        <label class="check"><input type="checkbox" name="completed" value="1" {checked_completed}> Include completed</label>
      </div>
    </form>
    <div class="layout">
      <aside class="panel">
        <div class="panel-head">
          <h2>Services</h2>
          <p>Filter by normalized service bucket.</p>
        </div>
        <div class="service-list">
          {''.join(sidebar_links)}
        </div>
      </aside>
      <section class="panel">
        <div class="panel-head">
          <h2>Results</h2>
          <p>{html.escape(results_heading)}</p>
        </div>
        <div class="results">
          {''.join(list_items) if list_items else '<div class="empty-state">No matching items.</div>'}
        </div>
      </section>
      <section class="panel">
        <div class="panel-head">
          <h2>Details</h2>
          <p>Original raw tags are preserved here even when service is normalized away.</p>
        </div>
        <div class="detail">
          {detail_html}
        </div>
      </section>
    </div>
    <footer class="app-version">tdmedia v{html.escape(__version__)}</footer>
  </div>
  <script>
    const syncForm = document.getElementById("sync-form");
    const syncButton = document.getElementById("sync-button");
    if (syncForm && syncButton) {{
      syncForm.addEventListener("submit", () => {{
        syncForm.classList.add("is-syncing");
        syncButton.disabled = true;
        syncButton.setAttribute("aria-busy", "true");
      }});
    }}

    const completeTrigger = document.getElementById("complete-trigger");
    const completeConfirmation = document.getElementById("complete-confirmation");
    const completeCancel = document.getElementById("complete-cancel");
    const completeForm = document.getElementById("complete-form");
    const completeSubmit = document.getElementById("complete-submit");
    if (completeTrigger && completeConfirmation && completeCancel && completeForm && completeSubmit) {{
      completeTrigger.addEventListener("click", () => {{
        completeConfirmation.hidden = false;
        completeTrigger.setAttribute("aria-expanded", "true");
        document
          .querySelector(`.result-card[data-toodledo-id="${{completeTrigger.parentElement.dataset.toodledoId}}"]`)
          ?.classList.add("is-completion-preview");
      }});
      completeCancel.addEventListener("click", () => {{
        completeConfirmation.hidden = true;
        completeTrigger.setAttribute("aria-expanded", "false");
        document
          .querySelector(`.result-card[data-toodledo-id="${{completeTrigger.parentElement.dataset.toodledoId}}"]`)
          ?.classList.remove("is-completion-preview");
        completeTrigger.focus();
      }});
      completeForm.addEventListener("submit", () => {{
        completeForm.classList.add("is-completing");
        completeTrigger.disabled = true;
        completeSubmit.disabled = true;
        completeSubmit.setAttribute("aria-busy", "true");
      }});
    }}

    if (document.querySelector(".flash")) {{
      const url = new URL(window.location.href);
      url.searchParams.delete("message");
      url.searchParams.delete("message_type");
      window.history.replaceState({{}}, "", url);
    }}
  </script>
</body>
</html>
"""


def _export_rows(db_path: Optional[str], format_name: str) -> tuple[str, bytes]:
    with db.connect(db_path) as conn:
        rows = [
            {key: row[key] for key in row.keys()}
            for row in query_module.iter_export_rows(conn, include_completed=True)
        ]
    if format_name == "csv":
        header = [
            "toodledo_id",
            "title",
            "service",
            "raw_tags",
            "notes",
            "folder_id",
            "completed",
            "modified",
            "imported_at",
        ]
        lines = [",".join(header)]
        for row in rows:
            lines.append(
                ",".join(
                    json.dumps("" if row.get(column) is None else row.get(column))[1:-1]
                    for column in header
                )
            )
        return "text/csv; charset=utf-8", ("\n".join(lines) + "\n").encode("utf-8")
    return "application/json; charset=utf-8", json.dumps(rows, indent=2).encode("utf-8")


def serve_browser(
    db_path: Optional[str] = None,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> None:
    class BrowserHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            if parsed.path == "/export":
                format_name = _first_param(params, "format") or "json"
                content_type, payload = _export_rows(db_path, format_name)
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            if parsed.path != "/":
                self.send_error(HTTPStatus.NOT_FOUND, "Not found")
                return
            payload = _render_page(db_path, params).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):  # noqa: N802
            if self.path not in {"/sync", "/complete"}:
                self.send_error(HTTPStatus.NOT_FOUND, "Not found")
                return
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length).decode("utf-8")
            params = parse_qs(raw_body)
            if not secrets.compare_digest(_first_param(params, "csrf_token"), CSRF_TOKEN):
                self.send_error(HTTPStatus.FORBIDDEN, "Invalid form token. Refresh and try again.")
                return

            selected_id = (
                int(_first_param(params, "id"))
                if _first_param(params, "id").isdigit()
                else None
            )
            if self.path == "/complete":
                raw_toodledo_id = _first_param(params, "toodledo_id")
                if not raw_toodledo_id.isdigit() or int(raw_toodledo_id) <= 0:
                    message = "Completion failed: invalid Watch List item."
                    message_type = "error"
                else:
                    toodledo_id = int(raw_toodledo_id)
                    try:
                        result = complete_watch_item(toodledo_id, db_path)
                        message = f"Marked {result['title']} complete in Toodledo."
                        message_type = "success"
                        selected_id = None
                    except Exception as exc:  # noqa: BLE001
                        message = (
                            f"Completion failed: {auth.redact_sensitive_text(exc)}"
                        )
                        message_type = "error"
            else:
                try:
                    result = sync_watchlist(db_path)
                    message = (
                        f"Synced {result['imported']} item(s) from {result['folder']}: "
                        f"{result['added']} added, {result['deleted']} deleted."
                    )
                    message_type = "success"
                except Exception as exc:  # noqa: BLE001
                    message = f"Sync failed: {auth.redact_sensitive_text(exc)}"
                    message_type = "error"
            qs = _build_query_string(
                search=_first_param(params, "q"),
                service=_first_param(params, "service"),
                selected_id=selected_id,
                include_completed=_bool_param(params, "completed"),
                uncategorized_only=_bool_param(params, "uncategorized"),
                has_notes=_bool_param(params, "notes"),
                message=message,
                message_type=message_type,
            )
            target = "/"
            if qs:
                target += "?" + qs
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", target)
            self.end_headers()

        def log_message(self, format, *args):  # noqa: A002
            return

    server = ThreadingHTTPServer((host, port), BrowserHandler)
    hostname = socket.gethostname()
    if host == "0.0.0.0":
        print(f"Serving tdmedia browser on all interfaces at port {port}")
        print(f"Local:   http://127.0.0.1:{port}")
        print(f"Network: http://{hostname}:{port}")
    else:
        print(f"Serving tdmedia browser at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    finally:
        server.server_close()
