import html
import json
import socket
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse

from . import db
from . import query as query_module
from .sync import sync_watchlist


DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8766


def _bool_param(params: dict, name: str) -> bool:
    value = (params.get(name) or [""])[0].strip().lower()
    return value in {"1", "true", "yes", "on"}


def _first_param(params: dict, name: str) -> str:
    return (params.get(name) or [""])[0].strip()


def _build_query_string(
    search: str,
    service: str,
    selected_id: Optional[int],
    include_completed: bool,
    uncategorized_only: bool,
    has_notes: bool,
    message: str = "",
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
    include_completed = _bool_param(params, "completed")
    uncategorized_only = _bool_param(params, "uncategorized")
    has_notes = _bool_param(params, "notes")
    selected_raw = _first_param(params, "id")
    selected_id = int(selected_raw) if selected_raw.isdigit() else None

    with db.connect(db_path) as conn:
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
            <a class="{selected_class}" href="/?{html.escape(href_qs, quote=True)}">
              <div class="result-title">{html.escape(row['title'])}</div>
              <div class="result-meta">
                <span>{html.escape(row_service)}</span>
                <span>#{row_id}</span>
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

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>tdmedia browser</title>
  <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%230d6b5d'/%3E%3Cpath d='M24 18 L46 32 L24 46 Z' fill='%23f4efe5'/%3E%3C/svg%3E">
  <style>
    :root {{
      --bg: #f4efe5;
      --panel: rgba(255, 252, 247, 0.94);
      --ink: #1f1b16;
      --muted: #6f6458;
      --line: rgba(84, 64, 40, 0.14);
      --accent: #0d6b5d;
      --accent-soft: rgba(13, 107, 93, 0.12);
      --shadow: 0 20px 45px rgba(72, 44, 18, 0.12);
      --radius: 22px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(13, 107, 93, 0.18), transparent 34%),
        radial-gradient(circle at top right, rgba(194, 108, 62, 0.16), transparent 28%),
        linear-gradient(180deg, #f7f2e8 0%, #f1e8d8 100%);
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
    .actions {{
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }}
    .sync-form, .filter-form {{
      display: contents;
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
      background: rgba(255, 255, 255, 0.75);
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
      background: rgba(255, 255, 255, 0.82);
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
      border: 1px solid rgba(255, 255, 255, 0.55);
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
      background: rgba(255, 255, 255, 0.52);
    }}
    .result-card:hover, .result-card.selected {{
      border-color: rgba(13, 107, 93, 0.2);
      background: rgba(13, 107, 93, 0.08);
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
    .result-note {{
      color: #564a3c;
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
    .detail h3 {{
      margin: 20px 0 8px;
      font-size: 1rem;
    }}
    .detail-notes, .detail-json {{
      white-space: pre-wrap;
      word-break: break-word;
      background: rgba(255, 255, 255, 0.68);
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
    }}
  </style>
</head>
<body>
  <div class="shell">
    <div class="topbar">
      <div class="brand">
        <h1>Watch List Browser</h1>
        <p>Browse your local tdmedia catalog without leaving the machine.</p>
      </div>
      <div class="actions">
        <form class="sync-form" method="post" action="/sync">
          <input type="hidden" name="q" value="{html.escape(search, quote=True)}">
          <input type="hidden" name="service" value="{html.escape(service, quote=True)}">
          <input type="hidden" name="id" value="{html.escape(str(selected_id or ''), quote=True)}">
          <input type="hidden" name="completed" value="{1 if include_completed else 0}">
          <input type="hidden" name="uncategorized" value="{1 if uncategorized_only else 0}">
          <input type="hidden" name="notes" value="{1 if has_notes else 0}">
          <button type="submit">Sync Now</button>
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
  </div>
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
            if self.path != "/sync":
                self.send_error(HTTPStatus.NOT_FOUND, "Not found")
                return
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length).decode("utf-8")
            params = parse_qs(raw_body)
            try:
                result = sync_watchlist(db_path)
                message = (
                    f"Synced {result['imported']} item(s) from {result['folder']}."
                )
            except Exception as exc:  # noqa: BLE001
                message = f"Sync failed: {exc}"
            qs = _build_query_string(
                search=_first_param(params, "q"),
                service=_first_param(params, "service"),
                selected_id=int(_first_param(params, "id"))
                if _first_param(params, "id").isdigit()
                else None,
                include_completed=_bool_param(params, "completed"),
                uncategorized_only=_bool_param(params, "uncategorized"),
                has_notes=_bool_param(params, "notes"),
                message=message,
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
