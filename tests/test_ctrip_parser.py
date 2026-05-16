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


def test_parse_search_results_ignores_discount_amount_when_extracting_price() -> None:
    html = """
    <div class="flight-item domestic">
        <div class="airline-name">龙江航空</div>
        <div>LT6689</div>
        <div>06:30 太平国际机场 T2 经停 榆林 榆阳机场 45m 11:45 江北国际机场 T3</div>
        <div>已减¥155 普通会员可享</div>
        <div class="price over-size"><span class="price">¥2325</span><span>起</span></div>
        <button class="btn-book">订票</button>
    </div>
    """
    request = SearchRequest(
        origin_city="哈尔滨",
        destination_city="重庆",
        departure_date=date(2026, 7, 11),
    )

    flights = parse_search_results(html, request, "https://example.invalid/results")

    assert len(flights) == 1
    assert flights[0].price == 2325


def test_parse_search_results_ignores_cabin_discount_when_extracting_price() -> None:
    html = """
    <div class="flight-item domestic">
        <div class="airline-name">南方航空</div>
        <div>CZ2334</div>
        <div>18:35 太平国际机场 T2 经停 青岛 00:55 江北国际机场 T3</div>
        <div class="price over-size"><span class="price">¥1290 起 经济舱5.3折</span></div>
        <button class="btn-book">订票</button>
    </div>
    """
    request = SearchRequest(
        origin_city="哈尔滨",
        destination_city="重庆",
        departure_date=date(2026, 7, 11),
    )

    flights = parse_search_results(html, request, "https://example.invalid/results")

    assert len(flights) == 1
    assert flights[0].price == 1290


def test_parse_search_results_keeps_flight_when_flight_number_is_missing() -> None:
    html = """
    <div class="flight-item domestic">
        <div class="airline-name">长龙航空</div>
        <div>12:00 太平国际机场 T2 16:15 江北国际机场 T3</div>
        <div class="price over-size"><span class="price">¥1460</span><span>起</span></div>
        <button class="btn-book">订票</button>
    </div>
    """
    request = SearchRequest(
        origin_city="哈尔滨",
        destination_city="重庆",
        departure_date=date(2026, 7, 11),
    )

    flights = parse_search_results(html, request, "https://example.invalid/results")

    assert len(flights) == 1
    assert flights[0].flight_no == "未知航班"
    assert flights[0].price == 1460
