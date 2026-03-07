"""
PricingAgent — The "After"

An AgentService. Goal-oriented. Context-aware. Reasoning-capable. Guardrailed.

This is the same pricing domain as the microservice, but fundamentally
re-architected. The business logic didn't change — the way it's
invoked, composed, and governed changed entirely.

Layers:
    1. Goal Interface    → POST /pricing/evaluate (this file)
    2. Reasoning Engine  → PricingAgent.reason() (this file)
    3. Tool Registry     → tools.py
    4. Domain Memory     → memory.py
    5. Safety Boundaries → safety.py
"""

import os
import json
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .tools import TOOL_DEFINITIONS, execute_tool
from .memory import memory
from .safety import safety, SafetyCheckResult

app = FastAPI(title="PricingAgent", version="2.0.0")


# ---------------------------------------------------------------------------
# Layer 1: Goal Interface — accepts outcomes, not just inputs
# ---------------------------------------------------------------------------

class PricingGoal(BaseModel):
    """
    Goal-oriented request. Compare this to the microservice's rigid
    QuoteRequest — here the caller describes WHAT they want, not
    HOW to compute it.
    """
    goal: str                          # Natural language goal
    customer_id: Optional[str] = None  # Optional context
    product_ids: list[str] = []        # Products being considered
    constraints: dict = {}             # Budget limits, timeline, etc.


class PricingResponse(BaseModel):
    """
    Response includes not just the answer, but the reasoning,
    tools used, confidence, and whether human approval is needed.
    """
    recommended_price: Optional[float] = None
    reasoning: str
    tools_used: list[str]
    confidence: float
    requires_approval: bool
    approval_reason: Optional[str] = None
    alternatives: list[dict] = []
    context_used: dict = {}
    trajectory: list[dict] = []  # Full reasoning trace


# ---------------------------------------------------------------------------
# Layer 2: Reasoning Engine
# ---------------------------------------------------------------------------

