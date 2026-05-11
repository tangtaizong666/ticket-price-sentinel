# Flight Comparison MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local web app that searches domestic one-way Ctrip flights for a fixed date, filters results, shows the current lowest price, preserves search history, and lets the user jump back to the matching Ctrip page.

**Architecture:** Use a single FastAPI app with server-rendered HTML, a small amount of browser-side JavaScript for the collapsible filter/tag UI, SQLite for persistent history/session state, and Playwright with a persistent Chromium profile for Ctrip access. Because Ctrip is an external site that can change without warning, the plan captures a real HTML fixture first and then implements the parser against that fixture before wiring the live scraper into the search flow.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, SQLite (`sqlite3`), Playwright, BeautifulSoup 4, pytest, httpx/TestClient, python-dotenv

---

## Planned File Structure

- Create: `.gitignore` — ignore local Python, SQLite, Playwright, and snapshot artifacts
- Create: `requirements.txt` — runtime dependencies
- Create: `requirements-dev.txt` — test-only dependencies
- Create: `.env.example` — local environment variable names only
- Create: `app/__init__.py` — Python package marker
- Create: `app/settings.py` — load local settings and filesystem paths
- Create: `app/models.py` — Pydantic request/response models and shared types
- Create: `app/db.py` — SQLite connection helpers and schema setup
- Create: `app/history.py` — CRUD for search history and browser session state
- Create: `app/filtering.py` — pure filtering/lowest-price logic
- Create: `app/search_service.py` — orchestrate scraper → filter → persist → response
- Create: `app/ctrip_urls.py` — build configured Ctrip search/result URLs from tokens
- Create: `app/ctrip_session.py` — persistent Playwright profile + relogin helpers
- Create: `app/ctrip_capture.py` — save live HTML snapshots for deterministic parser work
- Create: `app/ctrip_parser.py` — normalize captured Ctrip HTML into `FlightResult` objects
- Create: `app/ctrip_scraper.py` — live Playwright scraper using the persistent profile
- Create: `app/main.py` — FastAPI app factory, routes, exception mapping, template wiring
- Create: `app/templates/index.html` — search form, collapsible filters, results, history UI
- Create: `app/static/app.css` — minimal styles for layout, filters, cards, and history rows
- Create: `app/static/app.js` — expand/collapse filters, selected-tag syncing, fetch calls, rerun/edit actions
- Create: `scripts/capture_ctrip_snapshot.py` — manual helper to save a real logged-in Ctrip results page as a fixture
- Create: `tests/test_home_page.py` — homepage shell and static markup checks
- Create: `tests/test_history_repository.py` — SQLite history/session CRUD checks
- Create: `tests/test_filtering.py` — price/time/direct/airline filter checks
- Create: `tests/test_search_api.py` — `/api/search` integration checks using a fake scraper
- Create: `tests/test_history_api.py` — history list/detail/update/rerun checks
- Create: `tests/test_session_api.py` — relogin/session endpoint checks with a stub session manager
- Create: `tests/test_ctrip_urls.py` — tokenized search URL builder checks
- Create: `tests/test_ctrip_parser.py` — parser checks using a captured HTML fixture
- Create: `tests/fixtures/.gitkeep` — keep the fixture directory in git before a real snapshot exists
- Create: `data/.gitkeep` — keep the runtime data directory in git without committing live DB/profile files

## Execution Notes

1. The directory is not currently a git repository, so the first task initializes git before frequent commits.
2. The live scraper depends on two local environment variables populated from a real Ctrip session:
   - `CTRIP_SEARCH_URL_TEMPLATE`
   - `CTRIP_SESSION_URL`
3. The parser task is intentionally blocked on a real fixture capture. Do not skip the fixture step and guess selectors.
4. Keep the runtime SQLite database at `data/app.db` and the Playwright profile at `data/playwright-profile/`.

---

### Task 1: Initialize the repository and Python environment

**Files:**
- Create: `.gitignore`
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `.env.example`
- Create: `app/__init__.py`
- Create: `data/.gitkeep`
- Create: `tests/fixtures/.gitkeep`

- [ ] **Step 1: Initialize git and create the virtual environment**

Run:
```bash
git init && python3 -m venv .venv
```

Expected: `Initialized empty Git repository` and a new `.venv/` directory.

- [ ] **Step 2: Create the ignore file and dependency manifests**

```gitignore
# .gitignore
.venv/
__pycache__/
.pytest_cache/
.env
*.pyc
*.pyo
*.db
*.sqlite3
/data/playwright-profile/
/data/*.html
/tests/fixtures/ctrip_search_results.html
/tests/fixtures/last_live_search.html
```

```text
# requirements.txt
fastapi==0.115.6
uvicorn[standard]==0.34.0
jinja2==3.1.5
python-multipart==0.0.20
pydantic==2.10.6
playwright==1.51.0
python-dotenv==1.0.1
beautifulsoup4==4.12.3
```

```text
# requirements-dev.txt
pytest==8.3.5
httpx==0.28.1
```

```dotenv
# .env.example
APP_DB_PATH=data/app.db
PLAYWRIGHT_PROFILE_DIR=data/playwright-profile
CTRIP_SNAPSHOT_DIR=tests/fixtures
CTRIP_SEARCH_URL_TEMPLATE=
CTRIP_SESSION_URL=
```

- [ ] **Step 3: Install dependencies and Chromium**

Run:
```bash
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt && .venv/bin/playwright install chromium
```

Expected: pip finishes successfully and Playwright reports that Chromium was installed.

- [ ] **Step 4: Create package marker and keep directories**

```python
# app/__init__.py
```

Run:
```bash
mkdir -p app data tests/fixtures && touch data/.gitkeep tests/fixtures/.gitkeep
```

Expected: `app/`, `data/`, and `tests/fixtures/` exist.

- [ ] **Step 5: Commit the bootstrap**

Run:
```bash
git add .gitignore requirements.txt requirements-dev.txt .env.example app/__init__.py data/.gitkeep tests/fixtures/.gitkeep && git commit -m "chore: bootstrap flight comparison project"
```

Expected: a commit containing only setup files.

---

### Task 2: Render the homepage shell

**Files:**
- Create: `app/settings.py`
- Create: `app/main.py`
- Create: `app/templates/index.html`
- Test: `tests/test_home_page.py`

- [ ] **Step 1: Write the failing homepage test**

