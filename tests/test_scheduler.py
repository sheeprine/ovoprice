from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from database import Base, Product, Variant, PriceCheck
from scheduler import check_product_prices, check_all_prices

FAKE_RAW = {
    "handle": "test-battery",
    "title": "Test Battery 6S 1300mAh",
    "images": [{"src": "https://cdn.example.com/image.jpg"}],
    "variants": [
        {
            "id": 111,
            "title": "1 Pack",
            "sku": "TEST-1P",
            "price": "27.00",
            "compare_at_price": "44.00",
        },
    ],
}


@pytest.fixture
def engine():
    e = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=e)
    yield e
    Base.metadata.drop_all(bind=e)


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture
def product_with_variant(session):
    product = Product(
        handle="test-battery",
        title="Test Battery 6S 1300mAh",
        product_url="https://www.ampow.com/products/test-battery",
    )
    session.add(product)
    session.flush()

    variant = Variant(
        product_id=product.id,
        shopify_variant_id=111,
        name="1 Pack",
        sku="TEST-1P",
        tracked=True,
    )
    session.add(variant)
    session.flush()

    session.add(PriceCheck(variant_id=variant.id, price=29.0, compare_at_price=44.0))
    session.commit()

    return product, variant


class TestCheckProductPrices:
    def test_creates_new_price_check(self, session, product_with_variant):
        product, variant = product_with_variant

        with patch("scheduler.fetch_product", return_value=FAKE_RAW):
            check_product_prices("test-battery", session=session)
        session.commit()

        session.expire_all()
        checks = session.query(PriceCheck).filter_by(variant_id=variant.id).order_by(PriceCheck.id).all()
        assert len(checks) == 2
        assert checks[-1].price == 27.0
        assert checks[-1].compare_at_price == 44.0

    def test_updates_last_checked_at(self, session, product_with_variant):
        product, _ = product_with_variant
        assert product.last_checked_at is None

        with patch("scheduler.fetch_product", return_value=FAKE_RAW):
            check_product_prices("test-battery", session=session)
        session.commit()

        session.expire_all()
        product = session.query(Product).filter_by(handle="test-battery").first()
        assert product.last_checked_at is not None

    def test_unknown_handle_is_noop(self, session):
        with patch("scheduler.fetch_product", return_value=FAKE_RAW):
            check_product_prices("nonexistent", session=session)
        session.commit()

        assert session.query(PriceCheck).count() == 0

    def test_fetch_failure_is_noop(self, session, product_with_variant):
        _, variant = product_with_variant

        with patch("scheduler.fetch_product", return_value=None):
            check_product_prices("test-battery", session=session)

        session.expire_all()
        checks = session.query(PriceCheck).filter_by(variant_id=variant.id).all()
        assert len(checks) == 1  # only the initial check, no new ones

    def test_skips_untracked_variants(self, session, product_with_variant):
        product, variant = product_with_variant
        variant.tracked = False
        session.commit()

        with patch("scheduler.fetch_product", return_value=FAKE_RAW):
            check_product_prices("test-battery", session=session)
        session.commit()

        session.expire_all()
        checks = session.query(PriceCheck).filter_by(variant_id=variant.id).all()
        assert len(checks) == 1  # no new check added

    def test_ignores_unknown_variant_ids_from_api(self, session, product_with_variant):
        # API returns a variant not in our tracking list
        raw = {**FAKE_RAW, "variants": [{"id": 999, "title": "New Pack", "sku": "", "price": "50.00", "compare_at_price": None}]}

        with patch("scheduler.fetch_product", return_value=raw):
            check_product_prices("test-battery", session=session)
        session.commit()

        assert session.query(PriceCheck).count() == 1  # only the initial check

    def test_own_session_path(self, engine, product_with_variant):
        # Test the branch where no session is passed (scheduler owns the session)
        with patch("scheduler.engine", engine):
            with patch("scheduler.fetch_product", return_value=FAKE_RAW):
                check_product_prices("test-battery")  # no session passed

        _, variant = product_with_variant
        with Session(engine) as s:
            checks = s.query(PriceCheck).filter_by(variant_id=variant.id).all()
        assert len(checks) == 2


class TestCheckAllPrices:
    def test_checks_all_products(self, engine, session):
        for handle in ("bat-a", "bat-b"):
            p = Product(handle=handle, title=handle.upper(), product_url=f"https://www.ampow.com/products/{handle}")
            session.add(p)
        session.commit()

        with patch("scheduler.engine", engine):
            with patch("scheduler.check_product_prices") as mock_check:
                check_all_prices()

        handles_checked = {call.args[0] for call in mock_check.call_args_list}
        assert handles_checked == {"bat-a", "bat-b"}

    def test_empty_db_does_not_error(self, engine):
        with patch("scheduler.engine", engine):
            check_all_prices()  # should not raise
