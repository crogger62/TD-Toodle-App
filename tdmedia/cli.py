import argparse
import csv
import json
import sys
from typing import List, Optional

from . import __version__
from . import db
from . import query as query_module
from .sync import sync_watchlist


def _note_preview(value: Optional[str], width: int = 72) -> str:
    text = " ".join((value or "").split())
    if len(text) <= width:
        return text
    return text[: width - 3].rstrip() + "..."


def _print_items(rows) -> None:
    if not rows:
        print("No watch items found.")
        return
    for row in rows:
        service = row["service"] or "(none)"
        note = _note_preview(row["notes"])
        suffix = f" -- {note}" if note else ""
        print(f"{row['toodledo_id']}\t{service}\t{row['title']}{suffix}")


def cmd_sync(args: argparse.Namespace) -> int:
    try:
        result = sync_watchlist(args.db)
    except Exception as exc:  # noqa: BLE001
        print(f"sync failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"Imported {result['imported']} {result['folder']} item(s) "
        f"to {result['db_path']}."
    )
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    try:
        with db.connect(args.db) as conn:
            rows = query_module.list_items(
                conn,
                service=args.service,
                include_completed=args.include_completed,
            )
    except Exception as exc:  # noqa: BLE001
        print(f"list failed: {exc}", file=sys.stderr)
        return 1
    _print_items(rows)
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    try:
        with db.connect(args.db) as conn:
            rows = query_module.search_items(
                conn,
                args.query,
                include_completed=args.include_completed,
            )
    except Exception as exc:  # noqa: BLE001
        print(f"search failed: {exc}", file=sys.stderr)
        return 1
    _print_items(rows)
    return 0


def cmd_services(args: argparse.Namespace) -> int:
    try:
        with db.connect(args.db) as conn:
            rows = query_module.service_counts(
                conn,
                include_completed=args.include_completed,
            )
    except Exception as exc:  # noqa: BLE001
        print(f"services failed: {exc}", file=sys.stderr)
        return 1
    if not rows:
        print("No services found.")
        return 0
    width = max(len(row["service"]) for row in rows)
    for row in rows:
        print(f"{row['service']:<{width}}  {row['count']}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    try:
        with db.connect(args.db) as conn:
            row = query_module.get_item(conn, args.toodledo_id)
    except Exception as exc:  # noqa: BLE001
        print(f"show failed: {exc}", file=sys.stderr)
        return 1
    if row is None:
        print("Watch item not found.")
        return 1
    payload = {key: row[key] for key in row.keys()}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    try:
        with db.connect(args.db) as conn:
            rows = list(
                query_module.iter_export_rows(
                    conn,
                    include_completed=args.include_completed,
                )
            )
    except Exception as exc:  # noqa: BLE001
        print(f"export failed: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps([{key: row[key] for key in row.keys()} for row in rows], indent=2))
        return 0

    writer = csv.DictWriter(
        sys.stdout,
        fieldnames=[
            "toodledo_id",
            "title",
            "service",
            "raw_tags",
            "notes",
            "folder_id",
            "completed",
            "modified",
            "imported_at",
        ],
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row[key] for key in row.keys()})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tdmedia")
    parser.add_argument("--db", help="Path to watchlist SQLite database")
    parser.add_argument("--version", action="version", version=f"tdmedia {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_parser = subparsers.add_parser("sync", help="Import Toodledo WatchList tasks")
    sync_parser.set_defaults(func=cmd_sync)

    list_parser = subparsers.add_parser("list", help="List imported watch items")
    list_parser.add_argument("--service", help="Filter by streaming service tag")
    list_parser.add_argument(
        "--include-completed",
        action="store_true",
        help="Include completed Toodledo tasks",
    )
    list_parser.set_defaults(func=cmd_list)

    search_parser = subparsers.add_parser("search", help="Search titles and notes")
    search_parser.add_argument("query", help="Search text")
    search_parser.add_argument(
        "--include-completed",
        action="store_true",
        help="Include completed Toodledo tasks",
    )
    search_parser.set_defaults(func=cmd_search)

    services_parser = subparsers.add_parser("services", help="List service counts")
    services_parser.add_argument(
        "--include-completed",
        action="store_true",
        help="Include completed Toodledo tasks",
    )
    services_parser.set_defaults(func=cmd_services)

    show_parser = subparsers.add_parser("show", help="Show one watch item as JSON")
    show_parser.add_argument("toodledo_id", type=int)
    show_parser.set_defaults(func=cmd_show)

    export_parser = subparsers.add_parser("export", help="Export watch items")
    export_parser.add_argument("--format", choices=["json", "csv"], default="json")
    export_parser.add_argument(
        "--include-completed",
        action="store_true",
        help="Include completed Toodledo tasks",
    )
    export_parser.set_defaults(func=cmd_export)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