```python
# tests/test_home_page.py
from fastapi.testclient import TestClient

from app.main import create_app


def test_home_page_renders_search_shell() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert 'id="search-form"' in response.text
    assert 'data-filter-group="departure_time_filters"' in response.text
    assert 'id="selected-tags"' in response.text
    assert 'id="results-list"' in response.text
    assert 'id="history-list"' in response.text
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
.venv/bin/python -m pytest tests/test_home_page.py::test_home_page_renders_search_shell -v
```

Expected: FAIL with `ModuleNotFoundError` or `ImportError` because `app.main` does not exist yet.

- [ ] **Step 3: Add minimal settings, app factory, and template**

```python
# app/settings.py
from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_db_path: Path = Path(os.getenv("APP_DB_PATH", "data/app.db"))
    playwright_profile_dir: Path = Path(os.getenv("PLAYWRIGHT_PROFILE_DIR", "data/playwright-profile"))
    ctrip_snapshot_dir: Path = Path(os.getenv("CTRIP_SNAPSHOT_DIR", "tests/fixtures"))
    ctrip_search_url_template: str = os.getenv("CTRIP_SEARCH_URL_TEMPLATE", "")
    ctrip_session_url: str = os.getenv("CTRIP_SESSION_URL", "")
```

```python
# app/main.py
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.settings import Settings

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Fly Ticket")
    app.state.settings = settings or Settings()

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(
            request=request,
            name="index.html",
            context={"history": []},
        )

    return app


app = create_app()
```

```html
<!-- app/templates/index.html -->
<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <title>Fly Ticket</title>
  </head>
  <body>
    <main>
      <form id="search-form">
        <input name="origin_city" />
        <input name="destination_city" />
        <input name="departure_date" />
        <input name="max_price" />
        <section data-filter-group="departure_time_filters"></section>
        <section data-filter-group="flight_attribute_filters"></section>
        <section data-filter-group="airline_filters"></section>
        <div id="selected-tags"></div>
        <button type="submit">开始搜索</button>
      </form>
      <section id="results-list"></section>
      <section id="history-list"></section>
    </main>
  </body>
</html>
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
.venv/bin/python -m pytest tests/test_home_page.py::test_home_page_renders_search_shell -v
```

Expected: PASS.

- [ ] **Step 5: Commit the homepage shell**

Run:
```bash
git add app/settings.py app/main.py app/templates/index.html tests/test_home_page.py && git commit -m "feat: render flight search homepage shell"
```

Expected: a commit containing the minimal web shell.

---

### Task 3: Add SQLite schema setup and history persistence

**Files:**
- Create: `app/models.py`
- Create: `app/db.py`
- Create: `app/history.py`
- Test: `tests/test_history_repository.py`

- [ ] **Step 1: Write the failing repository test**

```python
# tests/test_history_repository.py
from datetime import date

from app.db import init_db
from app.history import list_history, save_history
from app.models import SearchRequest
from app.settings import Settings


def test_history_repository_round_trips_search_records(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    init_db(settings)

    record = save_history(
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

    rows = list_history(settings)

    assert record.id == 1
    assert len(rows) == 1
    assert rows[0].origin_city == "北京"
    assert rows[0].airline_filters == ["国航"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
.venv/bin/python -m pytest tests/test_history_repository.py::test_history_repository_round_trips_search_records -v
```

Expected: FAIL because `app.db`, `app.history`, and `app.models` do not exist.

- [ ] **Step 3: Implement the models, DB initializer, and repository**

```python
# app/models.py
from datetime import date, datetime

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    origin_city: str
    destination_city: str
    departure_date: date
    max_price: int | None = None
    departure_time_filters: list[str] = Field(default_factory=list)
    flight_attribute_filters: list[str] = Field(default_factory=list)
    airline_filters: list[str] = Field(default_factory=list)


class HistoryRecord(SearchRequest):
    id: int
    last_searched_at: datetime
    created_at: datetime
    updated_at: datetime


class SessionState(BaseModel):
    id: int = 1
    session_status: str
    last_successful_scrape_at: datetime | None = None
    updated_at: datetime
```

```python
# app/db.py
from pathlib import Path
import sqlite3

from app.settings import Settings


def connect(settings: Settings) -> sqlite3.Connection:
    settings.app_db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.app_db_path)
    connection.row_factory = sqlite3.Row
    return connection


def init_db(settings: Settings) -> None:
    with connect(settings) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                origin_city TEXT NOT NULL,
                destination_city TEXT NOT NULL,
                departure_date TEXT NOT NULL,
                max_price INTEGER,
                departure_time_filters TEXT NOT NULL,
                flight_attribute_filters TEXT NOT NULL,
                airline_filters TEXT NOT NULL,
                last_searched_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS session_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                session_status TEXT NOT NULL,
                last_successful_scrape_at TEXT,
                updated_at TEXT NOT NULL
            );
            """
        )
```

```python
# app/history.py
from datetime import datetime
import json

from app.db import connect
from app.models import HistoryRecord, SearchRequest, SessionState
from app.settings import Settings


def save_history(settings: Settings, request: SearchRequest) -> HistoryRecord:
    now = datetime.utcnow().isoformat()
    payload = (
        request.origin_city,
        request.destination_city,
        request.departure_date.isoformat(),
        request.max_price,
        json.dumps(request.departure_time_filters, ensure_ascii=False),
        json.dumps(request.flight_attribute_filters, ensure_ascii=False),
        json.dumps(request.airline_filters, ensure_ascii=False),
        now,
        now,
        now,
    )
    with connect(settings) as connection:
        cursor = connection.execute(
            """
            INSERT INTO search_history (
                origin_city, destination_city, departure_date, max_price,
                departure_time_filters, flight_attribute_filters, airline_filters,
                last_searched_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            payload,
        )
        row = connection.execute("SELECT * FROM search_history WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _row_to_history(row)


def list_history(settings: Settings) -> list[HistoryRecord]:
    with connect(settings) as connection:
        rows = connection.execute(
            "SELECT * FROM search_history ORDER BY updated_at DESC"
        ).fetchall()
    return [_row_to_history(row) for row in rows]


def _row_to_history(row) -> HistoryRecord:
    return HistoryRecord(
        id=row["id"],
        origin_city=row["origin_city"],
        destination_city=row["destination_city"],
        departure_date=row["departure_date"],
        max_price=row["max_price"],
        departure_time_filters=json.loads(row["departure_time_filters"]),
        flight_attribute_filters=json.loads(row["flight_attribute_filters"]),
        airline_filters=json.loads(row["airline_filters"]),
        last_searched_at=row["last_searched_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
```

- [ ] **Step 4: Run the repository test to verify it passes**

Run:
```bash
.venv/bin/python -m pytest tests/test_history_repository.py::test_history_repository_round_trips_search_records -v
```

