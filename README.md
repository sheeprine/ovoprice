# OvoPrice

A price tracker web application for [ampow.com](https://www.ampow.com/) — monitors LiPo battery and charger prices over time, stores history, and visualizes trends.

## Features

- **Track products** by pasting any `ampow.com/products/...` URL
- **Variant selection** — choose which pack sizes or options to monitor
- **Price history chart** — interactive line graph per variant (Chart.js)
- **Change indicators** — ↓/↑ percentage vs. first tracked price, color-coded
- **Manual refresh** — "Check Now" button to fetch current prices on demand
- **Hourly auto-check** — background scheduler updates all tracked products automatically
- **Remove tracking** — delete a product and its full price history

## Stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI + Jinja2 |
| Database | SQLite via SQLAlchemy |
| HTTP client | httpx |
| Scheduler | APScheduler |
| Frontend | Tailwind CSS (CDN) + Chart.js (CDN) |
| Package manager | uv |

Prices are fetched via Shopify's clean JSON API (`/products/{handle}.json`), not HTML scraping, so it's resilient to layout changes.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
git clone <repo>
cd ovoprice
uv sync
```

## Running

```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open [http://localhost:8000](http://localhost:8000).

## Usage

1. Click **Track Product** in the top-right corner
2. Paste a product URL, e.g. `https://www.ampow.com/products/ovonic-100c-1300mah-6s1p-22-2v-xt60-4pcs-lipo-battery`
3. Select which variants (pack sizes) to track
4. Click **Start Tracking** — the initial price is recorded immediately
5. Prices are rechecked every hour in the background
6. Visit the product detail page to see the full price history chart

## Project Structure

```
ovoprice/
├── main.py          # FastAPI app and all routes
├── database.py      # SQLAlchemy models (Product, Variant, PriceCheck)
├── scraper.py       # Shopify JSON API fetcher and parser
├── scheduler.py     # APScheduler hourly price check job
├── pyproject.toml
└── templates/
    ├── base.html
    ├── index.html   # Home — tracked product grid
    ├── add.html     # Enter product URL
    ├── preview.html # Select variants before tracking
    └── product.html # Price history chart and variant table
```

## Database Schema

```
products      — handle, title, image_url, product_url, last_checked_at
variants      — product_id, shopify_variant_id, name, sku, tracked
price_checks  — variant_id, price, compare_at_price, checked_at
```

The SQLite database file (`ovoprice.db`) is created automatically on first run.
