from typing import Protocol

from app.filtering import apply_filters, calculate_lowest_price
from app.history import save_history
from app.models import FlightResult, SearchRequest, SearchResponse
from app.settings import Settings


class Scraper(Protocol):
    async def search(self, request: SearchRequest) -> list[FlightResult]: ...


async def run_search(
    settings: Settings, scraper: Scraper, request: SearchRequest
) -> SearchResponse:
    flights = await scraper.search(request)
    filtered_flights = apply_filters(flights, request)
    history_record = save_history(settings, request)
    return SearchResponse(
        lowest_price=calculate_lowest_price(filtered_flights),
        flights=filtered_flights,
        history_id=history_record.id,
    )
