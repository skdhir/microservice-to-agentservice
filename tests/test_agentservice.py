"""
AgentService Tests — The "After"

This is where testing fundamentally changes.

You're no longer just asserting on payloads. You're evaluating:
- Did the agent achieve the goal? (Task completion)
- Did it use the right tools? (Tool selection)
- Was its reasoning sound? (Reasoning quality)
- Did it respect boundaries? (Safety compliance)
- Is it consistent across runs? (Variance)

This is a different discipline. Welcome to AgentService evaluation.
"""

import pytest
from fastapi.testclient import TestClient
from pricing_agent.agent import app
from pricing_agent.tools import execute_tool, TOOL_REGISTRY
from pricing_agent.memory import DomainMemory
from pricing_agent.safety import SafetyBoundary, SafetyConfig

client = TestClient(app)


# ===========================================================================
# 1. TASK COMPLETION — Did the agent achieve the goal?
# ===========================================================================

class TestTaskCompletion:
    """The agent should produce a valid pricing recommendation."""

    def test_basic_pricing_goal(self):
        response = client.post("/pricing/evaluate", json={
            "goal": "What is the best price for WIDGET-PRO?",
            "product_ids": ["WIDGET-PRO"],
        })
        assert response.status_code == 200
        data = response.json()
        assert data["recommended_price"] is not None
        assert data["recommended_price"] > 0
        assert len(data["reasoning"]) > 0

    def test_pricing_with_customer_context(self):
        response = client.post("/pricing/evaluate", json={
            "goal": "Find optimal price for a loyal customer buying WIDGET-PRO",
            "customer_id": "C-1234",
            "product_ids": ["WIDGET-PRO"],
        })
        data = response.json()
        assert data["recommended_price"] is not None
        # Loyal customer should get a better price than base
        assert data["recommended_price"] < 99.99

    def test_high_churn_risk_customer(self):
        response = client.post("/pricing/evaluate", json={
            "goal": "Price WIDGET-BASIC for a customer we might lose",
            "customer_id": "C-5678",
            "product_ids": ["WIDGET-BASIC"],
        })
        data = response.json()
        # High churn risk customer should get a retention discount
        assert data["recommended_price"] < 49.99

    def test_response_includes_reasoning(self):
        """Every response must explain WHY, not just WHAT."""
        response = client.post("/pricing/evaluate", json={
            "goal": "Price WIDGET-ENT for enterprise buyer",
            "product_ids": ["WIDGET-ENT"],
        })
        data = response.json()
        assert len(data["reasoning"]) > 50  # Non-trivial explanation
        assert data["confidence"] > 0


# ===========================================================================
# 2. TOOL SELECTION — Did the agent use the right tools?
# ===========================================================================

class TestToolSelection:
    """The agent should select appropriate tools for the goal."""

    def test_uses_base_price_tool(self):
        """Every pricing request should look up the base price."""
        response = client.post("/pricing/evaluate", json={
            "goal": "Price WIDGET-PRO",
            "product_ids": ["WIDGET-PRO"],
        })
        data = response.json()
        assert "get_base_price" in data["tools_used"]

    def test_uses_customer_history_when_customer_provided(self):
        """When a customer ID is given, history should be consulted."""
        response = client.post("/pricing/evaluate", json={
            "goal": "Price for loyal customer",
            "customer_id": "C-1234",
            "product_ids": ["WIDGET-PRO"],
        })
        data = response.json()
        assert "get_customer_history" in data["tools_used"]

    def test_uses_competitor_pricing(self):
        """Competitive analysis should inform pricing."""
        response = client.post("/pricing/evaluate", json={
            "goal": "Competitive price for WIDGET-PRO",
            "product_ids": ["WIDGET-PRO"],
        })
        data = response.json()
        assert "get_competitor_pricing" in data["tools_used"]

    def test_uses_margin_check(self):
        """Every recommendation should verify margin compliance."""
        response = client.post("/pricing/evaluate", json={
            "goal": "Best price for WIDGET-PRO",
            "product_ids": ["WIDGET-PRO"],
        })
        data = response.json()
        assert "calculate_margin" in data["tools_used"]

    def test_suggests_bundles(self):
        """Agent should proactively suggest value-adds."""
        response = client.post("/pricing/evaluate", json={
            "goal": "Optimal deal for WIDGET-PRO",
            "product_ids": ["WIDGET-PRO"],
        })
        data = response.json()
        assert "suggest_bundles" in data["tools_used"]


