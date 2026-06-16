# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
uv sync

# Install with dev dependencies (pytest)
uv sync --group dev

# Run the app
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/test_scraper.py

# Run a single test
uv run pytest tests/test_routes.py::TestTrack::test_creates_product_in_db
```

## Architecture

The app tracks prices on [ampow.com](https://www.ampow.com/) (a Shopify store). It uses **Shopify's JSON API** (`/products/{handle}.json`) rather than HTML scraping — no BeautifulSoup, no CSS selectors.

**Request flow for tracking a product:**
1. User pastes a URL → `POST /lookup` extracts the Shopify handle, calls `fetch_product()`, renders `preview.html` with variant checkboxes
2. User selects variants → `POST /track` saves `Product` + `Variant` rows and records the first `PriceCheck` immediately
3. `APScheduler` runs `check_all_prices()` every hour in the background, adding new `PriceCheck` rows for all tracked variants

**Data model** (`database.py`):
- `Product` — one row per tracked ampow.com product (keyed by Shopify handle)
- `Variant` — one row per tracked variant (e.g. "1 Pack", "2 Pack"); `tracked=False` soft-disables without deleting history
- `PriceCheck` — append-only price snapshot; the history that drives the chart

**Key design decisions:**
- `Product.handle` is the natural key (unique); re-tracking an existing product reuses the same row rather than duplicating it
- `time_ago()` in `main.py` normalises naive datetimes to UTC before comparing — necessary because SQLite strips timezone info on read
- The global `engine` in `database.py` is imported directly by `scheduler.py`; tests patch `scheduler.engine` to inject an in-memory SQLite engine

**Test setup** (`tests/conftest.py`):
- Uses `StaticPool` so all SQLAlchemy sessions share one in-memory SQLite connection within a test
- `client` fixture patches `main.init_db`, `main.start_scheduler`, and `main.stop_scheduler` to avoid touching the production DB or starting background jobs
- `get_db` dependency is overridden via `app.dependency_overrides` to use the test engine
- `fetch_product` and `check_product_prices` are patched per-test with `unittest.mock.patch` where HTTP calls or scheduler side-effects must be avoided

**Starlette 1.3.x API note:** `TemplateResponse` takes `request` as the first positional argument, not inside the context dict:
```python
# correct
templates.TemplateResponse(request, "template.html", {"key": val})
```
