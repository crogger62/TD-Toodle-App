import sqlite3
from typing import Iterable, Optional


def _browse_where(
    service: Optional[str] = None,
    include_completed: bool = False,
    query_text: Optional[str] = None,
    uncategorized_only: bool = False,
    has_notes: bool = False,
) -> tuple[list[str], dict]:
    where = []
    params = {}
    if not include_completed:
        where.append("completed = 0")
    if service:
        where.append("service IS NOT NULL AND lower(service) = lower(:service)")
        params["service"] = service.strip()
    if query_text:
        where.append("(lower(title) LIKE :q OR lower(coalesce(notes, '')) LIKE :q)")
        params["q"] = f"%{query_text.lower()}%"
    if uncategorized_only:
        where.append("service IS NULL")
    if has_notes:
        where.append("trim(coalesce(notes, '')) <> ''")
    return where, params


def list_items(
    conn: sqlite3.Connection,
    service: Optional[str] = None,
    include_completed: bool = False,
) -> list[sqlite3.Row]:
    where, params = _browse_where(
        service=service,
        include_completed=include_completed,
    )
    sql = "SELECT * FROM watch_items"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY lower(coalesce(service, '')), lower(title), toodledo_id"
    return list(conn.execute(sql, params))


def search_items(
    conn: sqlite3.Connection,
    query: str,
    include_completed: bool = False,
) -> list[sqlite3.Row]:
    where, params = _browse_where(
        include_completed=include_completed,
        query_text=query,
    )
    sql = (
        "SELECT * FROM watch_items WHERE "
        + " AND ".join(where)
        + " ORDER BY lower(coalesce(service, '')), lower(title), toodledo_id"
    )
    return list(conn.execute(sql, params))


def get_item(conn: sqlite3.Connection, toodledo_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM watch_items WHERE toodledo_id = ?",
        (toodledo_id,),
    ).fetchone()


def service_counts(
    conn: sqlite3.Connection,
    include_completed: bool = False,
) -> list[sqlite3.Row]:
    where = "" if include_completed else "WHERE completed = 0"
    sql = f"""
        SELECT coalesce(service, '(none)') AS service, count(*) AS count
        FROM watch_items
        {where}
        GROUP BY coalesce(service, '(none)')
        ORDER BY lower(service)
    """
    return list(conn.execute(sql))


def iter_export_rows(
    conn: sqlite3.Connection,
    include_completed: bool = False,
) -> Iterable[sqlite3.Row]:
    yield from list_items(conn, include_completed=include_completed)


def browse_items(
    conn: sqlite3.Connection,
    service: Optional[str] = None,
    include_completed: bool = False,
    query_text: Optional[str] = None,
    uncategorized_only: bool = False,
    has_notes: bool = False,
    limit: int = 250,
) -> list[sqlite3.Row]:
    where, params = _browse_where(
        service=service,
        include_completed=include_completed,
        query_text=query_text,
        uncategorized_only=uncategorized_only,
        has_notes=has_notes,
    )
    sql = "SELECT * FROM watch_items"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY lower(coalesce(service, '')), lower(title), toodledo_id LIMIT :limit"
    params["limit"] = max(1, min(limit, 1000))
    return list(conn.execute(sql, params))
