"""
Layer 3: Tool Registry

This is where the migration gets interesting. The business logic from the
microservice doesn't get rewritten — it gets WRAPPED as callable tools.

Same discount rules. Same rate tables. Same calculations. But now the
reasoning engine decides WHICH tools to use and HOW to combine them,
rather than following a hardcoded execution path.

This is why the migration isn't a rewrite. It's a re-architecture.
"""

from typing import Any

# ---------------------------------------------------------------------------
# Same data as the microservice (in production: same database)
# ---------------------------------------------------------------------------

PRODUCTS = {
    "WIDGET-PRO": {"name": "Widget Pro", "base_price": 99.99, "category": "premium", "margin_floor": 65.00},
    "WIDGET-BASIC": {"name": "Widget Basic", "base_price": 49.99, "category": "standard", "margin_floor": 30.00},
    "WIDGET-ENT": {"name": "Widget Enterprise", "base_price": 299.99, "category": "enterprise", "margin_floor": 180.00},
    "ADDON-SUPPORT": {"name": "Premium Support", "base_price": 29.99, "category": "addon", "margin_floor": 15.00},
    "ADDON-ANALYTICS": {"name": "Analytics Pack", "base_price": 19.99, "category": "addon", "margin_floor": 10.00},
}

COMPETITOR_PRICING = {
    "WIDGET-PRO": {"competitor_a": 94.99, "competitor_b": 89.99, "competitor_c": 109.99},
    "WIDGET-BASIC": {"competitor_a": 44.99, "competitor_b": 52.99, "competitor_c": 47.99},
    "WIDGET-ENT": {"competitor_a": 279.99, "competitor_b": 319.99, "competitor_c": 289.99},
}