Expected: PASS.

- [ ] **Step 5: Commit the persistence layer**

Run:
```bash
git add app/models.py app/db.py app/history.py tests/test_history_repository.py && git commit -m "feat: persist search history in sqlite"
```

Expected: a commit containing the base persistence layer.

---

### Task 4: Add request validation and pure flight filtering

**Files:**
- Modify: `app/models.py`
- Create: `app/filtering.py`
- Test: `tests/test_filtering.py`

- [ ] **Step 1: Write the failing validation/filter test**

```python
# tests/test_filtering.py
from datetime import date, time

import pytest

from app.filtering import apply_filters, calculate_lowest_price
from app.models import FlightResult, SearchRequest


def test_apply_filters_respects_price_time_and_airline_rules() -> None:
    request = SearchRequest(
        origin_city="北京",
        destination_city="上海",
        departure_date=date(2026, 5, 20),
        max_price=800,
        departure_time_filters=["上午"],
        flight_attribute_filters=["直飞"],
        airline_filters=["国航"],
    )
    flights = [
        FlightResult(
            flight_no="CA1883",
            airline="国航",
            origin_city="北京",
            destination_city="上海",
            departure_time=time(9, 10),
            arrival_time=time(11, 30),
            is_direct=True,
            stop_info="直飞",
            price=560,
            deeplink_url="https://example.invalid/ca1883",
            fallback_search_url="https://example.invalid/results",
        ),
        FlightResult(
            flight_no="MU5101",
            airline="东航",
            origin_city="北京",
            destination_city="上海",
            departure_time=time(14, 0),
            arrival_time=time(16, 0),
            is_direct=True,
            stop_info="直飞",
            price=620,
            deeplink_url="https://example.invalid/mu5101",
            fallback_search_url="https://example.invalid/results",
        ),
    ]

    filtered = apply_filters(flights, request)

    assert [flight.flight_no for flight in filtered] == ["CA1883"]
    assert calculate_lowest_price(filtered) == 560


def test_search_request_rejects_same_origin_and_destination() -> None:
    with pytest.raises(ValueError):
        SearchRequest(
            origin_city="北京",
            destination_city="北京",
            departure_date=date(2026, 5, 20),
        )
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
.venv/bin/python -m pytest tests/test_filtering.py -v
```

Expected: FAIL because `FlightResult`, validators, and `app.filtering` do not exist yet.

- [ ] **Step 3: Implement the result model and filtering helpers**

```python
# app/models.py
from datetime import date, datetime, time

from pydantic import BaseModel, Field, model_validator


class SearchRequest(BaseModel):
    origin_city: str
    destination_city: str
    departure_date: date
    max_price: int | None = None
    departure_time_filters: list[str] = Field(default_factory=list)
    flight_attribute_filters: list[str] = Field(default_factory=list)
    airline_filters: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_route(self):
        if self.origin_city == self.destination_city:
            raise ValueError("origin and destination must be different")
        if self.max_price is not None and self.max_price <= 0:
            raise ValueError("max_price must be positive")
        return self


class FlightResult(BaseModel):
    flight_no: str
    airline: str
    origin_city: str
    destination_city: str
    departure_time: time
    arrival_time: time
    is_direct: bool
    stop_info: str
    price: int
    deeplink_url: str
    fallback_search_url: str


class SearchResponse(BaseModel):
    lowest_price: int | None
    flights: list[FlightResult]
    history_id: int
```

```python
# app/filtering.py
from datetime import time

from app.models import FlightResult, SearchRequest

TIME_WINDOWS = {
    "上午": (time(6, 0), time(11, 59)),
    "下午": (time(12, 0), time(17, 59)),
    "晚上": (time(18, 0), time(23, 59)),
}


def apply_filters(flights: list[FlightResult], request: SearchRequest) -> list[FlightResult]:
    filtered = flights
    if request.max_price is not None:
        filtered = [flight for flight in filtered if flight.price <= request.max_price]
    if request.departure_time_filters:
        filtered = [flight for flight in filtered if _matches_time_window(flight, request.departure_time_filters)]
    if "直飞" in request.flight_attribute_filters:
        filtered = [flight for flight in filtered if flight.is_direct]
    if request.airline_filters:
        filtered = [flight for flight in filtered if flight.airline in request.airline_filters]
    return sorted(filtered, key=lambda flight: (flight.price, flight.departure_time))


def calculate_lowest_price(flights: list[FlightResult]) -> int | None:
    return min((flight.price for flight in flights), default=None)


def _matches_time_window(flight: FlightResult, labels: list[str]) -> bool:
    for label in labels:
        start, end = TIME_WINDOWS[label]
        if start <= flight.departure_time <= end:
            return True
    return False
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
.venv/bin/python -m pytest tests/test_filtering.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit the pure domain logic**

Run:
```bash
git add app/models.py app/filtering.py tests/test_filtering.py && git commit -m "feat: add flight request validation and filtering"
```

Expected: a commit containing the pure filtering logic.

---

### Task 5: Add `/api/search` with a fake scraper and history persistence

**Files:**
- Create: `app/search_service.py`
- Modify: `app/main.py`
- Test: `tests/test_search_api.py`

- [ ] **Step 1: Write the failing search API test**

```python
# tests/test_search_api.py
from datetime import time

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import FlightResult
from app.settings import Settings


class FakeScraper:
    async def search(self, request):
        return [
            FlightResult(
                flight_no="CA1883",
                airline="国航",
                origin_city=request.origin_city,
                destination_city=request.destination_city,
                departure_time=time(9, 10),
                arrival_time=time(11, 30),
                is_direct=True,
                stop_info="直飞",
                price=560,
                deeplink_url="https://example.invalid/ca1883",
                fallback_search_url="https://example.invalid/results",
            ),
            FlightResult(
                flight_no="MU5101",
                airline="东航",
                origin_city=request.origin_city,
                destination_city=request.destination_city,
                departure_time=time(14, 0),
                arrival_time=time(16, 0),
                is_direct=True,
                stop_info="直飞",
                price=920,
                deeplink_url="https://example.invalid/mu5101",
                fallback_search_url="https://example.invalid/results",
            ),
        ]


