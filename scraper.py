import re
from typing import Optional
import httpx

AMPOW_BASE = "https://www.ampow.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; OvoPrice/1.0; price tracker)",
    "Accept": "application/json",
}


def extract_handle(url: str) -> Optional[str]:
    match = re.search(r"/products/([^/?#]+)", url)
    return match.group(1) if match else None


def fetch_product(handle: str) -> Optional[dict]:
    url = f"{AMPOW_BASE}/products/{handle}.json"
    try:
        with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=15) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return None
            data = resp.json()
            return data.get("product")
    except Exception:
        return None


def parse_product(raw: dict) -> dict:
    image_url = None
    if raw.get("images"):
        image_url = raw["images"][0].get("src")

    variants = []
    for v in raw.get("variants", []):
        price = float(v["price"]) if v.get("price") else 0.0
        compare_at = float(v["compare_at_price"]) if v.get("compare_at_price") else None
        variants.append(
            {
                "shopify_variant_id": v["id"],
                "name": v.get("title", "Default"),
                "sku": v.get("sku", ""),
                "price": price,
                "compare_at_price": compare_at,
            }
        )

    return {
        "handle": raw["handle"],
        "title": raw["title"],
        "image_url": image_url,
        "product_url": f"{AMPOW_BASE}/products/{raw['handle']}",
        "variants": variants,
    }