# ---------------------------------------------------------------------------
# Tool definitions — each tool is a dict the LLM can understand and invoke
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "name": "get_base_price",
        "description": "Look up the base price and product details for a given product ID. Returns price, category, and margin floor.",
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "The product identifier (e.g., WIDGET-PRO)"}
            },
            "required": ["product_id"],
        },
    },
    {
        "name": "check_volume_discount",
        "description": "Calculate the volume discount percentage based on order quantity. Higher quantities get larger discounts.",
        "parameters": {
            "type": "object",
            "properties": {
                "quantity": {"type": "integer", "description": "Number of units being ordered"}
            },
            "required": ["quantity"],
        },
    },
    {
        "name": "get_customer_history",
        "description": "Retrieve a customer's purchase history including total spend, order count, loyalty tier, and recent purchases. Use this to inform loyalty discounts and personalized pricing.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "The customer identifier"}
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "get_competitor_pricing",
        "description": "Look up competitor prices for a product. Use this when the customer mentions competitors or when optimizing for retention.",
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "The product identifier"}
            },
            "required": ["product_id"],
        },
    },
    {
        "name": "calculate_margin",
        "description": "Calculate the profit margin for a proposed price. Returns margin percentage and whether it meets the margin floor.",
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "The product identifier"},
                "proposed_price": {"type": "number", "description": "The price to evaluate"},
            },
            "required": ["product_id", "proposed_price"],
        },
    },
    {
        "name": "suggest_bundles",
        "description": "Suggest product bundles that complement the given product. Use this to increase deal size and provide customer value.",
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "The primary product being considered"}
            },
            "required": ["product_id"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool implementations — same logic, now invocable by the reasoning engine
# ---------------------------------------------------------------------------

def get_base_price(product_id: str) -> dict[str, Any]:
    product = PRODUCTS.get(product_id)
    if not product:
        return {"error": f"Product {product_id} not found"}
    return {
        "product_id": product_id,
        "name": product["name"],
        "base_price": product["base_price"],
        "category": product["category"],
        "margin_floor": product["margin_floor"],
    }


def check_volume_discount(quantity: int) -> dict[str, Any]:
    tiers = [
        (50, 0.20, "Platinum"),
        (25, 0.15, "Gold"),
        (10, 0.10, "Silver"),
        (5, 0.05, "Bronze"),
    ]
    for min_qty, discount, tier in tiers:
        if quantity >= min_qty:
            return {
                "quantity": quantity,
                "discount_pct": discount,
                "tier": tier,
                "next_tier": None if tier == "Platinum" else f"Order {tiers[tiers.index((min_qty, discount, tier)) - 1][0]}+ for {tiers[tiers.index((min_qty, discount, tier)) - 1][2]} tier",
            }
    return {
        "quantity": quantity,
        "discount_pct": 0.0,
        "tier": "None",
        "next_tier": "Order 5+ for Bronze tier (5% discount)",
    }


def get_customer_history(customer_id: str) -> dict[str, Any]:
    """
    In production, this queries your CRM/database.
    Simulated here to demonstrate the pattern.
    """
    mock_customers = {
        "C-1234": {
            "customer_id": "C-1234",
            "name": "Acme Corp",
            "total_spend": 12450.00,
            "order_count": 15,
            "loyalty_tier": "Gold",
            "last_purchase": "2026-02-15",
            "products_purchased": ["WIDGET-PRO", "WIDGET-ENT", "ADDON-SUPPORT"],
            "avg_order_value": 830.00,
            "churn_risk": "low",
        },
        "C-5678": {
            "customer_id": "C-5678",
            "name": "Startup Inc",
            "total_spend": 499.90,
            "order_count": 2,
            "loyalty_tier": "None",
            "last_purchase": "2026-01-03",
            "products_purchased": ["WIDGET-BASIC"],
            "avg_order_value": 249.95,
            "churn_risk": "high",
        },
    }
    customer = mock_customers.get(customer_id)
    if not customer:
        return {"customer_id": customer_id, "status": "new_customer", "total_spend": 0, "order_count": 0}
    return customer


def get_competitor_pricing(product_id: str) -> dict[str, Any]:
    pricing = COMPETITOR_PRICING.get(product_id)
    if not pricing:
        return {"product_id": product_id, "competitors": {}, "note": "No competitor data available"}
    avg_price = round(sum(pricing.values()) / len(pricing), 2)
    min_price = min(pricing.values())
    return {
        "product_id": product_id,
        "competitors": pricing,
        "average_competitor_price": avg_price,
        "lowest_competitor_price": min_price,
    }


def calculate_margin(product_id: str, proposed_price: float) -> dict[str, Any]:
    product = PRODUCTS.get(product_id)
    if not product:
        return {"error": f"Product {product_id} not found"}
    margin_floor = product["margin_floor"]
    margin = round(proposed_price - margin_floor, 2)
    margin_pct = round((margin / proposed_price) * 100, 1) if proposed_price > 0 else 0
    return {
        "product_id": product_id,
        "proposed_price": proposed_price,
        "margin_floor": margin_floor,
        "margin_dollars": margin,
        "margin_pct": margin_pct,
        "meets_floor": proposed_price >= margin_floor,
        "warning": None if proposed_price >= margin_floor else f"Price ${proposed_price} is below margin floor ${margin_floor}",
    }


def suggest_bundles(product_id: str) -> dict[str, Any]:
    bundles = {
        "WIDGET-PRO": {
            "suggested": ["ADDON-SUPPORT", "ADDON-ANALYTICS"],
            "bundle_discount": 0.15,
            "rationale": "Pro users see 40% more value with analytics and dedicated support",
        },
        "WIDGET-BASIC": {
            "suggested": ["ADDON-ANALYTICS"],
            "bundle_discount": 0.10,
            "rationale": "Analytics pack helps Basic users identify upgrade opportunities",
        },
        "WIDGET-ENT": {
            "suggested": ["ADDON-SUPPORT", "ADDON-ANALYTICS"],
            "bundle_discount": 0.20,
            "rationale": "Enterprise customers expect full-stack solutions",
        },
    }
    bundle = bundles.get(product_id, {"suggested": [], "bundle_discount": 0, "rationale": "No bundles available"})
    return {"product_id": product_id, **bundle}


# ---------------------------------------------------------------------------
# Tool dispatcher — maps tool names to implementations
# ---------------------------------------------------------------------------

TOOL_REGISTRY = {
    "get_base_price": get_base_price,
    "check_volume_discount": check_volume_discount,
    "get_customer_history": get_customer_history,
    "get_competitor_pricing": get_competitor_pricing,
    "calculate_margin": calculate_margin,
    "suggest_bundles": suggest_bundles,
}


def execute_tool(tool_name: str, arguments: dict) -> dict[str, Any]:
    """Execute a tool by name with given arguments. Used by the reasoning engine."""
    tool_fn = TOOL_REGISTRY.get(tool_name)
    if not tool_fn:
        return {"error": f"Unknown tool: {tool_name}"}
    try:
        return tool_fn(**arguments)
    except Exception as e:
        return {"error": f"Tool execution failed: {str(e)}"}
