"""
Microservice Tests — The "Before"

Traditional API testing. Input X → Output Y. Deterministic. Repeatable.
This is what you know. This is what works for microservices.
"""

import pytest
from fastapi.testclient import TestClient
from pricing_service.app import app

client = TestClient(app)


class TestPriceLookup:
    """Simple GET tests. Assert on exact values."""

    def test_get_base_price(self):
        response = client.get("/price/WIDGET-PRO")
        assert response.status_code == 200
        data = response.json()
        assert data["base_price"] == 99.99
        assert data["currency"] == "USD"

    def test_product_not_found(self):
        response = client.get("/price/NONEXISTENT")
        assert response.status_code == 404

    def test_all_products_have_prices(self):
        products = ["WIDGET-PRO", "WIDGET-BASIC", "WIDGET-ENT", "ADDON-SUPPORT", "ADDON-ANALYTICS"]
        for product_id in products:
            response = client.get(f"/price/{product_id}")
            assert response.status_code == 200
            assert response.json()["base_price"] > 0


class TestDiscountCalculation:
    """Deterministic discount tests. Same input, same output, every time."""

    def test_no_volume_discount(self):
        response = client.get("/price/WIDGET-PRO/discount?quantity=1")
        data = response.json()
        assert data["volume_discount_pct"] == 0.0
        assert data["unit_price"] == 99.99

    def test_bronze_tier_discount(self):
        response = client.get("/price/WIDGET-PRO/discount?quantity=5")
        data = response.json()
        assert data["volume_discount_pct"] == 0.05
        assert data["unit_price"] == pytest.approx(94.99, abs=0.01)

    def test_silver_tier_discount(self):
        response = client.get("/price/WIDGET-PRO/discount?quantity=10")
        data = response.json()
        assert data["volume_discount_pct"] == 0.10

    def test_discount_cap_at_30_percent(self):
        """Discount should never exceed 30% regardless of stacking."""
        response = client.get("/price/WIDGET-ENT/discount?quantity=50")
        data = response.json()
        # Enterprise gets 10% category + 20% volume = 30% (at cap)
        assert data["total_discount_pct"] <= 0.30


class TestQuoteGeneration:
    """Quote endpoint tests. Structured input, structured output."""

    def test_simple_quote(self):
        response = client.post("/quote", json={
            "customer_id": "C-1234",
            "items": [{"product_id": "WIDGET-PRO", "quantity": 1}],
        })
        assert response.status_code == 200
        data = response.json()
        assert data["customer_id"] == "C-1234"
        assert data["final_total"] > 0
        assert data["quote_id"].startswith("Q-")

    def test_multi_item_quote(self):
        response = client.post("/quote", json={
            "customer_id": "C-1234",
            "items": [
                {"product_id": "WIDGET-PRO", "quantity": 2},
                {"product_id": "ADDON-SUPPORT", "quantity": 2},
            ],
        })
        data = response.json()
        assert len(data["line_items"]) == 2
        assert data["final_total"] > 0

    def test_promo_code(self):
        response = client.post("/quote", json={
            "customer_id": "C-1234",
            "items": [{"product_id": "WIDGET-PRO", "quantity": 1}],
            "promo_code": "SAVE10",
        })
        data = response.json()
        assert data["discount_total"] > 0

    def test_invalid_product_in_quote(self):
        response = client.post("/quote", json={
            "customer_id": "C-1234",
            "items": [{"product_id": "NONEXISTENT", "quantity": 1}],
        })
        assert response.status_code == 404


class TestHealth:
    def test_health_check(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["service"] == "PricingService"