def test_search_endpoint_returns_filtered_results_and_saves_history(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    app = create_app(settings=settings, scraper=FakeScraper())
    client = TestClient(app)

    payload = {
        "origin_city": "北京",
        "destination_city": "上海",
        "departure_date": "2026-05-20",
        "max_price": 800,
        "departure_time_filters": ["上午"],
        "flight_attribute_filters": ["直飞"],
        "airline_filters": ["国航"],
    }

    response = client.post("/api/search", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["lowest_price"] == 560
    assert [flight["flight_no"] for flight in body["flights"]] == ["CA1883"]

    history = client.get("/api/history")
    assert history.status_code == 200
    assert history.json()[0]["origin_city"] == "北京"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
.venv/bin/python -m pytest tests/test_search_api.py::test_search_endpoint_returns_filtered_results_and_saves_history -v
```

Expected: FAIL because `/api/search` and `/api/history` do not exist yet.

- [ ] **Step 3: Implement the search service and API routes**

```python
# app/search_service.py
from typing import Protocol

from app.filtering import apply_filters, calculate_lowest_price
from app.history import save_history
from app.models import SearchRequest, SearchResponse
from app.settings import Settings


class Scraper(Protocol):
    async def search(self, request: SearchRequest): ...


async def run_search(settings: Settings, scraper: Scraper, request: SearchRequest) -> SearchResponse:
    flights = await scraper.search(request)
    filtered = apply_filters(flights, request)
    history = save_history(settings, request)
    return SearchResponse(
        lowest_price=calculate_lowest_price(filtered),
        flights=filtered,
        history_id=history.id,
    )
```

```python
# app/main.py
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.db import init_db
from app.history import list_history
from app.models import SearchRequest
from app.search_service import run_search
from app.settings import Settings

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))


class EmptyScraper:
    async def search(self, request: SearchRequest):
        return []


def create_app(settings: Settings | None = None, scraper=None, session_manager=None) -> FastAPI:
    app = FastAPI(title="Fly Ticket")
    app.state.settings = settings or Settings()
    app.state.scraper = scraper or EmptyScraper()
    app.state.session_manager = session_manager
    init_db(app.state.settings)
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(
            request=request,
            name="index.html",
            context={"history": list_history(app.state.settings)},
        )

    @app.get("/api/history")
    async def history_index():
        return list_history(app.state.settings)

    @app.post("/api/search")
    async def search(payload: SearchRequest):
        return await run_search(app.state.settings, app.state.scraper, payload)

    return app


app = create_app()
```

Run:
```bash
mkdir -p app/static && touch app/static/app.css app/static/app.js
```

Expected: the app now has the basic API surface and static directory.

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
.venv/bin/python -m pytest tests/test_search_api.py::test_search_endpoint_returns_filtered_results_and_saves_history -v
```

Expected: PASS.

- [ ] **Step 5: Commit the basic search flow**

Run:
```bash
git add app/main.py app/search_service.py app/static/app.css app/static/app.js tests/test_search_api.py && git commit -m "feat: add search api with history persistence"
```

Expected: a commit containing the first working end-to-end flow with a fake scraper.

---

### Task 6: Build the collapsible filter UI and client-side rendering

**Files:**
- Modify: `app/templates/index.html`
- Modify: `app/static/app.css`
- Modify: `app/static/app.js`
- Test: `tests/test_home_page.py`

- [ ] **Step 1: Extend the failing homepage test for the final shell markup**

```python
# tests/test_home_page.py
from fastapi.testclient import TestClient

from app.main import create_app


def test_home_page_renders_search_shell() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert 'data-filter-toggle="departure_time_filters"' in response.text
    assert 'data-filter-toggle="flight_attribute_filters"' in response.text
    assert 'data-filter-toggle="airline_filters"' in response.text
    assert 'id="selected-tags"' in response.text
    assert 'id="search-summary"' in response.text
    assert 'data-history-action="rerun"' in response.text
    assert 'data-history-action="edit"' in response.text
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
.venv/bin/python -m pytest tests/test_home_page.py::test_home_page_renders_search_shell -v
```

Expected: FAIL because the richer markup has not been added yet.

- [ ] **Step 3: Implement the template, CSS, and JavaScript**

```html
<!-- app/templates/index.html -->
<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <title>Fly Ticket</title>
    <link rel="stylesheet" href="{{ url_for('static', path='app.css') }}" />
  </head>
  <body>
    <main class="layout">
      <section class="panel search-panel">
        <h1>机票比价</h1>
        <form id="search-form">
          <label>出发地<input name="origin_city" required /></label>
          <label>到达地<input name="destination_city" required /></label>
          <label>出发日期<input type="date" name="departure_date" required /></label>
          <label>最高价格<input type="number" name="max_price" min="1" /></label>

          <div class="filter-block">
            <button type="button" data-filter-toggle="departure_time_filters">起飞时间</button>
            <div class="filter-options" data-filter-group="departure_time_filters" hidden>
              <button type="button" data-filter-value="上午">上午</button>
              <button type="button" data-filter-value="下午">下午</button>
              <button type="button" data-filter-value="晚上">晚上</button>
            </div>
          </div>

          <div class="filter-block">
            <button type="button" data-filter-toggle="flight_attribute_filters">航班属性</button>
            <div class="filter-options" data-filter-group="flight_attribute_filters" hidden>
              <button type="button" data-filter-value="直飞">直飞</button>
              <button type="button" data-filter-value="经停">经停</button>
            </div>
          </div>

          <div class="filter-block">
            <button type="button" data-filter-toggle="airline_filters">航空公司</button>
            <div class="filter-options" data-filter-group="airline_filters" hidden>
              <button type="button" data-filter-value="国航">国航</button>
              <button type="button" data-filter-value="东航">东航</button>
              <button type="button" data-filter-value="春秋">春秋</button>
            </div>
          </div>

          <div id="selected-tags"></div>
          <div class="actions">
            <button type="submit">开始搜索</button>
            <button type="button" id="clear-filters">清空筛选</button>
          </div>
        </form>
      </section>

      <section class="panel results-panel">
        <div id="search-summary"></div>
        <div id="results-list"></div>
      </section>

      <section class="panel history-panel">
        <h2>历史搜索</h2>
        <div id="history-list">
          {% for record in history %}
          <article class="history-row" data-history-id="{{ record.id }}">
            <div>{{ record.origin_city }} → {{ record.destination_city }}</div>
            <div>{{ record.departure_date }}</div>
            <button type="button" data-history-action="rerun">重新搜索</button>
            <button type="button" data-history-action="edit">编辑</button>
          </article>
          {% endfor %}
        </div>
      </section>
    </main>
    <script src="{{ url_for('static', path='app.js') }}"></script>
  </body>
</html>
```

