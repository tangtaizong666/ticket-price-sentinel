from datetime import UTC, date, datetime, timedelta
import json
import sqlite3

from app.db import connect
from app.models import MonitorHit, MonitorTask, MonitorTaskCreate, MonitorTaskUpdate
from app.settings import Settings


def create_monitor_task(settings: Settings, payload: MonitorTaskCreate) -> MonitorTask:
    now = datetime.now(UTC)
    next_check_at = now + timedelta(minutes=payload.check_interval_minutes)
    with connect(settings) as connection:
        cursor = connection.execute(
            """
            INSERT INTO monitor_tasks (
                origin_city,
                destination_city,
                departure_date,
                target_price,
                check_interval_minutes,
                departure_time_filters,
                flight_attribute_filters,
                airline_filters,
                enabled,
                next_check_at,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.origin_city,
                payload.destination_city,
                payload.departure_date.isoformat(),
                payload.target_price,
                payload.check_interval_minutes,
                json.dumps(payload.departure_time_filters, ensure_ascii=False),
                json.dumps(payload.flight_attribute_filters, ensure_ascii=False),
                json.dumps(payload.airline_filters, ensure_ascii=False),
                1,
                next_check_at.isoformat(),
                now.isoformat(),
                now.isoformat(),
            ),
        )
        row = connection.execute(
            "SELECT * FROM monitor_tasks WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()

    return _row_to_monitor_task(row)


def list_monitor_tasks(settings: Settings) -> list[MonitorTask]:
    with connect(settings) as connection:
        rows = connection.execute(
            "SELECT * FROM monitor_tasks ORDER BY created_at DESC"
        ).fetchall()

    return [_row_to_monitor_task(row) for row in rows]


def get_monitor_task(settings: Settings, monitor_task_id: int) -> MonitorTask | None:
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT * FROM monitor_tasks WHERE id = ?",
            (monitor_task_id,),
        ).fetchone()

    return _row_to_monitor_task(row) if row else None


def update_monitor_task(
    settings: Settings,
    monitor_task_id: int,
    payload: MonitorTaskUpdate,
    *,
    existing_monitor: MonitorTask | None = None,
) -> MonitorTask:
    now = datetime.now(UTC)
    enabled = payload.enabled
    if enabled is None:
        enabled = existing_monitor.enabled if existing_monitor is not None else True
    next_check_at = now + timedelta(minutes=payload.check_interval_minutes)
    with connect(settings) as connection:
        connection.execute(
            """
            UPDATE monitor_tasks
            SET origin_city = ?,
                destination_city = ?,
                departure_date = ?,
                target_price = ?,
                check_interval_minutes = ?,
                departure_time_filters = ?,
                flight_attribute_filters = ?,
                airline_filters = ?,
                enabled = ?,
                next_check_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                payload.origin_city,
                payload.destination_city,
                payload.departure_date.isoformat(),
                payload.target_price,
                payload.check_interval_minutes,
                json.dumps(payload.departure_time_filters, ensure_ascii=False),
                json.dumps(payload.flight_attribute_filters, ensure_ascii=False),
                json.dumps(payload.airline_filters, ensure_ascii=False),
                int(enabled),
                next_check_at.isoformat(),
                now.isoformat(),
                monitor_task_id,
            ),
        )
        row = connection.execute(
            "SELECT * FROM monitor_tasks WHERE id = ?",
            (monitor_task_id,),
        ).fetchone()

    return _row_to_monitor_task(row)


def update_monitor_runtime_state(
    settings: Settings,
    task_id: int,
    *,
    last_checked_at: datetime | None = None,
    next_check_at: datetime | None = None,
    last_seen_lowest_price: int | None = None,
    last_notified_at: datetime | None = None,
    last_notified_price: int | None = None,
) -> MonitorTask:
    now = datetime.now(UTC)
    with connect(settings) as connection:
        connection.execute(
            """
            UPDATE monitor_tasks
            SET last_checked_at = ?,
                next_check_at = COALESCE(?, next_check_at),
                last_seen_lowest_price = ?,
                last_notified_at = ?,
                last_notified_price = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                last_checked_at.isoformat() if last_checked_at else None,
                next_check_at.isoformat() if next_check_at else None,
                last_seen_lowest_price,
                last_notified_at.isoformat() if last_notified_at else None,
                last_notified_price,
                now.isoformat(),
                task_id,
            ),
        )
        row = connection.execute(
            "SELECT * FROM monitor_tasks WHERE id = ?",
            (task_id,),
        ).fetchone()

    return _row_to_monitor_task(row)


def record_monitor_hit(
    settings: Settings,
    task_id: int,
    lowest_price: int,
    flights_snapshot: list[dict],
) -> MonitorHit:
    now = datetime.now(UTC)
    with connect(settings) as connection:
        cursor = connection.execute(
            """
            INSERT INTO monitor_hits (
                monitor_task_id,
                hit_price,
                hit_at,
                search_snapshot_json,
                lowest_price,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                lowest_price,
                now.isoformat(),
                json.dumps(flights_snapshot, ensure_ascii=False),
                lowest_price,
                now.isoformat(),
            ),
        )
        row = connection.execute(
            "SELECT * FROM monitor_hits WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()

    return _row_to_monitor_hit(row)


def list_monitor_hits(settings: Settings, monitor_task_id: int) -> list[MonitorHit]:
    with connect(settings) as connection:
        rows = connection.execute(
            "SELECT * FROM monitor_hits WHERE monitor_task_id = ? ORDER BY hit_at DESC, id DESC",
            (monitor_task_id,),
        ).fetchall()

    return [_row_to_monitor_hit(row) for row in rows]


def count_enabled_monitor_tasks(settings: Settings) -> int:
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM monitor_tasks WHERE enabled = 1"
        ).fetchone()

    return int(row["count"])


def get_latest_monitor_hit(settings: Settings) -> tuple[MonitorTask, MonitorHit] | None:
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT * FROM monitor_hits ORDER BY hit_at DESC, id DESC LIMIT 1"
        ).fetchone()

    if row is None:
        return None

    hit = _row_to_monitor_hit(row)
    task = get_monitor_task(settings, hit.monitor_task_id)
    if task is None:
        return None

    return task, hit


def _row_to_monitor_task(row: sqlite3.Row) -> MonitorTask:
    return MonitorTask(
        id=row["id"],
        origin_city=row["origin_city"],
        destination_city=row["destination_city"],
        departure_date=date.fromisoformat(row["departure_date"]),
        target_price=row["target_price"],
        check_interval_minutes=row["check_interval_minutes"],
        departure_time_filters=json.loads(row["departure_time_filters"]),
        flight_attribute_filters=json.loads(row["flight_attribute_filters"]),
        airline_filters=json.loads(row["airline_filters"]),
        enabled=bool(row["enabled"]),
        last_checked_at=(
            datetime.fromisoformat(row["last_checked_at"])
            if row["last_checked_at"]
            else None
        ),
        next_check_at=datetime.fromisoformat(row["next_check_at"]),
        last_seen_lowest_price=row["last_seen_lowest_price"],
        last_notified_at=(
            datetime.fromisoformat(row["last_notified_at"])
            if row["last_notified_at"]
            else None
        ),
        last_notified_price=row["last_notified_price"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _row_to_monitor_hit(row: sqlite3.Row) -> MonitorHit:
    return MonitorHit(
        id=row["id"],
        monitor_task_id=row["monitor_task_id"],
        hit_price=row["hit_price"],
        hit_at=datetime.fromisoformat(row["hit_at"]),
        search_snapshot_json=json.loads(row["search_snapshot_json"]),
        lowest_price=row["lowest_price"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )
