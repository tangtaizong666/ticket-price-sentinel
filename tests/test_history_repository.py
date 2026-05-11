from datetime import UTC, date, datetime
from typing import get_type_hints

from app.db import connect, init_db
from app.history import _row_to_history, list_history, save_history, update_history
from app.models import HistoryRecord, SearchRequest
from app.settings import Settings


def test_row_to_history_converts_sqlite_text_values_before_model_construction(tmp_path, monkeypatch) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    init_db(settings)

    request = SearchRequest(
        origin_city="北京",
        destination_city="上海",
        departure_date=date(2026, 5, 20),
        max_price=None,
        departure_time_filters=["上午", "晚上"],
        flight_attribute_filters=["直飞", "红眼航班"],
        airline_filters=["国航", "东航"],
    )
    saved = save_history(settings, request)

    with connect(settings) as connection:
        row = connection.execute(
            "SELECT * FROM search_history WHERE id = ?",
            (saved.id,),
        ).fetchone()

    captured = {}

    def fake_history_record(**kwargs):
        captured.update(kwargs)
        return kwargs

    monkeypatch.setattr("app.history.HistoryRecord", fake_history_record)

    converted = _row_to_history(row)

    assert converted["departure_date"] == date(2026, 5, 20)
    assert isinstance(converted["departure_date"], date)
    assert converted["max_price"] is None
    assert converted["departure_time_filters"] == ["上午", "晚上"]
    assert converted["flight_attribute_filters"] == ["直飞", "红眼航班"]
    assert converted["airline_filters"] == ["国航", "东航"]
    assert isinstance(converted["last_searched_at"], datetime)
    assert isinstance(converted["created_at"], datetime)
    assert isinstance(converted["updated_at"], datetime)
    assert captured == converted


def test_history_repository_lists_multiple_records_newest_first(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    init_db(settings)

    older = save_history(
        settings,
        SearchRequest(
            origin_city="北京",
            destination_city="上海",
            departure_date=date(2026, 5, 20),
            max_price=800,
            departure_time_filters=["上午"],
            flight_attribute_filters=["直飞"],
            airline_filters=["国航"],
        ),
    )
    newer = save_history(
        settings,
        SearchRequest(
            origin_city="广州",
            destination_city="深圳",
            departure_date=date(2026, 5, 21),
            max_price=500,
            departure_time_filters=["下午"],
            flight_attribute_filters=["经停"],
            airline_filters=["南航"],
        ),
    )

    older_updated_at = datetime(2026, 5, 20, 10, 0, tzinfo=UTC).isoformat()
    newer_updated_at = datetime(2026, 5, 20, 12, 0, tzinfo=UTC).isoformat()
    with connect(settings) as connection:
        connection.execute(
            "UPDATE search_history SET updated_at = ? WHERE id = ?",
            (older_updated_at, older.id),
        )
        connection.execute(
            "UPDATE search_history SET updated_at = ? WHERE id = ?",
            (newer_updated_at, newer.id),
        )

    rows = list_history(settings)

    assert [row.id for row in rows] == [newer.id, older.id]
    assert rows[0].updated_at == datetime.fromisoformat(newer_updated_at)
    assert rows[1].updated_at == datetime.fromisoformat(older_updated_at)


def test_update_history_returns_history_record_and_none_lookup_stays_at_route_layer(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    init_db(settings)

    saved = save_history(
        settings,
        SearchRequest(
            origin_city="北京",
            destination_city="上海",
            departure_date=date(2026, 5, 20),
            max_price=600,
            departure_time_filters=["上午"],
            flight_attribute_filters=["直飞"],
            airline_filters=["东航"],
        ),
    )

    type_hints = get_type_hints(update_history)
    assert type_hints["return"] is HistoryRecord

    updated = update_history(
        settings,
        saved.id,
        SearchRequest(
            origin_city="北京",
            destination_city="广州",
            departure_date=date(2026, 5, 22),
            max_price=700,
            departure_time_filters=["上午"],
            flight_attribute_filters=["直飞"],
            airline_filters=["东航"],
        ),
    )

    assert isinstance(updated, HistoryRecord)
    assert updated.id == saved.id
    assert updated.destination_city == "广州"
