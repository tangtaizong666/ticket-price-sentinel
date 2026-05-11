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
            """
        )
