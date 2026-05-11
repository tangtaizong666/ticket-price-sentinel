from datetime import date, time

import pytest

from app.filtering import apply_filters, calculate_lowest_price
from app.models import FlightResult, SearchRequest


def test_apply_filters_combines_price_time_airline_and_direct_filters() -> None:
    request = SearchRequest(
        origin_city="北京",
        destination_city="上海",
        departure_date=date(2026, 5, 20),
        max_price=1000,
        departure_time_filters=["上午", "下午"],
        flight_attribute_filters=["直飞"],
        airline_filters=["国航"],
    )
    matching_flight = FlightResult(
        flight_no="CA1234",
        airline="国航",
        origin_city="北京",
        destination_city="上海",
        departure_time=time(9, 30),
        arrival_time=time(11, 45),
        is_direct=True,
        stop_info="直飞",
        price=980,
        deeplink_url="https://example.com/ca1234",
        fallback_search_url="https://example.com/search-ca1234",
    )
    same_price_earlier_departure = FlightResult(
        flight_no="CA2234",
        airline="国航",
        origin_city="北京",
        destination_city="上海",
        departure_time=time(8, 45),
        arrival_time=time(10, 55),
        is_direct=True,
        stop_info="直飞",
        price=980,
        deeplink_url="https://example.com/ca2234",
        fallback_search_url="https://example.com/search-ca2234",
    )
    filtered_out_by_price = FlightResult(
        flight_no="CA5678",
        airline="国航",
        origin_city="北京",
        destination_city="上海",
        departure_time=time(9, 45),
        arrival_time=time(12, 0),
        is_direct=True,
        stop_info="直飞",
        price=1200,
        deeplink_url="https://example.com/ca5678",
        fallback_search_url="https://example.com/search-ca5678",
    )
    filtered_out_by_time = FlightResult(
        flight_no="CA8888",
        airline="国航",
        origin_city="北京",
        destination_city="上海",
        departure_time=time(19, 15),
        arrival_time=time(21, 30),
        is_direct=True,
        stop_info="直飞",
        price=900,
        deeplink_url="https://example.com/ca8888",
        fallback_search_url="https://example.com/search-ca8888",
    )
    filtered_out_by_airline = FlightResult(
        flight_no="MU1234",
        airline="东航",
        origin_city="北京",
        destination_city="上海",
        departure_time=time(9, 15),
        arrival_time=time(11, 30),
        is_direct=True,
        stop_info="直飞",
        price=860,
        deeplink_url="https://example.com/mu1234",
        fallback_search_url="https://example.com/search-mu1234",
    )
    filtered_out_by_directness = FlightResult(
        flight_no="CA9999",
        airline="国航",
        origin_city="北京",
        destination_city="上海",
        departure_time=time(8, 50),
        arrival_time=time(12, 10),
        is_direct=False,
        stop_info="经停西安",
        price=700,
        deeplink_url="https://example.com/ca9999",
        fallback_search_url="https://example.com/search-ca9999",
    )

    filtered = apply_filters(
        [
            matching_flight,
            same_price_earlier_departure,
            filtered_out_by_price,
            filtered_out_by_time,
            filtered_out_by_airline,
            filtered_out_by_directness,
        ],
        request,
    )

    assert filtered == [same_price_earlier_departure, matching_flight]
    assert filtered == sorted(filtered, key=lambda flight: (flight.price, flight.departure_time))
    assert calculate_lowest_price(filtered) == 980


def test_apply_filters_checks_directness_before_airline_filter() -> None:
    request = SearchRequest(
        origin_city="北京",
        destination_city="上海",
        departure_date=date(2026, 5, 20),
        flight_attribute_filters=["直飞"],
        airline_filters=["国航"],
    )
    access_log: list[str] = []

    class FlightProbe:
        price = 800
        departure_time = time(9, 0)

        @property
        def is_direct(self) -> bool:
            access_log.append("is_direct")
            return False

        @property
        def airline(self) -> str:
            access_log.append("airline")
            return "国航"

    filtered = apply_filters([FlightProbe()], request)

    assert filtered == []
    assert access_log == ["is_direct"]


def test_search_request_validates_origin_destination_and_max_price() -> None:
    with pytest.raises(ValueError):
        SearchRequest(
            origin_city="北京",
            destination_city="北京",
            departure_date=date(2026, 5, 20),
        )

    with pytest.raises(ValueError):
        SearchRequest(
            origin_city="北京",
            destination_city="上海",
            departure_date=date(2026, 5, 20),
            max_price=0,
        )