```css
/* app/static/app.css */
body { font-family: sans-serif; margin: 0; background: #f7f8fb; }
.layout { display: grid; grid-template-columns: 340px 1fr; gap: 16px; padding: 16px; }
.panel { background: #ffffff; border-radius: 12px; padding: 16px; box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06); }
.history-panel { grid-column: 1 / -1; }
.filter-options { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.filter-options button, #selected-tags button { border: 1px solid #d1d5db; border-radius: 999px; background: #fff; padding: 6px 12px; }
#selected-tags { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }
.result-card, .history-row { border: 1px solid #e5e7eb; border-radius: 10px; padding: 12px; margin-top: 12px; }
.actions { display: flex; gap: 8px; }
```

```javascript
// app/static/app.js
const activeFilters = {
  departure_time_filters: new Set(),
  flight_attribute_filters: new Set(),
  airline_filters: new Set(),
};

function renderSelectedTags() {
  const container = document.getElementById("selected-tags");
  container.innerHTML = "";
  Object.entries(activeFilters).forEach(([group, values]) => {
    values.forEach((value) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `${value} ×`;
      button.addEventListener("click", () => {
        values.delete(value);
        renderSelectedTags();
      });
      container.appendChild(button);
    });
  });
}

document.querySelectorAll("[data-filter-toggle]").forEach((button) => {
  button.addEventListener("click", () => {
    const group = document.querySelector(`[data-filter-group='${button.dataset.filterToggle}']`);
    group.hidden = !group.hidden;
  });
});

document.querySelectorAll(".filter-options [data-filter-value]").forEach((button) => {
  button.addEventListener("click", () => {
    const groupName = button.closest(".filter-options").dataset.filterGroup;
    const value = button.dataset.filterValue;
    if (activeFilters[groupName].has(value)) {
      activeFilters[groupName].delete(value);
    } else {
      activeFilters[groupName].add(value);
    }
    renderSelectedTags();
  });
});

document.getElementById("clear-filters").addEventListener("click", () => {
  Object.values(activeFilters).forEach((values) => values.clear());
  renderSelectedTags();
});
```

- [ ] **Step 4: Run the homepage test and a manual browser check**

Run:
```bash
.venv/bin/python -m pytest tests/test_home_page.py::test_home_page_renders_search_shell -v && .venv/bin/python -m uvicorn app.main:app --reload
```

Expected: the pytest check passes, then the app starts at `http://127.0.0.1:8000` and the browser UI shows collapsible filter groups with selected tags.

- [ ] **Step 5: Commit the web UI**

Run:
```bash
git add app/templates/index.html app/static/app.css app/static/app.js tests/test_home_page.py && git commit -m "feat: add collapsible filter ui"
```

Expected: a commit containing the MVP frontend shell.

---

### Task 7: Add history detail, update, and rerun endpoints

**Files:**
- Modify: `app/history.py`
- Modify: `app/main.py`
- Test: `tests/test_history_api.py`

- [ ] **Step 1: Write the failing history API test**

```python
# tests/test_history_api.py
from datetime import time

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import FlightResult
from app.settings import Settings


class FakeScraper:
    async def search(self, request):
        return [
            FlightResult(
                flight_no="CA1883",
                airline="国航",
                origin_city=request.origin_city,
                destination_city=request.destination_city,
                departure_time=time(9, 10),
                arrival_time=time(11, 30),
                is_direct=True,
                stop_info="直飞",
                price=560,
                deeplink_url="https://example.invalid/ca1883",
                fallback_search_url="https://example.invalid/results",
            )
        ]


def test_history_detail_update_and_rerun_flow(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    client = TestClient(create_app(settings=settings, scraper=FakeScraper()))

    created = client.post(
        "/api/search",
        json={
            "origin_city": "北京",
            "destination_city": "上海",
            "departure_date": "2026-05-20",
            "max_price": 800,
            "departure_time_filters": ["上午"],
            "flight_attribute_filters": ["直飞"],
            "airline_filters": ["国航"],
        },
    ).json()

    history_id = created["history_id"]
    detail = client.get(f"/api/history/{history_id}")
    assert detail.status_code == 200
    assert detail.json()["origin_city"] == "北京"

    updated = client.put(
        f"/api/history/{history_id}",
        json={
            "origin_city": "北京",
            "destination_city": "上海",
            "departure_date": "2026-05-20",
            "max_price": 700,
            "departure_time_filters": ["上午"],
            "flight_attribute_filters": ["直飞"],
            "airline_filters": ["国航"],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["max_price"] == 700

    rerun = client.post(f"/api/history/{history_id}/rerun")
    assert rerun.status_code == 200
    assert rerun.json()["lowest_price"] == 560
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
.venv/bin/python -m pytest tests/test_history_api.py::test_history_detail_update_and_rerun_flow -v
```

Expected: FAIL because the detail/update/rerun endpoints and repository helpers do not exist.

- [ ] **Step 3: Implement repository helpers and routes**

```python
# app/history.py
from datetime import datetime
import json

from app.db import connect
from app.models import HistoryRecord, SearchRequest
from app.settings import Settings


def get_history(settings: Settings, history_id: int) -> HistoryRecord | None:
    with connect(settings) as connection:
        row = connection.execute("SELECT * FROM search_history WHERE id = ?", (history_id,)).fetchone()
    return _row_to_history(row) if row else None


def update_history(settings: Settings, history_id: int, request: SearchRequest) -> HistoryRecord:
    now = datetime.utcnow().isoformat()
    with connect(settings) as connection:
        connection.execute(
            """
            UPDATE search_history
            SET origin_city = ?, destination_city = ?, departure_date = ?, max_price = ?,
                departure_time_filters = ?, flight_attribute_filters = ?, airline_filters = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                request.origin_city,
                request.destination_city,
                request.departure_date.isoformat(),
                request.max_price,
                json.dumps(request.departure_time_filters, ensure_ascii=False),
                json.dumps(request.flight_attribute_filters, ensure_ascii=False),
                json.dumps(request.airline_filters, ensure_ascii=False),
                now,
                history_id,
            ),
        )
        row = connection.execute("SELECT * FROM search_history WHERE id = ?", (history_id,)).fetchone()
    return _row_to_history(row)
```

```python
# app/main.py
from fastapi import FastAPI, HTTPException, Request

from app.history import get_history, list_history, update_history
from app.models import SearchRequest
from app.search_service import run_search

    @app.get("/api/history/{history_id}")
    async def history_detail(history_id: int):
        record = get_history(app.state.settings, history_id)
        if record is None:
            raise HTTPException(status_code=404, detail="history record not found")
        return record

    @app.put("/api/history/{history_id}")
    async def history_update(history_id: int, payload: SearchRequest):
        if get_history(app.state.settings, history_id) is None:
            raise HTTPException(status_code=404, detail="history record not found")
        return update_history(app.state.settings, history_id, payload)

    @app.post("/api/history/{history_id}/rerun")
    async def history_rerun(history_id: int):
        record = get_history(app.state.settings, history_id)
        if record is None:
            raise HTTPException(status_code=404, detail="history record not found")
        payload = SearchRequest(**record.model_dump(exclude={"id", "last_searched_at", "created_at", "updated_at"}))
        return await run_search(app.state.settings, app.state.scraper, payload)
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
.venv/bin/python -m pytest tests/test_history_api.py::test_history_detail_update_and_rerun_flow -v
```

