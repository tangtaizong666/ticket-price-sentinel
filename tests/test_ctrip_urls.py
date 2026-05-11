from app.ctrip_urls import build_search_url


def test_build_search_url_replaces_tokens_and_url_quotes_values() -> None:
    template = (
        "https://flights.example.com/search?from={origin}&to={destination}&date={departure_date}"
        "&title={origin}-{destination}"
    )

    result = build_search_url(
        template=template,
        origin="北京 首都",
        destination="上海/虹桥",
        departure_date="2026-05-20",
    )

    assert result == (
        "https://flights.example.com/search?from=%E5%8C%97%E4%BA%AC%20%E9%A6%96%E9%83%BD"
        "&to=%E4%B8%8A%E6%B5%B7%2F%E8%99%B9%E6%A1%A5&date=2026-05-20"
        "&title=%E5%8C%97%E4%BA%AC%20%E9%A6%96%E9%83%BD-%E4%B8%8A%E6%B5%B7%2F%E8%99%B9%E6%A1%A5"
    )
