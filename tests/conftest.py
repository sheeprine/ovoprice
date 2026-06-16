import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from unittest.mock import patch

from database import Base, get_db, Product, Variant, PriceCheck
from main import app

# Shared fake Shopify product payload (what fetch_product returns)
FAKE_RAW_PRODUCT = {
    "handle": "test-battery",
    "title": "Test Battery 6S 1300mAh",
    "images": [{"src": "https://cdn.example.com/image.jpg"}],
    "variants": [
        {
            "id": 111,
            "title": "1 Pack",
            "sku": "TEST-1P",
            "price": "29.00",
            "compare_at_price": "44.00",
        },
        {
            "id": 222,
            "title": "2 Pack",
            "sku": "TEST-2P",
            "price": "43.00",
            "compare_at_price": "67.00",
        },
    ],
}


@pytest.fixture
def test_engine():
    # StaticPool ensures all sessions share one in-memory SQLite connection
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(test_engine):
    with Session(test_engine) as session:
        yield session


@pytest.fixture
def client(test_engine):
    def override_get_db():
        with Session(test_engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    with (
        patch("main.init_db"),
        patch("main.start_scheduler"),
        patch("main.stop_scheduler"),
    ):
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c

    app.dependency_overrides.clear()


@pytest.fixture
def seeded_product(db_session):
    product = Product(
        handle="test-battery",
        title="Test Battery 6S 1300mAh",
        image_url="https://cdn.example.com/image.jpg",
        product_url="https://www.ampow.com/products/test-battery",
    )
    db_session.add(product)
    db_session.flush()

    v1 = Variant(product_id=product.id, shopify_variant_id=111, name="1 Pack", sku="TEST-1P", tracked=True)
    v2 = Variant(product_id=product.id, shopify_variant_id=222, name="2 Pack", sku="TEST-2P", tracked=True)
    db_session.add_all([v1, v2])
    db_session.flush()

    db_session.add_all([
        PriceCheck(variant_id=v1.id, price=29.0, compare_at_price=44.0),
        PriceCheck(variant_id=v2.id, price=43.0, compare_at_price=67.0),
    ])
    db_session.commit()

    return product