class PricingAgentEngine:
    """
    The reasoning engine. This is where the agent THINKS.

    In production, this wraps your LLM provider (OpenAI, Anthropic, etc.)
    with tool calling. Here we provide both:
      - A real LLM integration (when API key is available)
      - A rule-based fallback (for demo/testing without API key)

    The fallback demonstrates the PATTERN — the same tool registry,
    memory, and safety layers work regardless of the reasoning backend.
    """

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("MODEL_NAME", "gpt-4o")

    async def reason(self, goal: PricingGoal) -> PricingResponse:
        """
        Main reasoning loop.

        1. Gather context from domain memory
        2. Plan which tools to use
        3. Execute tools iteratively
        4. Synthesize recommendation
        5. Validate against safety boundaries
        """

        trajectory = []
        tools_used = []

        # Step 1: Gather context from memory (Layer 4)
        context = {}
        if goal.customer_id:
            context = memory.get_context_summary(goal.customer_id)
            trajectory.append({
                "step": "memory_lookup",
                "action": f"Retrieved context for customer {goal.customer_id}",
                "result": context,
            })

        # Step 2: Record this interaction in memory
        if goal.customer_id:
            memory.record_interaction(goal.customer_id, {
                "goal": goal.goal,
                "product_id": goal.product_ids[0] if goal.product_ids else None,
                "type": "pricing_inquiry",
            })

        # Step 3: Reason (LLM or fallback)
        if self.api_key:
            response = await self._reason_with_llm(goal, context, trajectory, tools_used)
        else:
            response = await self._reason_with_rules(goal, context, trajectory, tools_used)

        # Step 4: Safety validation (Layer 5)
        safety_check = safety.validate_response(response.model_dump())
        if safety_check.requires_approval:
            response.requires_approval = True
            response.approval_reason = safety_check.approval_reason
        if not safety_check.allowed:
            trajectory.append({
                "step": "safety_block",
                "action": "Safety boundary blocked the recommendation",
                "result": safety_check.reason,
            })
            response.reasoning += f" [SAFETY: {safety_check.reason}]"

        # Step 5: Log decision in memory
        memory.record_decision({
            "product_id": goal.product_ids[0] if goal.product_ids else None,
            "customer_id": goal.customer_id,
            "recommended_price": response.recommended_price,
            "confidence": response.confidence,
            "tools_used": tools_used,
        })

        response.trajectory = trajectory
        return response

    async def _reason_with_llm(
        self,
        goal: PricingGoal,
        context: dict,
        trajectory: list,
        tools_used: list,
    ) -> PricingResponse:
        """
        Real LLM-powered reasoning with tool calling.

        This is the production path. The LLM receives:
        - The goal (what the caller wants)
        - Domain context (from memory)
        - Available tools (from the registry)
        - Safety constraints (from the boundary layer)

        It then reasons through the problem, calling tools as needed,
        and synthesizes a recommendation.
        """
        try:
            import openai
            client = openai.AsyncOpenAI(api_key=self.api_key)
        except ImportError:
            return await self._reason_with_rules(goal, context, trajectory, tools_used)

        system_prompt = f"""You are a PricingAgent — an intelligent pricing service that reasons
about optimal pricing for customers. You have access to tools for looking up prices,
customer history, competitor data, margins, and bundles.

Your job is to:
1. Understand the pricing goal
2. Gather relevant data using your tools
3. Reason about the optimal price considering ALL factors
4. Recommend a price with clear justification

Current context from domain memory:
{json.dumps(context, indent=2)}

Safety constraints:
- Maximum discount: 35%
- Never go below margin floor
- Deals over $10,000 require human approval
- You cannot commit quotes or modify base prices

Always explain your reasoning clearly."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": goal.goal},
        ]

        # Convert our tool definitions to OpenAI format
        openai_tools = [
            {"type": "function", "function": t} for t in TOOL_DEFINITIONS
        ]

        # Reasoning loop with tool calling
        step_count = 0
        max_steps = 10

        while step_count < max_steps:
            step_count += 1

            # Safety check on reasoning steps
            step_check = safety.check_reasoning_limits(step_count, len(tools_used))
            if not step_check.allowed:
                trajectory.append({"step": "safety_halt", "reason": step_check.reason})
                break

            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=openai_tools,
                tool_choice="auto",
            )

            message = response.choices[0].message

            if message.tool_calls:
                messages.append(message)
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)

                    # Execute tool
                    result = execute_tool(tool_name, tool_args)
                    tools_used.append(tool_name)

                    trajectory.append({
                        "step": f"tool_call_{step_count}",
                        "tool": tool_name,
                        "arguments": tool_args,
                        "result": result,
                    })

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result),
                    })
            else:
                # Agent has finished reasoning
                reasoning_text = message.content or ""
                trajectory.append({
                    "step": "final_reasoning",
                    "content": reasoning_text,
                })
                break

        # Extract price from the LLM response (or parse structured output)
        recommended_price = self._extract_price_from_reasoning(
            reasoning_text, goal.product_ids
        )

        return PricingResponse(
            recommended_price=recommended_price,
            reasoning=reasoning_text,
            tools_used=list(set(tools_used)),
            confidence=0.85,
            requires_approval=False,
            context_used=context,
        )

    async def _reason_with_rules(
        self,
        goal: PricingGoal,
        context: dict,
        trajectory: list,
        tools_used: list,
    ) -> PricingResponse:
        """
        Rule-based fallback reasoning (no LLM required).

        This demonstrates the PATTERN of an AgentService even without
        an LLM backend. The same tools, memory, and safety layers
        are used — the reasoning is just simpler.

        In production, you'd never ship this. But for understanding
        the architecture, it shows that the value of an AgentService
        isn't just "add an LLM" — it's the entire 5-layer structure.
        """
        reasoning_parts = []
        recommended_price = None
        alternatives = []

        # Gather data using tools (same tools the LLM would use)
        for product_id in goal.product_ids:
            # Tool 1: Base price
            price_data = execute_tool("get_base_price", {"product_id": product_id})
            tools_used.append("get_base_price")
            trajectory.append({
                "step": "get_base_price",
                "tool": "get_base_price",
                "result": price_data,
            })

            if "error" in price_data:
                continue

            base_price = price_data["base_price"]
            margin_floor = price_data["margin_floor"]
            reasoning_parts.append(f"Base price for {product_id}: ${base_price}")

            # Tool 2: Customer history
            discount_pct = 0.0
            if goal.customer_id:
                customer_data = execute_tool(
                    "get_customer_history", {"customer_id": goal.customer_id}
                )
                tools_used.append("get_customer_history")
                trajectory.append({
                    "step": "get_customer_history",
                    "tool": "get_customer_history",
                    "result": customer_data,
                })

                # Reason about loyalty discount
                loyalty_tier = customer_data.get("loyalty_tier", "None")
                if loyalty_tier == "Gold":
                    discount_pct += 0.10
                    reasoning_parts.append(
                        f"Customer is {loyalty_tier} tier: applying 10% loyalty discount"
                    )
                elif loyalty_tier == "None" and customer_data.get("churn_risk") == "high":
                    discount_pct += 0.08
                    reasoning_parts.append(
                        "Customer has high churn risk: applying 8% retention discount"
                    )

            # Tool 3: Competitor pricing
            competitor_data = execute_tool(
                "get_competitor_pricing", {"product_id": product_id}
            )
            tools_used.append("get_competitor_pricing")
            trajectory.append({
                "step": "get_competitor_pricing",
                "tool": "get_competitor_pricing",
                "result": competitor_data,
            })

            lowest_competitor = competitor_data.get("lowest_competitor_price")
            if lowest_competitor and lowest_competitor < base_price:
                competitive_discount = min(
                    (base_price - lowest_competitor) / base_price * 0.5, 0.10
                )
                discount_pct += competitive_discount
                reasoning_parts.append(
                    f"Competitor pricing at ${lowest_competitor}: adding {competitive_discount:.0%} competitive adjustment"
                )

            # Tool 4: Margin check
            proposed = round(base_price * (1 - discount_pct), 2)

            # Safety: enforce margin floor
            margin_check = safety.check_margin(proposed, margin_floor)
            if not margin_check.allowed:
                proposed = margin_floor
                reasoning_parts.append(
                    f"Adjusted to margin floor ${margin_floor} (safety boundary)"
                )

            # Safety: enforce max discount
            discount_check = safety.check_discount(discount_pct, product_id)
            if not discount_check.allowed:
                discount_pct = discount_check.modified_action["discount_pct"]
                proposed = round(base_price * (1 - discount_pct), 2)
                reasoning_parts.append(
                    f"Discount capped at {discount_pct:.0%} (safety boundary)"
                )

            margin_data = execute_tool(
                "calculate_margin",
                {"product_id": product_id, "proposed_price": proposed},
            )
            tools_used.append("calculate_margin")
            trajectory.append({
                "step": "calculate_margin",
                "tool": "calculate_margin",
                "result": margin_data,
            })
            reasoning_parts.append(
                f"Final margin: {margin_data.get('margin_pct', 0)}% (${margin_data.get('margin_dollars', 0)})"
            )

            recommended_price = proposed

            # Tool 5: Bundle suggestions
            bundle_data = execute_tool("suggest_bundles", {"product_id": product_id})
            tools_used.append("suggest_bundles")
            trajectory.append({
                "step": "suggest_bundles",
                "tool": "suggest_bundles",
                "result": bundle_data,
            })

            if bundle_data.get("suggested"):
                bundle_items = bundle_data["suggested"]
                bundle_discount = bundle_data["bundle_discount"]
                alternatives.append({
                    "type": "bundle",
                    "products": [product_id] + bundle_items,
                    "bundle_discount": bundle_discount,
                    "rationale": bundle_data.get("rationale", ""),
                })
                reasoning_parts.append(
                    f"Bundle opportunity: {bundle_items} with {bundle_discount:.0%} bundle discount"
                )

        reasoning = ". ".join(reasoning_parts) + "."

        return PricingResponse(
            recommended_price=recommended_price,
            reasoning=reasoning,
            tools_used=list(set(tools_used)),
            confidence=0.75 if not goal.customer_id else 0.85,
            requires_approval=False,
            alternatives=alternatives,
            context_used=context,
        )

    def _extract_price_from_reasoning(
        self, reasoning: str, product_ids: list[str]
    ) -> Optional[float]:
        """Extract a numeric price from LLM reasoning text."""
        import re
        # Look for patterns like "$84.99" or "recommend 84.99"
        prices = re.findall(r'\$(\d+\.?\d*)', reasoning)
        if prices:
            return float(prices[-1])  # Take the last mentioned price
        return None


# ---------------------------------------------------------------------------
# Singleton engine
# ---------------------------------------------------------------------------
engine = PricingAgentEngine()


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.post("/pricing/evaluate", response_model=PricingResponse)
async def evaluate_pricing(goal: PricingGoal):
    """
    Layer 1: Goal Interface

    Compare this to the microservice's GET /price/{product_id}.
    Same domain. Fundamentally different contract.

    The caller describes WHAT they want. The agent figures out HOW.
    """
    if not goal.product_ids and not goal.goal:
        raise HTTPException(status_code=400, detail="Provide a goal or product IDs")

    return await engine.reason(goal)


# Backward compatibility — the old microservice endpoints still work
@app.get("/price/{product_id}")
def get_price_legacy(product_id: str):
    """Legacy endpoint. Same as the microservice. Still works."""
    from .tools import get_base_price
    result = get_base_price(product_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return {
        "product_id": product_id,
        "name": result["name"],
        "base_price": result["base_price"],
        "currency": "USD",
        "_notice": "This is a legacy endpoint. Use POST /pricing/evaluate for goal-oriented pricing.",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "PricingAgent",
        "version": "2.0.0",
        "type": "AgentService",
        "layers": {
            "goal_interface": "active",
            "reasoning_engine": "llm" if engine.api_key else "rule-based-fallback",
            "tool_registry": f"{len(TOOL_DEFINITIONS)} tools registered",
            "domain_memory": "active",
            "safety_boundaries": "active",
        },
    }