Expected: PASS.

- [ ] **Step 5: Commit the history workflow**

Run:
```bash
git add app/history.py app/main.py tests/test_history_api.py && git commit -m "feat: add history edit and rerun endpoints"
```

Expected: a commit containing the reusable history flow.

---

### Task 8: Add persistent browser session management and relogin support

**Files:**
- Create: `app/ctrip_session.py`
- Modify: `app/history.py`
- Modify: `app/main.py`
- Test: `tests/test_session_api.py`

- [ ] **Step 1: Write the failing relogin/session test**

```python
# tests/test_session_api.py
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings


class StubSessionManager:
    async def open_relogin_window(self):
        return {"status": "login_started", "url": "https://example.invalid/session"}


def test_relogin_endpoint_returns_login_started(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    client = TestClient(create_app(settings=settings, session_manager=StubSessionManager()))

    response = client.post("/api/session/relogin")

    assert response.status_code == 200
    assert response.json()["status"] == "login_started"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
.venv/bin/python -m pytest tests/test_session_api.py::test_relogin_endpoint_returns_login_started -v
```

Expected: FAIL because the session manager and `/api/session/relogin` route do not exist.

- [ ] **Step 3: Implement session state persistence and relogin helper**

```python
# app/ctrip_session.py
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

from app.settings import Settings


class CtripSessionManager:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def open_relogin_window(self):
        if not self.settings.ctrip_session_url:
            return {"status": "missing_session_url", "url": ""}

        self.settings.playwright_profile_dir.mkdir(parents=True, exist_ok=True)
        playwright = await async_playwright().start()
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.settings.playwright_profile_dir),
            headless=False,
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(self.settings.ctrip_session_url, wait_until="domcontentloaded")
        return {"status": "login_started", "url": self.settings.ctrip_session_url}
```

```python
# app/history.py
from datetime import datetime

from app.db import connect
from app.models import SessionState
from app.settings import Settings


def save_session_state(settings: Settings, session_status: str, last_successful_scrape_at: str | None = None) -> SessionState:
    now = datetime.utcnow().isoformat()
    with connect(settings) as connection:
        connection.execute(
            """
            INSERT INTO session_state (id, session_status, last_successful_scrape_at, updated_at)
            VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                session_status = excluded.session_status,
                last_successful_scrape_at = excluded.last_successful_scrape_at,
                updated_at = excluded.updated_at
            """,
            (session_status, last_successful_scrape_at, now),
        )
        row = connection.execute("SELECT * FROM session_state WHERE id = 1").fetchone()
    return SessionState(**dict(row))
```

```python
# app/main.py
from app.ctrip_session import CtripSessionManager

    app.state.session_manager = session_manager or CtripSessionManager(app.state.settings)

    @app.post("/api/session/relogin")
    async def relogin():
        return await app.state.session_manager.open_relogin_window()
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
.venv/bin/python -m pytest tests/test_session_api.py::test_relogin_endpoint_returns_login_started -v
```

Expected: PASS.

- [ ] **Step 5: Commit the session helper**

Run:
```bash
git add app/ctrip_session.py app/history.py app/main.py tests/test_session_api.py && git commit -m "feat: add ctrip relogin endpoint"
```

Expected: a commit containing the browser-session flow.

---

### Task 9: Capture a real Ctrip search fixture and lock the URL template workflow

**Files:**
- Create: `app/ctrip_urls.py`
- Create: `scripts/capture_ctrip_snapshot.py`
- Test: `tests/test_ctrip_urls.py`
- Create locally during execution: `tests/fixtures/ctrip_search_results.html`

- [ ] **Step 1: Write the failing search URL builder test**

```python
# tests/test_ctrip_urls.py
from app.ctrip_urls import build_search_url


def test_build_search_url_replaces_origin_destination_and_date() -> None:
    template = "https://travel.example/list?from={origin}&to={destination}&date={date}"

    url = build_search_url(template, "BJS", "SHA", "2026-05-20")

    assert url == "https://travel.example/list?from=BJS&to=SHA&date=2026-05-20"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
.venv/bin/python -m pytest tests/test_ctrip_urls.py::test_build_search_url_replaces_origin_destination_and_date -v
```

Expected: FAIL because `app.ctrip_urls` does not exist.

- [ ] **Step 3: Implement the URL helper and fixture capture script**

```python
# app/ctrip_urls.py
from urllib.parse import quote


def build_search_url(template: str, origin: str, destination: str, departure_date: str) -> str:
    return (
        template.replace("{origin}", quote(origin))
        .replace("{destination}", quote(destination))
        .replace("{date}", quote(departure_date))
    )
```

```python
# scripts/capture_ctrip_snapshot.py
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

from app.ctrip_urls import build_search_url
from app.settings import Settings


async def main() -> None:
    settings = Settings()
    if not settings.ctrip_search_url_template:
        raise SystemExit("Set CTRIP_SEARCH_URL_TEMPLATE before running this script")

    url = build_search_url(
        settings.ctrip_search_url_template,
        origin="北京",
        destination="上海",
        departure_date="2026-05-20",
    )

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(settings.playwright_profile_dir),
            headless=False,
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(url, wait_until="networkidle")
        input("If the page is logged in and fully loaded, press Enter to save the snapshot... ")
        settings.ctrip_snapshot_dir.mkdir(parents=True, exist_ok=True)
        Path(settings.ctrip_snapshot_dir / "ctrip_search_results.html").write_text(
            await page.content(),
            encoding="utf-8",
        )
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
.venv/bin/python -m pytest tests/test_ctrip_urls.py::test_build_search_url_replaces_origin_destination_and_date -v
```

Expected: PASS.

- [ ] **Step 5: Capture the real fixture from a logged-in Ctrip results page**

Run:
```bash
cp .env.example .env
```

Then edit `.env` so it contains:
- `CTRIP_SEARCH_URL_TEMPLATE` — a real Ctrip results URL template with `{origin}`, `{destination}`, and `{date}` tokens
- `CTRIP_SESSION_URL` — any Ctrip page that can be used to refresh login state

