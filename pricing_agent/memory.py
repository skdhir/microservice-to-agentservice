"""
Layer 4: Domain Memory

This is what makes an AgentService fundamentally different from a
stateless microservice. The agent remembers.

Not session state. Not cache. Domain memory — operational context
that informs reasoning across interactions.

The PricingAgent remembers that customer C-1234 asked about three
configurations in the last hour. It knows that last quarter's
enterprise deals averaged 18% discount. It recalls that aggressive
pricing on WIDGET-PRO led to margin compression in Q2.

In production, this would be backed by Redis, a vector database,
or a purpose-built memory store. Here we use an in-memory
implementation to demonstrate the pattern.
"""

from datetime import datetime, timedelta
from typing import Any, Optional
from collections import defaultdict


class DomainMemory:
    """
    In-memory implementation of domain memory for the PricingAgent.

    In production, swap this for Redis, Postgres, or a vector DB.
    The interface stays the same — the agent doesn't care about
    the storage backend.
    """

    def __init__(self):
        # Customer interaction history (short-term)
        self._interactions: dict[str, list[dict]] = defaultdict(list)

        # Pricing decisions log (medium-term)
        self._decisions: list[dict] = []

        # Domain patterns (long-term, would be periodically computed)
        self._patterns: dict[str, Any] = {
            "avg_enterprise_discount": 0.18,
            "avg_deal_cycle_days": 14,
            "top_bundle_attachment_rate": 0.35,
            "seasonal_demand": {"Q1": "low", "Q2": "medium", "Q3": "high", "Q4": "high"},
        }

    def record_interaction(self, customer_id: str, interaction: dict) -> None:
        """Record a customer interaction for context in future reasoning."""
        self._interactions[customer_id].append({
            **interaction,
            "timestamp": datetime.now().isoformat(),
        })

    def get_recent_interactions(
        self, customer_id: str, hours: int = 24
    ) -> list[dict]:
        """Get recent interactions with a customer."""
        cutoff = datetime.now() - timedelta(hours=hours)
        return [
            i for i in self._interactions.get(customer_id, [])
            if datetime.fromisoformat(i["timestamp"]) > cutoff
        ]

    def record_decision(self, decision: dict) -> None:
        """Log a pricing decision for pattern analysis."""
        self._decisions.append({
            **decision,
            "timestamp": datetime.now().isoformat(),
        })

    def get_similar_decisions(
        self, product_id: str, customer_tier: Optional[str] = None, limit: int = 5
    ) -> list[dict]:
        """
        Find similar past pricing decisions.

        In production with a vector DB, this would be semantic similarity
        search over decision embeddings. Here we filter on product and tier.
        """
        matches = [
            d for d in self._decisions
            if d.get("product_id") == product_id
            and (customer_tier is None or d.get("customer_tier") == customer_tier)
        ]
        return matches[-limit:]

    def get_domain_pattern(self, pattern_key: str) -> Any:
        """Retrieve a domain-level pattern or insight."""
        return self._patterns.get(pattern_key)

    def get_context_summary(self, customer_id: str) -> dict[str, Any]:
        """
        Build a context summary the reasoning engine can use.
        This is what gets injected into the LLM prompt.
        """
        recent = self.get_recent_interactions(customer_id, hours=24)
        return {
            "customer_id": customer_id,
            "recent_interaction_count": len(recent),
            "recent_products_discussed": list(set(
                i.get("product_id") for i in recent if i.get("product_id")
            )),
            "recent_goals": [i.get("goal", "") for i in recent[-3:]],
            "domain_patterns": {
                "current_quarter_demand": self._patterns.get("seasonal_demand", {}).get("Q1", "unknown"),
                "avg_enterprise_discount": self._patterns.get("avg_enterprise_discount"),
                "bundle_attachment_rate": self._patterns.get("top_bundle_attachment_rate"),
            },
        }


# Singleton instance (in production: inject via dependency)
memory = DomainMemory()
