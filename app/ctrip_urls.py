from urllib.parse import quote


TOKEN_VALUES = {
    "origin": "origin",
    "destination": "destination",
    "departure_date": "departure_date",
}


def build_search_url(
    template: str,
    origin: str,
    destination: str,
    departure_date: str,
) -> str:
    replacements = {
        "origin": quote(origin, safe=""),
        "destination": quote(destination, safe=""),
        "departure_date": quote(departure_date, safe=""),
    }

    url = template
    for token in TOKEN_VALUES:
        url = url.replace(f"{{{token}}}", replacements[token])

    return url