After that, run:
```bash
.venv/bin/python scripts/capture_ctrip_snapshot.py
```

Expected: Chromium opens with the persistent profile, the logged-in results page loads, and pressing Enter writes `tests/fixtures/ctrip_search_results.html`.

- [ ] **Step 6: Commit the URL helper and captured fixture**

Run:
```bash
git add app/ctrip_urls.py scripts/capture_ctrip_snapshot.py tests/test_ctrip_urls.py tests/fixtures/ctrip_search_results.html .env.example && git commit -m "feat: capture ctrip results fixture"
```

Expected: a commit containing the deterministic fixture needed for parser work.

---

### Task 10: Parse the captured Ctrip results HTML into flight objects

**Files:**
- Create: `app/ctrip_capture.py`
- Create: `app/ctrip_parser.py`
- Test: `tests/test_ctrip_parser.py`

- [ ] **Step 1: Write the failing parser test against the captured fixture**

```python
# tests/test_ctrip_parser.py
from datetime import date
from pathlib import Path

from app.ctrip_parser import parse_search_results
from app.models import SearchRequest


def test_parse_search_results_extracts_required_fields() -> None:
    html = Path("tests/fixtures/ctrip_search_results.html").read_text(encoding="utf-8")
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

    assert flights
    assert all(flight.flight_no for flight in flights)
    assert all(flight.airline for flight in flights)
    assert all(flight.price > 0 for flight in flights)
    assert all(flight.fallback_search_url == "https://example.invalid/results" for flight in flights)
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
.venv/bin/python -m pytest tests/test_ctrip_parser.py::test_parse_search_results_extracts_required_fields -v
```

Expected: FAIL because `app.ctrip_parser` does not exist yet.

- [ ] **Step 3: Implement snapshot saving and the HTML parser**

```python
# app/ctrip_capture.py
from datetime import datetime
from pathlib import Path

from app.models import SearchRequest
from app.settings import Settings


def save_live_snapshot(settings: Settings, request: SearchRequest, html: str, filename: str = "last_live_search.html") -> Path:
    settings.ctrip_snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = settings.ctrip_snapshot_dir / filename
    path.write_text(html, encoding="utf-8")
    return path
```

```python
# app/ctrip_parser.py
import re
from datetime import time

from bs4 import BeautifulSoup

from app.models import FlightResult, SearchRequest

CARD_SELECTORS = [
    "[data-testid*='flight']",
    "div[class*='flight']",
    "li[class*='flight']",
    "article",
]
FLIGHT_NO_RE = re.compile(r"\b([A-Z0-9]{2}\d{3,4})\b")
TIME_RE = re.compile(r"\b(\d{2}:\d{2})\b")
PRICE_RE = re.compile(r"[¥￥]\s*(\d+)")
DIRECT_WORDS = ("直飞", "无中转")


def parse_search_results(html: str, request: SearchRequest, fallback_search_url: str) -> list[FlightResult]:
    soup = BeautifulSoup(html, "html.parser")
    cards = []
    for selector in CARD_SELECTORS:
        cards = soup.select(selector)
        if cards:
            break

    flights: list[FlightResult] = []
    for card in cards:
        text = " ".join(card.stripped_strings)
        flight_no_match = FLIGHT_NO_RE.search(text)
        times = TIME_RE.findall(text)
        price_match = PRICE_RE.search(text)
        if not flight_no_match or len(times) < 2 or not price_match:
            continue

        airline = text.split()[0]
        href = card.find("a", href=True)
        flights.append(
            FlightResult(
                flight_no=flight_no_match.group(1),
                airline=airline,
                origin_city=request.origin_city,
                destination_city=request.destination_city,
                departure_time=time.fromisoformat(times[0]),
                arrival_time=time.fromisoformat(times[1]),
                is_direct=any(word in text for word in DIRECT_WORDS),
                stop_info="直飞" if any(word in text for word in DIRECT_WORDS) else "经停或中转",
                price=int(price_match.group(1)),
                deeplink_url=href["href"] if href else fallback_search_url,
                fallback_search_url=fallback_search_url,
            )
        )

    return flights
```

- [ ] **Step 4: Run the parser test to verify it passes**

Run:
```bash
.venv/bin/python -m pytest tests/test_ctrip_parser.py::test_parse_search_results_extracts_required_fields -v
```

Expected: PASS against the real captured fixture.

- [ ] **Step 5: Commit the parser**

Run:
```bash
git add app/ctrip_capture.py app/ctrip_parser.py tests/test_ctrip_parser.py && git commit -m "feat: parse captured ctrip search results"
```

Expected: a commit containing the deterministic parser.

---

### Task 11: Wire the live Playwright scraper and map scraper failures to API responses

**Files:**
- Create: `app/ctrip_scraper.py`
- Modify: `app/main.py`
- Modify: `app/search_service.py`
- Test: `tests/test_search_api.py`

- [ ] **Step 1: Extend the failing search API test for scraper failure modes**

```python
# tests/test_search_api.py
from datetime import time

from fastapi.testclient import TestClient

from app.ctrip_scraper import ScrapeFailedError, SessionExpiredError
from app.main import create_app
from app.models import FlightResult
from app.settings import Settings


class ExpiredScraper:
    async def search(self, request):
        raise SessionExpiredError("login required")


class BrokenScraper:
    async def search(self, request):
        raise ScrapeFailedError("parser returned no flights")


def test_search_endpoint_returns_503_when_login_is_required(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    client = TestClient(create_app(settings=settings, scraper=ExpiredScraper()))

    response = client.post(
        "/api/search",
        json={
            "origin_city": "北京",
            "destination_city": "上海",
            "departure_date": "2026-05-20",
        },
    )

    assert response.status_code == 503
    assert response.json()["error"] == "relogin_required"


def test_search_endpoint_returns_502_when_scrape_fails(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    client = TestClient(create_app(settings=settings, scraper=BrokenScraper()))

    response = client.post(
        "/api/search",
        json={
            "origin_city": "北京",
            "destination_city": "上海",
            "departure_date": "2026-05-20",
        },
    )

    assert response.status_code == 502
    assert response.json()["error"] == "scrape_failed"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
.venv/bin/python -m pytest tests/test_search_api.py::test_search_endpoint_returns_503_when_login_is_required tests/test_search_api.py::test_search_endpoint_returns_502_when_scrape_fails -v
```

Expected: FAIL because the scraper exceptions and error mapping do not exist.

- [ ] **Step 3: Implement the live scraper and exception handling**

