from datetime import time

from app.models import FlightResult, SearchRequest

TIME_WINDOWS = {
    "上午": (time(6, 0), time(11, 59, 59)),
    "下午": (time(12, 0), time(17, 59, 59)),
    "晚上": (time(18, 0), time(23, 59, 59)),
}


def apply_filters(flights: list[FlightResult], request: SearchRequest) -> list[FlightResult]:
    filtered: list[FlightResult] = []
    max_price = getattr(request, "max_price", None)

    for flight in flights:
        if max_price is not None and flight.price > max_price:
            continue
        if request.departure_time_filters and not _matches_time_window(
            flight, request.departure_time_filters
        ):
            continue
        if "直飞" in request.flight_attribute_filters and not flight.is_direct:
            continue
        if request.airline_filters and flight.airline not in request.airline_filters:
            continue
        filtered.append(flight)

    return sorted(filtered, key=lambda flight: (flight.price, flight.departure_time))


def calculate_lowest_price(flights: list[FlightResult]) -> int | None:
    if not flights:
        return None
    return min(flight.price for flight in flights)


def _matches_time_window(flight: FlightResult, labels: list[str]) -> bool:
    return any(
        start <= flight.departure_time <= end
        for label in labels
        if (window := TIME_WINDOWS.get(label)) is not None
        for start, end in [window]
    )
