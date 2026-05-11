import re
from datetime import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from app.models import FlightResult, SearchRequest


CARD_SELECTORS = [
    "div.flight-item.domestic",
    "[data-testid*='flight']",
    "div[class*='flight-item']",
    "div[class*='flight']",
    "li[class*='flight']",
    "article",
]
FLIGHT_NO_RE = re.compile(r"\b([A-Z]{2}\d{3,4})\b")
EMBEDDED_FLIGHT_NO_RE = re.compile(r"([A-Z]{2}\d{3,4})(?=[^A-Z0-9]|$)")
TIME_RE = re.compile(r"\b(\d{2}:\d{2})\b")
PRICE_RE = re.compile(r"[¥￥]\s*(\d+)")
AIRLINE_FALLBACK_RE = re.compile(r"([一-鿿]{2,}(?:航空|航司))")
DIRECT_WORDS = ("直飞", "无中转")
STOP_WORDS = ("经停", "中转")
BASE_URL = "https://flights.ctrip.com"


def parse_search_results(
    html: str, request: SearchRequest, fallback_search_url: str
) -> list[FlightResult]:
    soup = BeautifulSoup(html, "html.parser")
    cards = _find_cards(soup)

    flights: list[FlightResult] = []
    seen: set[tuple[str, str, str, int]] = set()
    for card in cards:
        parsed = _parse_card(card, request, fallback_search_url)
        if parsed is None:
            continue
        dedupe_key = (
            parsed.flight_no,
            parsed.departure_time.isoformat(),
            parsed.arrival_time.isoformat(),
            parsed.price,
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        flights.append(parsed)

    return flights


def _find_cards(soup: BeautifulSoup) -> list[Tag]:
    for selector in CARD_SELECTORS:
        cards = [node for node in soup.select(selector) if isinstance(node, Tag)]
        if cards:
            return cards
    return []


def _parse_card(
    card: Tag, request: SearchRequest, fallback_search_url: str
) -> FlightResult | None:
    text = " ".join(card.stripped_strings)
    flight_no = _extract_flight_no(card, text)
    times = TIME_RE.findall(text)
    price = _extract_price(card, text)
    airline = _extract_airline(card, text)

    if not flight_no or len(times) < 2 or price is None or not airline:
        return None

    href = _extract_deeplink(card, fallback_search_url)
    stop_info = _extract_stop_info(card, text)
    is_direct = stop_info == "直飞"

    return FlightResult(
        flight_no=flight_no,
        airline=airline,
        origin_city=request.origin_city,
        destination_city=request.destination_city,
        departure_time=time.fromisoformat(times[0]),
        arrival_time=time.fromisoformat(times[1]),
        is_direct=is_direct,
        stop_info=stop_info,
        price=price,
        deeplink_url=href,
        fallback_search_url=fallback_search_url,
    )


def _extract_flight_no(card: Tag, text: str) -> str | None:
    match = FLIGHT_NO_RE.search(text)
    if match:
        return match.group(1)

    for attr_value in _iter_relevant_attribute_values(card):
        match = FLIGHT_NO_RE.search(attr_value) or EMBEDDED_FLIGHT_NO_RE.search(attr_value)
        if match:
            return match.group(1)
    return None


def _extract_price(card: Tag, text: str) -> int | None:
    match = PRICE_RE.search(text)
    if match:
        return int(match.group(1))

    price_node = card.select_one(".price.over-size .price, .flight-price .price")
    if price_node is None:
        return None
    digits = "".join(ch for ch in price_node.get_text(strip=True) if ch.isdigit())
    return int(digits) if digits else None


def _extract_airline(card: Tag, text: str) -> str | None:
    airline_node = card.select_one(".airline-name span, .airline-name")
    if airline_node is not None:
        airline = airline_node.get_text(strip=True)
        if airline:
            return airline

    logo = card.select_one("img.airline-logo[alt]")
    if logo is not None:
        airline = (logo.get("alt") or "").strip()
        if airline:
            return airline

    match = AIRLINE_FALLBACK_RE.search(text)
    if match:
        return match.group(1)
    return None


def _extract_stop_info(card: Tag, text: str) -> str:
    for selector in (".transfer-duration", "[id^='transfer-text-']"):
        node = card.select_one(selector)
        if node is None:
            continue
        value = node.get_text(" ", strip=True)
        if any(word in value for word in STOP_WORDS):
            return value

    for word in STOP_WORDS:
        if word in text:
            idx = text.index(word)
            snippet = text[max(0, idx - 6) : idx + 10].strip()
            return snippet or word

    if any(word in text for word in DIRECT_WORDS):
        return "直飞"

    flight_detail = card.select_one(".flight-detail")
    if flight_detail is not None:
        detail_text = flight_detail.get_text(" ", strip=True)
        if detail_text and not any(word in detail_text for word in STOP_WORDS):
            return "直飞"

    return "经停或中转"


def _extract_deeplink(card: Tag, fallback_search_url: str) -> str:
    anchor = card.find("a", href=True)
    if anchor is not None:
        href = (anchor.get("href") or "").strip()
        if href:
            return urljoin(BASE_URL, href)
    button = card.select_one("button.btn-book")
    if button is not None:
        for attr_name, attr_value in button.attrs.items():
            if isinstance(attr_value, str) and attr_value.strip().startswith("http"):
                return attr_value.strip()
    return fallback_search_url


def _iter_relevant_attribute_values(card: Tag):
    for node in card.descendants:
        if not isinstance(node, Tag):
            continue
        for attr_name, attr_value in node.attrs.items():
            if attr_name != "id":
                continue
            values = attr_value if isinstance(attr_value, list) else [attr_value]
            for value in values:
                if isinstance(value, str):
                    yield value