```python
# app/ctrip_scraper.py
from playwright.async_api import async_playwright

from app.ctrip_capture import save_live_snapshot
from app.ctrip_parser import parse_search_results
from app.ctrip_urls import build_search_url
from app.models import SearchRequest
from app.settings import Settings


class SessionExpiredError(RuntimeError):
    pass


class ScrapeFailedError(RuntimeError):
    pass


class CtripScraper:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def search(self, request: SearchRequest):
        if not self.settings.ctrip_search_url_template:
            raise ScrapeFailedError("CTRIP_SEARCH_URL_TEMPLATE is not configured")

        search_url = build_search_url(
            self.settings.ctrip_search_url_template,
            request.origin_city,
            request.destination_city,
            request.departure_date.isoformat(),
        )

        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.settings.playwright_profile_dir),
                headless=False,
            )
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(search_url, wait_until="networkidle")
            html = await page.content()
            save_live_snapshot(self.settings, request, html)
            await context.close()

        if "登录" in html or "验证码" in html:
            raise SessionExpiredError("Ctrip requires a fresh login in the persistent browser profile")

        flights = parse_search_results(html, request, fallback_search_url=search_url)
        if not flights:
            raise ScrapeFailedError("parser returned no flights")
        return flights
```

```python
# app/main.py
from fastapi import FastAPI, HTTPException, Request

from app.ctrip_scraper import CtripScraper, ScrapeFailedError, SessionExpiredError

    app.state.scraper = scraper or CtripScraper(app.state.settings)

    @app.post("/api/search")
    async def search(payload: SearchRequest):
        try:
            return await run_search(app.state.settings, app.state.scraper, payload)
        except SessionExpiredError as exc:
            raise HTTPException(status_code=503, detail={"error": "relogin_required", "message": str(exc)})
        except ScrapeFailedError as exc:
            raise HTTPException(status_code=502, detail={"error": "scrape_failed", "message": str(exc)})
```

```python
# app/main.py
from fastapi.responses import JSONResponse

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        if isinstance(exc.detail, dict):
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
```

- [ ] **Step 4: Run the failure-mode tests and the earlier happy-path search test**

Run:
```bash
.venv/bin/python -m pytest tests/test_search_api.py -v
```

Expected: PASS for both failure-mode tests and the earlier fake-scraper success case.

- [ ] **Step 5: Commit the live scraper integration**

Run:
```bash
git add app/ctrip_scraper.py app/main.py app/search_service.py tests/test_search_api.py && git commit -m "feat: integrate live ctrip scraper"
```

Expected: a commit containing the real scraper path and explicit error mapping.

---

### Task 12: Verify the full MVP manually and lock the final UX

**Files:**
- Modify if needed: `app/static/app.js`
- Modify if needed: `app/templates/index.html`
- Modify if needed: `app/static/app.css`
- Test: all existing tests

- [ ] **Step 1: Run the full automated test suite**

Run:
```bash
.venv/bin/python -m pytest -v
```

Expected: all repository, filter, API, session, URL, parser, and homepage tests pass.

- [ ] **Step 2: Start the app and perform a real manual search**

Run:
```bash
.venv/bin/python -m uvicorn app.main:app --reload
```

Expected: the app starts at `http://127.0.0.1:8000`.

Manual checklist in the browser:
- Enter origin, destination, date, and max price
- Expand each filter group and verify only selected items appear in the selected-tag area
- Click `开始搜索` and confirm the results area shows the current lowest price and at least one result card
- Click a flight jump link and confirm it opens the matching Ctrip page or results page
- Confirm a new history row appears
- Click `编辑` and confirm the saved values refill the form
- Click `重新搜索` and confirm a fresh search runs with the saved criteria

- [ ] **Step 3: Trigger the relogin flow and verify the fallback**

Run:
```bash
curl -X POST http://127.0.0.1:8000/api/session/relogin
```

Expected: JSON with either `{"status": "login_started"}` or `{"status": "missing_session_url"}` depending on local configuration. If login starts, finish the login manually in the opened persistent browser window.

- [ ] **Step 4: Make only the smallest UI fixes needed to satisfy the manual checklist**

```javascript
// app/static/app.js
// If history edit/rerun wiring is still missing, add this minimal event delegation:
document.getElementById("history-list").addEventListener("click", async (event) => {
  const action = event.target.dataset.historyAction;
  if (!action) return;
  const row = event.target.closest("[data-history-id]");
  const historyId = row.dataset.historyId;

  if (action === "edit") {
    const response = await fetch(`/api/history/${historyId}`);
    const record = await response.json();
    Object.entries(record).forEach(([key, value]) => {
      const input = document.querySelector(`[name='${key}']`);
      if (input && typeof value !== "object") input.value = value ?? "";
    });
  }

  if (action === "rerun") {
    const response = await fetch(`/api/history/${historyId}/rerun`, { method: "POST" });
    const payload = await response.json();
    document.getElementById("search-summary").textContent = `当前最低价 ¥${payload.lowest_price ?? "--"}`;
  }
});
```

Expected: only small fixes are needed at this stage; if large rewrites are needed, stop and split a follow-up plan instead of thrashing.

- [ ] **Step 5: Commit the verified MVP**

Run:
```bash
git add app/main.py app/static/app.js app/static/app.css app/templates/index.html && git commit -m "feat: finalize flight comparison mvp"
```

Expected: a final commit after both automated and manual verification succeed.

---

## Self-Review Checklist

### Spec coverage
- Web front end: covered by Tasks 2, 6, and 12.
- Real Ctrip search path: covered by Tasks 8, 9, 10, and 11.
- Filtering by price/time/airline/direct: covered by Task 4 and exercised again in Tasks 5 and 12.
- Lowest price display: covered by Tasks 4, 5, and 12.
- Click-through to Ctrip: supported by `deeplink_url` / `fallback_search_url` in Tasks 4, 10, 11, and 12.
- Search history save/edit/rerun: covered by Tasks 3, 5, 7, and 12.
- Explicit relogin flow and scrape failure handling: covered by Tasks 8 and 11.

### Placeholder scan
- No `TODO`, `TBD`, or “similar to previous task” placeholders remain.
- The only manual inputs are the two required local environment variables needed to bind the app to a real Ctrip session.

### Type consistency
- `SearchRequest`, `FlightResult`, `SearchResponse`, and `HistoryRecord` are introduced in Tasks 3–4 and reused consistently afterward.
- Scraper failure types are defined once in Task 11 and reused only through the API layer.

### External dependency gate
- The live scraper tasks do not guess selectors before capturing a real fixture. The parser is intentionally driven by `tests/fixtures/ctrip_search_results.html` first.
