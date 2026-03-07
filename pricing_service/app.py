"""
PricingService — The "Before"

A traditional microservice. Deterministic. Stateless. Rigid contracts.
This is what most organizations have today.

Endpoints:
    GET  /price/{product_id}           → Base price lookup
    GET  /price/{product_id}/discount  → Apply discount rules
    POST /quote                        → Generate a quote with multiple products
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

app = FastAPI(title="PricingService", version="1.0.0")


# ---------------------------------------------------------------------------
# Data layer (in production, this would be a database)
# ---------------------------------------------------------------------------

PRODUCTS = {
    "WIDGET-PRO": {"name": "Widget Pro", "base_price": 99.99, "category": "premium"},
    "WIDGET-BASIC": {"name": "Widget Basic", "base_price": 49.99, "category": "standard"},
    "WIDGET-ENT": {"name": "Widget Enterprise", "base_price": 299.99, "category": "enterprise"},
    "ADDON-SUPPORT": {"name": "Premium Support", "base_price": 29.99, "category": "addon"},
    "ADDON-ANALYTICS": {"name": "Analytics Pack", "base_price": 19.99, "category": "addon"},
}

DISCOUNT_RULES = {
    "volume_5": {"min_quantity": 5, "discount_pct": 0.05},
    "volume_10": {"min_quantity": 10, "discount_pct": 0.10},
    "volume_25": {"min_quantity": 25, "discount_pct": 0.15},
    "volume_50": {"min_quantity": 50, "discount_pct": 0.20},
    "enterprise_base": {"category": "enterprise", "discount_pct": 0.10},
    "addon_bundle": {"category": "addon", "min_bundle_size": 2, "discount_pct": 0.15},
}


# ---------------------------------------------------------------------------
# Request/Response models — rigid, predefined schemas
# ---------------------------------------------------------------------------

class QuoteRequest(BaseModel):
    customer_id: str
    items: list[dict]  # [{"product_id": "...", "quantity": 1}]
    promo_code: Optional[str] = None


class QuoteResponse(BaseModel):
    quote_id: str
    customer_id: str
    line_items: list[dict]
    subtotal: float
    discount_total: float
    final_total: float
    generated_at: str


# ---------------------------------------------------------------------------
# Deterministic business logic
# ---------------------------------------------------------------------------

def calculate_volume_discount(quantity: int) -> float:
    """Apply volume discount based on rigid tier thresholds."""
    discount = 0.0
    for rule in DISCOUNT_RULES.values():
        if "min_quantity" in rule and quantity >= rule["min_quantity"]:
            discount = max(discount, rule["discount_pct"])
    return discount


def calculate_category_discount(product_id: str) -> float:
    """Apply category-based discount."""
    product = PRODUCTS.get(product_id)
    if not product:
        return 0.0
    category = product["category"]
    for rule in DISCOUNT_RULES.values():
        if rule.get("category") == category and "min_bundle_size" not in rule:
            return rule["discount_pct"]
    return 0.0


def apply_promo_code(code: str) -> float:
    """Hardcoded promo codes. This is where it gets ugly in production."""
    promos = {
        "SAVE10": 0.10,
        "WELCOME5": 0.05,
        "ENTERPRISE20": 0.20,
    }
    return promos.get(code, 0.0)


# ---------------------------------------------------------------------------
# Endpoints — procedure-oriented contracts
# ---------------------------------------------------------------------------

@app.get("/price/{product_id}")
def get_price(product_id: str):
    """Look up base price. No context. No reasoning. Just data retrieval."""
    product = PRODUCTS.get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
    return {
        "product_id": product_id,
        "name": product["name"],
        "base_price": product["base_price"],
        "currency": "USD",
    }


@app.get("/price/{product_id}/discount")
def get_discount(product_id: str, quantity: int = 1):
    """Calculate discounted price. Rigid rules. No negotiation."""
    product = PRODUCTS.get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")

    base = product["base_price"]
    vol_discount = calculate_volume_discount(quantity)
    cat_discount = calculate_category_discount(product_id)
    total_discount = min(vol_discount + cat_discount, 0.30)  # Hard cap at 30%

    final_price = round(base * (1 - total_discount), 2)

    return {
        "product_id": product_id,
        "base_price": base,
        "quantity": quantity,
        "volume_discount_pct": vol_discount,
        "category_discount_pct": cat_discount,
        "total_discount_pct": total_discount,
        "unit_price": final_price,
        "total_price": round(final_price * quantity, 2),
        "currency": "USD",
    }


@app.post("/quote", response_model=QuoteResponse)
def generate_quote(request: QuoteRequest):
    """
    Generate a quote. This is where the limitations show.

    What this CAN'T do:
    - Consider customer purchase history
    - Factor in competitor pricing
    - Reason about margin targets
    - Handle "give me your best price for everything" requests
    - Negotiate or explain pricing rationale
    - Suggest alternatives or bundles the customer didn't ask about
    """
    line_items = []
    subtotal = 0.0
    discount_total = 0.0

    for item in request.items:
        product = PRODUCTS.get(item["product_id"])
        if not product:
            raise HTTPException(
                status_code=404,
                detail=f"Product {item['product_id']} not found"
            )

        quantity = item.get("quantity", 1)
        base = product["base_price"]
        vol_discount = calculate_volume_discount(quantity)
        cat_discount = calculate_category_discount(item["product_id"])
        total_discount_pct = min(vol_discount + cat_discount, 0.30)

        # Apply promo code (stacks, but still capped)
        if request.promo_code:
            promo_discount = apply_promo_code(request.promo_code)
            total_discount_pct = min(total_discount_pct + promo_discount, 0.35)

        unit_price = round(base * (1 - total_discount_pct), 2)
        line_total = round(unit_price * quantity, 2)
        line_discount = round((base * quantity) - line_total, 2)

        line_items.append({
            "product_id": item["product_id"],
            "name": product["name"],
            "quantity": quantity,
            "base_price": base,
            "unit_price": unit_price,
            "line_total": line_total,
            "discount_applied_pct": total_discount_pct,
        })

        subtotal += base * quantity
        discount_total += line_discount

    final_total = round(subtotal - discount_total, 2)

    return QuoteResponse(
        quote_id=f"Q-{int(datetime.now().timestamp())}",
        customer_id=request.customer_id,
        line_items=line_items,
        subtotal=round(subtotal, 2),
        discount_total=round(discount_total, 2),
        final_total=final_total,
        generated_at=datetime.now().isoformat(),
    )


@app.get("/health")
def health():
    return {"status": "ok", "service": "PricingService", "version": "1.0.0"}
