import pytest
import httpx
from unittest.mock import patch, MagicMock

from scraper import extract_handle, fetch_product, parse_product


class TestExtractHandle:
    def test_full_url(self):
        assert extract_handle("https://www.ampow.com/products/my-battery") == "my-battery"

    def test_url_with_query_params(self):
        assert extract_handle("https://www.ampow.com/products/my-battery?variant=123") == "my-battery"

    def test_url_with_fragment(self):
        assert extract_handle("https://www.ampow.com/products/my-battery#details") == "my-battery"

    def test_url_with_hyphenated_handle(self):
        handle = extract_handle("https://www.ampow.com/products/ovonic-100c-1300mah-6s1p-22-2v-xt60")
        assert handle == "ovonic-100c-1300mah-6s1p-22-2v-xt60"

    def test_path_only(self):
        assert extract_handle("/products/my-battery") == "my-battery"

    def test_non_product_url_returns_none(self):
        assert extract_handle("https://www.ampow.com/collections/all") is None

    def test_empty_string_returns_none(self):
        assert extract_handle("") is None

    def test_unrelated_url_returns_none(self):
        assert extract_handle("https://example.com/page") is None


class TestParseProduct:
    def test_full_product(self):
        raw = {
            "handle": "test-battery",
            "title": "Test Battery 6S",
            "images": [{"src": "https://cdn.example.com/img.jpg"}],
            "variants": [
                {"id": 1, "title": "1 Pack", "sku": "TB-1P", "price": "29.00", "compare_at_price": "44.00"},
            ],
        }
        result = parse_product(raw)

        assert result["handle"] == "test-battery"
        assert result["title"] == "Test Battery 6S"
        assert result["image_url"] == "https://cdn.example.com/img.jpg"
        assert result["product_url"] == "https://www.ampow.com/products/test-battery"
        assert len(result["variants"]) == 1
        v = result["variants"][0]
        assert v["shopify_variant_id"] == 1
        assert v["name"] == "1 Pack"
        assert v["sku"] == "TB-1P"
        assert v["price"] == 29.0
        assert v["compare_at_price"] == 44.0

    def test_no_images(self):
        raw = {
            "handle": "test",
            "title": "Test",
            "images": [],
            "variants": [],
        }
        assert parse_product(raw)["image_url"] is None

    def test_missing_images_key(self):
        raw = {"handle": "test", "title": "Test", "variants": []}
        assert parse_product(raw)["image_url"] is None

    def test_variant_without_compare_at_price(self):
        raw = {
            "handle": "test",
            "title": "Test",
            "images": [],
            "variants": [
                {"id": 1, "title": "Default", "sku": "", "price": "19.99", "compare_at_price": None},
            ],
        }
        v = parse_product(raw)["variants"][0]
        assert v["price"] == 19.99
        assert v["compare_at_price"] is None

    def test_multiple_variants(self):
        raw = {
            "handle": "test",
            "title": "Test",
            "images": [],
            "variants": [
                {"id": 1, "title": "1 Pack", "sku": "A", "price": "10.00", "compare_at_price": None},
                {"id": 2, "title": "2 Pack", "sku": "B", "price": "18.00", "compare_at_price": "22.00"},
                {"id": 3, "title": "4 Pack", "sku": "C", "price": "32.00", "compare_at_price": "40.00"},
            ],
        }
        variants = parse_product(raw)["variants"]
        assert len(variants) == 3
        assert variants[1]["price"] == 18.0
        assert variants[2]["compare_at_price"] == 40.0

    def test_variant_with_no_price_defaults_to_zero(self):
        raw = {
            "handle": "test",
            "title": "Test",
            "images": [],
            "variants": [
                {"id": 1, "title": "Default", "sku": "", "price": None, "compare_at_price": None},
            ],
        }
        assert parse_product(raw)["variants"][0]["price"] == 0.0

    def test_variant_missing_title_uses_default(self):
        raw = {
            "handle": "test",
            "title": "Test",
            "images": [],
            "variants": [
                {"id": 1, "sku": "", "price": "9.99", "compare_at_price": None},
            ],
        }
        assert parse_product(raw)["variants"][0]["name"] == "Default"


class TestFetchProduct:
    def _mock_response(self, status_code: int, json_data: dict):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = status_code
        resp.json.return_value = json_data
        return resp

    def test_success_returns_product(self):
        payload = {"product": {"handle": "test", "title": "Test", "images": [], "variants": []}}
        mock_resp = self._mock_response(200, payload)

        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.get.return_value = mock_resp
            result = fetch_product("test")

        assert result == payload["product"]

    def test_404_returns_none(self):
        mock_resp = self._mock_response(404, {})

        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.get.return_value = mock_resp
            result = fetch_product("nonexistent")

        assert result is None

    def test_network_error_returns_none(self):
        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.get.side_effect = httpx.ConnectError("timeout")
            result = fetch_product("test")

        assert result is None

    def test_missing_product_key_returns_none(self):
        mock_resp = self._mock_response(200, {"not_product": {}})

        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.get.return_value = mock_resp
            result = fetch_product("test")

        assert result is None

    def test_requests_correct_url(self):
        mock_resp = self._mock_response(200, {"product": {"handle": "my-bat", "title": "T", "images": [], "variants": []}})

        with patch("httpx.Client") as mock_client_cls:
            mock_get = mock_client_cls.return_value.__enter__.return_value.get
            mock_get.return_value = mock_resp
            fetch_product("my-bat")

        called_url = mock_get.call_args[0][0]
        assert called_url == "https://www.ampow.com/products/my-bat.json"