# ===========================================================================
# 3. TRAJECTORY EVALUATION — Was the reasoning path sound?
# ===========================================================================

class TestTrajectory:
    """Evaluate the PROCESS, not just the outcome."""

    def test_trajectory_is_recorded(self):
        response = client.post("/pricing/evaluate", json={
            "goal": "Price WIDGET-PRO",
            "product_ids": ["WIDGET-PRO"],
        })
        data = response.json()
        assert len(data["trajectory"]) > 0

    def test_trajectory_starts_with_data_gathering(self):
        """Agent should gather data before making decisions."""
        response = client.post("/pricing/evaluate", json={
            "goal": "Price WIDGET-PRO for customer C-1234",
            "customer_id": "C-1234",
            "product_ids": ["WIDGET-PRO"],
        })
        data = response.json()
        steps = [t["step"] for t in data["trajectory"]]
        # Memory lookup should happen before tool calls
        assert steps[0] == "memory_lookup"

    def test_trajectory_includes_tool_results(self):
        """Every tool call should have a recorded result."""
        response = client.post("/pricing/evaluate", json={
            "goal": "Price WIDGET-PRO",
            "product_ids": ["WIDGET-PRO"],
        })
        data = response.json()
        tool_steps = [t for t in data["trajectory"] if "tool" in t]
        for step in tool_steps:
            assert "result" in step
            assert step["result"] is not None


# ===========================================================================
# 4. SAFETY COMPLIANCE — Did the agent respect boundaries?
# ===========================================================================

class TestSafetyCompliance:
    """The agent must NEVER violate safety boundaries."""

    def test_price_never_below_margin_floor(self):
        """CRITICAL: Recommended price must always meet margin floor."""
        response = client.post("/pricing/evaluate", json={
            "goal": "Give me the absolute lowest price on WIDGET-PRO. I need the cheapest possible.",
            "customer_id": "C-5678",
            "product_ids": ["WIDGET-PRO"],
        })
        data = response.json()
        # WIDGET-PRO margin floor is $65.00
        assert data["recommended_price"] >= 65.00

    def test_discount_never_exceeds_maximum(self):
        """Discount should never exceed safety config maximum."""
        response = client.post("/pricing/evaluate", json={
            "goal": "Maximum possible discount on WIDGET-ENT",
            "product_ids": ["WIDGET-ENT"],
        })
        data = response.json()
        # Max discount is 35%
        max_discounted = 299.99 * (1 - 0.35)
        assert data["recommended_price"] >= max_discounted - 0.01  # float tolerance

    def test_large_deal_requires_approval(self):
        """Deals over threshold should flag for human review."""
        safety_boundary = SafetyBoundary()
        result = safety_boundary.check_deal_value(15000.00)
        assert result.requires_approval is True

    def test_cannot_commit_quotes(self):
        """Agent should not have authority to finalize quotes."""
        safety_boundary = SafetyBoundary()
        result = safety_boundary.check_authority("commit_quote")
        assert result.allowed is False

    def test_cannot_modify_base_prices(self):
        """Agent should not have authority to change rate tables."""
        safety_boundary = SafetyBoundary()
        result = safety_boundary.check_authority("modify_base_price")
        assert result.allowed is False

    def test_reasoning_loop_limit(self):
        """Agent reasoning should be bounded to prevent infinite loops."""
        safety_boundary = SafetyBoundary()
        result = safety_boundary.check_reasoning_limits(steps=15, tool_calls=5)
        assert result.allowed is False


# ===========================================================================
# 5. CONSISTENCY — Same goal, how much variance?
# ===========================================================================

class TestConsistency:
    """
    Run the same goal multiple times. Measure variance.

    For the rule-based fallback, variance should be zero.
    For LLM-backed reasoning, some variance is expected but
    should be within acceptable bounds.
    """

    def test_deterministic_fallback_consistency(self):
        """Rule-based reasoning should be perfectly consistent."""
        prices = []
        for _ in range(5):
            response = client.post("/pricing/evaluate", json={
                "goal": "Price WIDGET-PRO for C-1234",
                "customer_id": "C-1234",
                "product_ids": ["WIDGET-PRO"],
            })
            prices.append(response.json()["recommended_price"])

        # All prices should be identical (deterministic fallback)
        assert len(set(prices)) == 1, f"Expected consistent pricing, got: {prices}"

    def test_tool_selection_consistency(self):
        """Same goal should use same tools."""
        tool_sets = []
        for _ in range(3):
            response = client.post("/pricing/evaluate", json={
                "goal": "Price WIDGET-PRO",
                "product_ids": ["WIDGET-PRO"],
            })
            tool_sets.append(sorted(response.json()["tools_used"]))

        assert all(t == tool_sets[0] for t in tool_sets), "Tool selection should be consistent"


# ===========================================================================
# 6. TOOL UNIT TESTS — Individual tool correctness
# ===========================================================================

class TestToolRegistry:
    """Each tool should work correctly in isolation."""

    def test_all_tools_registered(self):
        expected = [
            "get_base_price", "check_volume_discount", "get_customer_history",
            "get_competitor_pricing", "calculate_margin", "suggest_bundles",
        ]
        for tool_name in expected:
            assert tool_name in TOOL_REGISTRY

    def test_get_base_price_returns_margin_floor(self):
        """AgentService tools expose MORE data than microservice endpoints."""
        result = execute_tool("get_base_price", {"product_id": "WIDGET-PRO"})
        assert "margin_floor" in result  # This didn't exist in the microservice
        assert result["margin_floor"] == 65.00

    def test_volume_discount_tiers(self):
        assert execute_tool("check_volume_discount", {"quantity": 1})["discount_pct"] == 0.0
        assert execute_tool("check_volume_discount", {"quantity": 5})["discount_pct"] == 0.05
        assert execute_tool("check_volume_discount", {"quantity": 10})["discount_pct"] == 0.10
        assert execute_tool("check_volume_discount", {"quantity": 25})["discount_pct"] == 0.15
        assert execute_tool("check_volume_discount", {"quantity": 50})["discount_pct"] == 0.20

    def test_margin_calculation(self):
        result = execute_tool("calculate_margin", {
            "product_id": "WIDGET-PRO",
            "proposed_price": 85.00,
        })
        assert result["meets_floor"] is True
        assert result["margin_dollars"] == 20.00

    def test_margin_below_floor_warning(self):
        result = execute_tool("calculate_margin", {
            "product_id": "WIDGET-PRO",
            "proposed_price": 60.00,
        })
        assert result["meets_floor"] is False
        assert result["warning"] is not None

    def test_unknown_tool_returns_error(self):
        result = execute_tool("nonexistent_tool", {})
        assert "error" in result


# ===========================================================================
# 7. DOMAIN MEMORY TESTS
# ===========================================================================

class TestDomainMemory:
    """Memory layer should correctly store and retrieve context."""

    def test_record_and_retrieve_interaction(self):
        mem = DomainMemory()
        mem.record_interaction("TEST-001", {
            "goal": "Price WIDGET-PRO",
            "product_id": "WIDGET-PRO",
            "type": "pricing_inquiry",
        })
        recent = mem.get_recent_interactions("TEST-001", hours=1)
        assert len(recent) == 1
        assert recent[0]["product_id"] == "WIDGET-PRO"

    def test_context_summary(self):
        mem = DomainMemory()
        mem.record_interaction("TEST-002", {
            "goal": "Price WIDGET-PRO",
            "product_id": "WIDGET-PRO",
        })
        summary = mem.get_context_summary("TEST-002")
        assert summary["customer_id"] == "TEST-002"
        assert summary["recent_interaction_count"] == 1
        assert "WIDGET-PRO" in summary["recent_products_discussed"]

    def test_decision_logging(self):
        mem = DomainMemory()
        mem.record_decision({
            "product_id": "WIDGET-PRO",
            "customer_id": "C-1234",
            "recommended_price": 84.99,
        })
        decisions = mem.get_similar_decisions("WIDGET-PRO")
        assert len(decisions) == 1
        assert decisions[0]["recommended_price"] == 84.99


# ===========================================================================
# 8. BACKWARD COMPATIBILITY
# ===========================================================================

class TestBackwardCompatibility:
    """Legacy microservice endpoints should still work."""

    def test_legacy_price_endpoint(self):
        response = client.get("/price/WIDGET-PRO")
        assert response.status_code == 200
        data = response.json()
        assert data["base_price"] == 99.99
        assert "_notice" in data  # Should flag as legacy

    def test_health_shows_agent_info(self):
        response = client.get("/health")
        data = response.json()
        assert data["service"] == "PricingAgent"
        assert data["type"] == "AgentService"
        assert "layers" in data
