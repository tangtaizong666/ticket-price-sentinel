from urllib.parse import quote


TOKEN_VALUES = {
    "origin": "origin",
    "destination": "destination",
    "departure_date": "departure_date",
}
CTRIP_CITY_CODES = {
    "上海": "sha",
    "北京": "bjs",
    "成都": "ctu",
    "广州": "can",
    "深圳": "szx",
    "昆明": "kmg",
    "重庆": "ckg",
    "杭州": "hgh",
    "西安": "sia",
    "乌鲁木齐": "urc",
    "三亚": "syx",
    "长沙": "csx",
    "青岛": "tao",
    "南京": "nkg",
    "沈阳": "she",
    "厦门": "xmn",
    "海口": "hak",
    "哈尔滨": "hrb",
    "武汉": "wuh",
    "郑州": "cgo",
}


def build_search_url(
    template: str,
    origin: str,
    destination: str,
    departure_date: str,
) -> str:
    normalized_origin = _normalize_city_for_ctrip_url(origin)
    normalized_destination = _normalize_city_for_ctrip_url(destination)
    replacements = {
        "origin": quote(normalized_origin, safe=""),
        "destination": quote(normalized_destination, safe=""),
        "departure_date": quote(departure_date, safe=""),
    }

    url = template
    for token in TOKEN_VALUES:
        url = url.replace(f"{{{token}}}", replacements[token])

    return url


def _normalize_city_for_ctrip_url(value: str) -> str:
    stripped = value.strip()
    return CTRIP_CITY_CODES.get(stripped, stripped)
