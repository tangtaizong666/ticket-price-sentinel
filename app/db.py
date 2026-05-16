import sqlite3

from app.settings import Settings


def connect(settings: Settings) -> sqlite3.Connection:
    settings.app_db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.app_db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db(settings: Settings) -> None:
    with connect(settings) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                origin_city TEXT NOT NULL,
                destination_city TEXT NOT NULL,
                departure_date TEXT NOT NULL,
                max_price INTEGER,
                departure_time_filters TEXT NOT NULL,
                flight_attribute_filters TEXT NOT NULL,
                airline_filters TEXT NOT NULL,
                last_searched_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS session_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                session_status TEXT NOT NULL,
                last_successful_scrape_at TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS monitor_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                origin_city TEXT NOT NULL,
                destination_city TEXT NOT NULL,
                departure_date TEXT NOT NULL,
                target_price INTEGER NOT NULL,
                check_interval_minutes INTEGER NOT NULL,
                departure_time_filters TEXT NOT NULL,
                flight_attribute_filters TEXT NOT NULL,
                airline_filters TEXT NOT NULL,
                reminder_policy TEXT NOT NULL DEFAULT 'interval',
                unchanged_reminder_interval_minutes INTEGER NOT NULL DEFAULT 360,
                alert_sound_enabled INTEGER NOT NULL DEFAULT 1,
                alert_taskbar_enabled INTEGER NOT NULL DEFAULT 1,
                alert_popup_enabled INTEGER NOT NULL DEFAULT 1,
                enabled INTEGER NOT NULL,
                last_checked_at TEXT,
                next_check_at TEXT NOT NULL,
                last_seen_lowest_price INTEGER,
                last_notified_at TEXT,
                last_notified_price INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS monitor_hits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                monitor_task_id INTEGER NOT NULL,
                hit_price INTEGER NOT NULL,
                hit_at TEXT NOT NULL,
                search_snapshot_json TEXT NOT NULL,
                lowest_price INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (monitor_task_id) REFERENCES monitor_tasks(id)
            );

            CREATE TABLE IF NOT EXISTS monitor_check_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                monitor_task_id INTEGER NOT NULL,
                checked_at TEXT NOT NULL,
                status TEXT NOT NULL,
                lowest_price INTEGER,
                is_target_hit INTEGER NOT NULL,
                notification_sent INTEGER NOT NULL,
                error_message TEXT,
                search_snapshot_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (monitor_task_id) REFERENCES monitor_tasks(id)
            );
            """
        )
        _ensure_column(
            connection,
            "monitor_tasks",
            "reminder_policy",
            "TEXT NOT NULL DEFAULT 'interval'",
        )
        _ensure_column(
            connection,
            "monitor_tasks",
            "unchanged_reminder_interval_minutes",
            "INTEGER NOT NULL DEFAULT 360",
        )
        _ensure_column(
            connection,
            "monitor_tasks",
            "alert_sound_enabled",
            "INTEGER NOT NULL DEFAULT 1",
        )
        _ensure_column(
            connection,
            "monitor_tasks",
            "alert_taskbar_enabled",
            "INTEGER NOT NULL DEFAULT 1",
        )
        _ensure_column(
            connection,
            "monitor_tasks",
            "alert_popup_enabled",
            "INTEGER NOT NULL DEFAULT 1",
        )


def _ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )
