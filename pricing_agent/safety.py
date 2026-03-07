"""
Layer 5: Safety Boundaries

This is the layer that lets you sleep at night.

An AgentService that reasons and decides also needs guardrails on
WHAT it can decide, HOW MUCH authority it has, and WHEN to escalate
to a human.

Without this layer, you have an autonomous agent with no limits.
With it, you have a useful agent you can actually deploy.

Safety boundaries are not an afterthought. They're a first-class
architectural layer, evaluated and tested with the same rigor
as the reasoning engine itself.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SafetyConfig:
    """Configuration for agent safety boundaries."""

    # Pricing limits
    max_discount_pct: float = 0.35          # Absolute maximum discount
    margin_floor_override: bool = False      # Can the agent go below margin floor?
    max_unit_price_authority: float = 500.0  # Above this, requires human approval

    # Reasoning limits
    max_reasoning_steps: int = 10            # Prevent infinite loops
    max_tool_calls: int = 15                 # Prevent runaway tool usage
    max_reasoning_time_seconds: int = 30     # Timeout for reasoning

    # Authority scope
    can_commit_quotes: bool = False          # Can agent finalize quotes?
    can_modify_base_prices: bool = False     # Can agent change rate tables?
    can_create_custom_promos: bool = False   # Can agent invent promo codes?
    can_contact_customer: bool = False       # Can agent send communications?

    # Escalation thresholds
    escalate_above_deal_value: float = 10000.0  # Auto-escalate large deals
    escalate_on_competitor_match: bool = True     # Human review for price matching
    escalate_new_customer: bool = False           # Extra review for new customers


# Default configuration — conservative
DEFAULT_SAFETY = SafetyConfig()


@dataclass
class SafetyCheckResult:
    """Result of a safety boundary check."""
    allowed: bool
    reason: Optional[str] = None
    requires_approval: bool = False
    approval_reason: Optional[str] = None
    modified_action: Optional[dict] = None  # If we adjusted the action to be safe


class SafetyBoundary:
    """
    Evaluates agent actions against safety boundaries.

    Called BEFORE any action is executed. The reasoning engine
    proposes an action, the safety layer approves, modifies,
    or blocks it.
    """

    def __init__(self, config: SafetyConfig = DEFAULT_SAFETY):
        self.config = config

    def check_discount(self, discount_pct: float, product_id: str = "") -> SafetyCheckResult:
        """Validate a proposed discount against limits."""
        if discount_pct > self.config.max_discount_pct:
            return SafetyCheckResult(
                allowed=False,
                reason=f"Discount {discount_pct:.0%} exceeds maximum allowed {self.config.max_discount_pct:.0%}",
                requires_approval=True,
                approval_reason=f"Discount of {discount_pct:.0%} on {product_id} requires manager approval",
                modified_action={"discount_pct": self.config.max_discount_pct},
            )
        return SafetyCheckResult(allowed=True)

    def check_margin(self, proposed_price: float, margin_floor: float) -> SafetyCheckResult:
        """Ensure proposed price doesn't violate margin floor."""
        if proposed_price < margin_floor and not self.config.margin_floor_override:
            return SafetyCheckResult(
                allowed=False,
                reason=f"Price ${proposed_price:.2f} is below margin floor ${margin_floor:.2f}",
                requires_approval=True,
                approval_reason="Below-floor pricing requires VP Sales approval",
                modified_action={"proposed_price": margin_floor},
            )
        return SafetyCheckResult(allowed=True)

    def check_deal_value(self, total_value: float) -> SafetyCheckResult:
        """Check if deal size requires escalation."""
        if total_value > self.config.escalate_above_deal_value:
            return SafetyCheckResult(
                allowed=True,  # Allow but flag
                requires_approval=True,
                approval_reason=f"Deal value ${total_value:,.2f} exceeds ${self.config.escalate_above_deal_value:,.2f} threshold",
            )
        return SafetyCheckResult(allowed=True)

    def check_reasoning_limits(self, steps: int, tool_calls: int) -> SafetyCheckResult:
        """Prevent runaway reasoning loops."""
        if steps > self.config.max_reasoning_steps:
            return SafetyCheckResult(
                allowed=False,
                reason=f"Reasoning exceeded {self.config.max_reasoning_steps} step limit. Possible loop detected.",
            )
        if tool_calls > self.config.max_tool_calls:
            return SafetyCheckResult(
                allowed=False,
                reason=f"Tool calls exceeded {self.config.max_tool_calls} call limit.",
            )
        return SafetyCheckResult(allowed=True)

    def check_authority(self, action: str) -> SafetyCheckResult:
        """Check if the agent has authority for a proposed action."""
        authority_map = {
            "commit_quote": self.config.can_commit_quotes,
            "modify_base_price": self.config.can_modify_base_prices,
            "create_promo": self.config.can_create_custom_promos,
            "contact_customer": self.config.can_contact_customer,
        }
        if action in authority_map and not authority_map[action]:
            return SafetyCheckResult(
                allowed=False,
                reason=f"Agent does not have authority for action: {action}",
                requires_approval=True,
                approval_reason=f"Action '{action}' requires human execution",
            )
        return SafetyCheckResult(allowed=True)

    def validate_response(self, response: dict) -> SafetyCheckResult:
        """
        Final validation before sending response to caller.

        This is the last line of defense. Even if the reasoning engine
        produces something unexpected, this catches it.
        """
        checks = []

        # Check recommended price against limits
        if "recommended_price" in response and "product_id" in response:
            from .tools import PRODUCTS
            product = PRODUCTS.get(response["product_id"], {})
            margin_floor = product.get("margin_floor", 0)
            checks.append(self.check_margin(response["recommended_price"], margin_floor))

        # Check discount
        if "discount_applied_pct" in response:
            checks.append(self.check_discount(response["discount_applied_pct"]))

        # Check deal value
        if "total_value" in response:
            checks.append(self.check_deal_value(response["total_value"]))

        # Aggregate results
        blocked = [c for c in checks if not c.allowed]
        needs_approval = [c for c in checks if c.requires_approval]

        if blocked:
            return SafetyCheckResult(
                allowed=False,
                reason="; ".join(c.reason for c in blocked if c.reason),
                requires_approval=True,
                approval_reason="; ".join(c.approval_reason for c in blocked if c.approval_reason),
            )

        if needs_approval:
            return SafetyCheckResult(
                allowed=True,
                requires_approval=True,
                approval_reason="; ".join(c.approval_reason for c in needs_approval if c.approval_reason),
            )

        return SafetyCheckResult(allowed=True)


# Default instance
safety = SafetyBoundary()
