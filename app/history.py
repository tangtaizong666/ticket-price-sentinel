from datetime import date, datetime, UTC
import json
import sqlite3

from app.db import connect
from app.models import HistoryRecord, SearchRequest, SessionState
from app.settings import Settings


def save_history(settings: Settings, request: SearchRequest) -> HistoryRecord:
    now = datetime.now(UTC).isoformat()
    payload = (
        request.origin_city,
        request.destination_city,
        request.departure_date.isoformat(),
        request.max_price,
        json.dumps(request.departure_time_filters, ensure_ascii=False),
        json.dumps(request.flight_attribute_filters, ensure_ascii=False),
        json.dumps(request.airline_filters, ensure_ascii=False),
        now,
        now,
        now,
    )
    with connect(settings) as connection:
        cursor = connection.execute(
            """
            INSERT INTO search_history (
                origin_city,
                destination_city,
                departure_date,
                max_price,
                departure_time_filters,
                flight_attribute_filters,
                airline_filters,
                last_searched_at,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            payload,
        )
        row = connection.execute(
            "SELECT * FROM search_history WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()

    return _row_to_history(row)


def list_history(settings: Settings) -> list[HistoryRecord]:
    with connect(settings) as connection:
        rows = connection.execute(
            "SELECT * FROM search_history ORDER BY updated_at DESC"
        ).fetchall()

    return [_row_to_history(row) for row in rows]


def get_history(settings: Settings, history_id: int) -> HistoryRecord | None:
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT * FROM search_history WHERE id = ?",
            (history_id,),
        ).fetchone()

    if row is None:
        return None

    return _row_to_history(row)


def update_history(
    settings: Settings, history_id: int, request: SearchRequest
) -> HistoryRecord:
    now = datetime.now(UTC).isoformat()
    payload = (
        request.origin_city,
        request.destination_city,
        request.departure_date.isoformat(),
        request.max_price,
        json.dumps(request.departure_time_filters, ensure_ascii=False),
        json.dumps(request.flight_attribute_filters, ensure_ascii=False),
        json.dumps(request.airline_filters, ensure_ascii=False),
        now,
        history_id,
    )
    with connect(settings) as connection:
        connection.execute(
            """
            UPDATE search_history
            SET origin_city = ?,
                destination_city = ?,
                departure_date = ?,
                max_price = ?,
                departure_time_filters = ?,
                flight_attribute_filters = ?,
                airline_filters = ?,
                updated_at = ?
            WHERE id = ?
            """,
            payload,
        )
        row = connection.execute(
            "SELECT * FROM search_history WHERE id = ?",
            (history_id,),
        ).fetchone()

    return _row_to_history(row)


def save_session_state(
    settings: Settings,
    session_status: str,
    last_successful_scrape_at: str | None = None,
) -> SessionState:
    now = datetime.now(UTC).isoformat()
    with connect(settings) as connection:
        connection.execute(
            """
            INSERT INTO session_state (id, session_status, last_successful_scrape_at, updated_at)
            VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                session_status = excluded.session_status,
                last_successful_scrape_at = excluded.last_successful_scrape_at,
                updated_at = excluded.updated_at
            """,
            (session_status, last_successful_scrape_at, now),
        )
        row = connection.execute(
            "SELECT * FROM session_state WHERE id = 1"
        ).fetchone()

    return _row_to_session_state(row)


def get_session_state(settings: Settings) -> SessionState | None:
    with connect(settings) as connection:
        row = connection.execute("SELECT * FROM session_state WHERE id = 1").fetchone()

    if row is None:
        return None

    return _row_to_session_state(row)


def _row_to_session_state(row: sqlite3.Row) -> SessionState:
    return SessionState(
        id=row["id"],
        session_status=row["session_status"],
        last_successful_scrape_at=(
            datetime.fromisoformat(row["last_successful_scrape_at"])
            if row["last_successful_scrape_at"]
            else None
        ),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _row_to_history(row: sqlite3.Row) -> HistoryRecord:
    return HistoryRecord(
        id=row["id"],
        origin_city=row["origin_city"],
        destination_city=row["destination_city"],
        departure_date=date.fromisoformat(row["departure_date"]),
        max_price=row["max_price"],
        departure_time_filters=json.loads(row["departure_time_filters"]),
        flight_attribute_filters=json.loads(row["flight_attribute_filters"]),
        airline_filters=json.loads(row["airline_filters"]),
        last_searched_at=datetime.fromisoformat(row["last_searched_at"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )
