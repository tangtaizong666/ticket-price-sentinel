from datetime import date
from pathlib import Path

from app.ctrip_parser import parse_search_results
from app.models import SearchRequest


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ctrip_search_results.html"


def test_parse_search_results_extracts_required_fields() -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    request = SearchRequest(
        origin_city="北京",
        destination_city="上海",
        departure_date=date(2026, 5, 20),
        max_price=800,
        departure_time_filters=[],
        flight_attribute_filters=[],
        airline_filters=[],
    )

    flights = parse_search_results(html, request, "https://example.invalid/results")

    assert len(flights) >= 6
    assert all(flight.flight_no for flight in flights)
    assert all(flight.airline for flight in flights)
    assert all(flight.origin_city == "北京" for flight in flights)
    assert all(flight.destination_city == "上海" for flight in flights)
    assert all(flight.departure_time.isoformat() for flight in flights)
    assert all(flight.arrival_time.isoformat() for flight in flights)
    assert all(flight.departure_time < flight.arrival_time for flight in flights)
    assert all(isinstance(flight.is_direct, bool) for flight in flights)
    assert all(flight.stop_info for flight in flights)
    assert all(flight.price > 0 for flight in flights)
    assert all(flight.deeplink_url for flight in flights)
    assert all(
        flight.fallback_search_url == "https://example.invalid/results"
        for flight in flights
    )

    direct_flights = [flight for flight in flights if flight.is_direct]
    connecting_flights = [flight for flight in flights if not flight.is_direct]

    assert len(direct_flights) >= 5
    assert any(flight.stop_info == "直飞" for flight in direct_flights)
    assert any("中转" in flight.stop_info for flight in connecting_flights)
    assert {flight.flight_no for flight in connecting_flights} == {"SC7604"}
