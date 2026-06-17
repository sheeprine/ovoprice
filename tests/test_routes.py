from unittest.mock import patch

import pytest

from conftest import FAKE_RAW_PRODUCT
from database import PriceCheck, Product, Variant


class TestIndex:
    def test_empty_state_shows_empty_message(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Track your first product" in resp.text

    def test_shows_product_card_when_tracked(self, client, seeded_product):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Test Battery" in resp.text
        # 2 Pack at €43 → €21.50/item beats 1 Pack at €29.00/item
        assert "€21.50" in resp.text

    def test_shows_variant_count(self, client, seeded_product):
        resp = client.get("/")
        assert "2 variants" in resp.text

    def test_price_decrease_shown_in_green(self, client, seeded_product, db_session):
        # Add a lower price check so change_pct is negative
        v = db_session.query(Variant).filter_by(name="1 Pack").first()
        db_session.add(PriceCheck(variant_id=v.id, price=20.0, compare_at_price=44.0))
        db_session.commit()

        resp = client.get("/")
        assert "↓" in resp.text
        assert "emerald" in resp.text  # green CSS class


class TestAddPage:
    def test_returns_200(self, client):
        assert client.get("/add").status_code == 200

    def test_contains_url_input(self, client):
        assert 'name="url"' in client.get("/add").text

    def test_shows_error_from_query_param(self, client):
        resp = client.get("/add?error=Something+went+wrong")
        assert "Something went wrong" in resp.text


class TestLookup:
    def test_invalid_url_shows_error(self, client):
        resp = client.post("/lookup", data={"url": "https://example.com/not-a-product"})
        assert resp.status_code == 200
        assert "Invalid URL" in resp.text

    def test_fetch_failure_shows_error(self, client):
        with patch("main.fetch_product", return_value=None):
            resp = client.post("/lookup", data={"url": "https://www.ampow.com/products/nonexistent"})
        assert resp.status_code == 200
        assert "Could not fetch" in resp.text

    def test_valid_url_shows_preview(self, client):
        with patch("main.fetch_product", return_value=FAKE_RAW_PRODUCT):
            resp = client.post("/lookup", data={"url": "https://www.ampow.com/products/test-battery"})
        assert resp.status_code == 200
        assert "Test Battery 6S 1300mAh" in resp.text
        assert "1 Pack" in resp.text
        assert "2 Pack" in resp.text
        assert "€29.00" in resp.text

    def test_preview_shows_variant_checkboxes(self, client):
        with patch("main.fetch_product", return_value=FAKE_RAW_PRODUCT):
            resp = client.post("/lookup", data={"url": "https://www.ampow.com/products/test-battery"})
        assert 'type="checkbox"' in resp.text
        assert 'name="variant_ids"' in resp.text


class TestTrack:
    def test_no_variants_redirects_to_add(self, client):
        resp = client.post(
            "/track",
            data={"handle": "test-battery"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "/add" in resp.headers["location"]

    def test_creates_product_in_db(self, client, db_session):
        with patch("main.fetch_product", return_value=FAKE_RAW_PRODUCT):
            client.post("/track", data={"handle": "test-battery", "variant_ids": ["111"]})

        db_session.expire_all()
        product = db_session.query(Product).filter_by(handle="test-battery").first()
        assert product is not None
        assert product.title == "Test Battery 6S 1300mAh"
        assert product.image_url == "https://cdn.example.com/image.jpg"

    def test_creates_selected_variant_only(self, client, db_session):
        with patch("main.fetch_product", return_value=FAKE_RAW_PRODUCT):
            client.post("/track", data={"handle": "test-battery", "variant_ids": ["111"]})

        db_session.expire_all()
        product = db_session.query(Product).filter_by(handle="test-battery").first()
        variants = db_session.query(Variant).filter_by(product_id=product.id).all()
        assert len(variants) == 1
        assert variants[0].shopify_variant_id == 111
        assert variants[0].name == "1 Pack"

    def test_creates_initial_price_check(self, client, db_session):
        with patch("main.fetch_product", return_value=FAKE_RAW_PRODUCT):
            client.post("/track", data={"handle": "test-battery", "variant_ids": ["111"]})

        db_session.expire_all()
        product = db_session.query(Product).filter_by(handle="test-battery").first()
        variant = db_session.query(Variant).filter_by(product_id=product.id, shopify_variant_id=111).first()
        checks = db_session.query(PriceCheck).filter_by(variant_id=variant.id).all()
        assert len(checks) == 1
        assert checks[0].price == 29.0
        assert checks[0].compare_at_price == 44.0

    def test_redirects_to_product_page(self, client):
        with patch("main.fetch_product", return_value=FAKE_RAW_PRODUCT):
            resp = client.post(
                "/track",
                data={"handle": "test-battery", "variant_ids": ["111"]},
                follow_redirects=False,
            )
        assert resp.status_code == 303
        assert resp.headers["location"].endswith("/products/test-battery")

    def test_tracking_multiple_variants(self, client, db_session):
        with patch("main.fetch_product", return_value=FAKE_RAW_PRODUCT):
            client.post("/track", data={"handle": "test-battery", "variant_ids": ["111", "222"]})

        db_session.expire_all()
        product = db_session.query(Product).filter_by(handle="test-battery").first()
        variants = db_session.query(Variant).filter_by(product_id=product.id).all()
        assert len(variants) == 2

    def test_retracking_existing_product_does_not_duplicate_variants(self, client, seeded_product, db_session):
        with patch("main.fetch_product", return_value=FAKE_RAW_PRODUCT):
            client.post("/track", data={"handle": "test-battery", "variant_ids": ["111"]})

        db_session.expire_all()
        variants = db_session.query(Variant).filter_by(product_id=seeded_product.id).all()
        assert len(variants) == 2  # original 2, not duplicated

    def test_fetch_failure_returns_400(self, client):
        with patch("main.fetch_product", return_value=None):
            resp = client.post("/track", data={"handle": "bad-handle", "variant_ids": ["111"]})
        assert resp.status_code == 400


class TestProductDetail:
    def test_unknown_handle_returns_404(self, client):
        assert client.get("/products/nonexistent").status_code == 404

    def test_shows_product_title(self, client, seeded_product):
        resp = client.get("/products/test-battery")
        assert resp.status_code == 200
        assert "Test Battery 6S 1300mAh" in resp.text

    def test_shows_variant_prices(self, client, seeded_product):
        resp = client.get("/products/test-battery")
        assert "€29.00" in resp.text
        assert "€43.00" in resp.text

    def test_shows_compare_at_prices(self, client, seeded_product):
        resp = client.get("/products/test-battery")
        assert "€44.00" in resp.text
        assert "€67.00" in resp.text

    def test_includes_chart_data(self, client, seeded_product):
        resp = client.get("/products/test-battery")
        assert "priceChart" in resp.text
        assert "29.0" in resp.text  # price in JSON dataset

    def test_shows_ampow_link(self, client, seeded_product):
        resp = client.get("/products/test-battery")
        assert "ampow.com/products/test-battery" in resp.text


class TestManualCheck:
    def test_unknown_handle_returns_404(self, client):
        resp = client.post("/products/nonexistent/check")
        assert resp.status_code == 404

    def test_triggers_price_check(self, client, seeded_product):
        with patch("main.check_product_prices") as mock_check:
            client.post("/products/test-battery/check", follow_redirects=False)
        mock_check.assert_called_once_with("test-battery")

    def test_redirects_to_product_page(self, client, seeded_product):
        with patch("main.check_product_prices"):
            resp = client.post("/products/test-battery/check", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"].endswith("/products/test-battery")


class TestDeleteProduct:
    def test_unknown_handle_returns_404(self, client):
        resp = client.post("/products/nonexistent/delete")
        assert resp.status_code == 404

    def test_removes_product_from_db(self, client, seeded_product, db_session):
        client.post("/products/test-battery/delete")

        db_session.expire_all()
        assert db_session.query(Product).filter_by(handle="test-battery").first() is None

    def test_cascades_to_variants_and_checks(self, client, seeded_product, db_session):
        product_id = seeded_product.id
        client.post("/products/test-battery/delete")

        db_session.expire_all()
        assert db_session.query(Variant).filter_by(product_id=product_id).count() == 0
        variants = db_session.query(Variant).filter_by(product_id=product_id).all()
        for v in variants:
            assert db_session.query(PriceCheck).filter_by(variant_id=v.id).count() == 0

    def test_redirects_to_home(self, client, seeded_product):
        resp = client.post("/products/test-battery/delete", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/"
