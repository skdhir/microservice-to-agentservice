# Technical Design: microservice-to-agentservice

## Context

Read `PRD.md` first for full scope and requirements. This document specifies HOW to build it.

## Architecture Overview

```
microservice-to-agentservice/
├── pricing_service/              # THE "BEFORE"
│   ├── __init__.py
│   └── app.py                    # Complete microservice (single file)
│
├── pricing_agent/                # THE "AFTER"
│   ├── __init__.py
│   ├── agent.py                  # Layer 1 (Goal Interface) + Layer 2 (Reasoning Engine)
│   ├── tools.py                  # Layer 3 (Tool Registry)
│   ├── memory.py                 # Layer 4 (Domain Memory)
│   └── safety.py                 # Layer 5 (Safety Boundaries)
│
├── tests/
│   ├── __init__.py
│   ├── test_microservice.py      # Traditional payload assertion tests
│   └── test_agentservice.py      # Trajectory, safety, consistency evals
│
├── README.md
├── PRD.md                        # This project's requirements
├── TECH_DESIGN.md                # This document
├── requirements.txt
├── .gitignore
└── LICENSE
```

## Tech Stack

- Python 3.11+
- FastAPI (both services)
- Pydantic v2 (request/response models)
- pytest + httpx (testing via TestClient)
- openai SDK (optional, for LLM reasoning path)
- No database. All data is in-memory dicts and lists.

## File-by-File Specification

---

### `pricing_service/app.py` — The Microservice

**Purpose:** Demonstrate a clean, typical microservice. This is the baseline that readers compare against.

**Design principles:**
- Single file. No abstractions. No cleverness.
- Deterministic: same input always produces same output
- Stateless: no memory of previous requests
- Rigid contracts: fixed request/response schemas

**Endpoints:**

1. `GET /price/{product_id}`
   - Input: product_id (path param)
   - Output: `{ product_id, name, base_price, currency }`
   - Logic: Dict lookup. 404 if not found.

2. `GET /price/{product_id}/discount`
   - Input: product_id (path), quantity (query, default 1)
   - Output: `{ product_id, base_price, quantity, volume_discount_pct, category_discount_pct, total_discount_pct, unit_price, total_price, currency }`
   - Logic: Calculate volume discount (tier lookup), category discount (enterprise gets 10%), stack them, cap at 30%.

3. `POST /quote`
   - Input: `{ customer_id, items: [{product_id, quantity}], promo_code? }`
   - Output: `{ quote_id, customer_id, line_items[], subtotal, discount_total, final_total, generated_at }`
   - Logic: Loop items, apply discounts per item, apply promo code, sum totals. Quote ID is timestamp-based.
   - IMPORTANT: Include code comments explaining what this endpoint CAN'T do (no customer history, no competitor awareness, no negotiation, no reasoning).

4. `GET /health`
   - Output: `{ status: "ok", service: "PricingService", version: "1.0.0" }`

**Data:** All in module-level dicts (PRODUCTS, DISCOUNT_RULES). See PRD for exact values.

---

### `pricing_agent/tools.py` — Layer 3: Tool Registry

**Purpose:** Wrap business logic as LLM-callable tools. The key insight: the microservice's logic doesn't get rewritten, it gets WRAPPED.

**Contains:**

1. `TOOL_DEFINITIONS` — List of dicts in OpenAI function-calling format. Each has name, description, parameters (JSON Schema). These get passed to the LLM so it knows what tools are available.

2. Tool implementations (6 functions):

   - `get_base_price(product_id) -> dict` — Same as microservice price lookup, BUT also returns margin_floor (data the microservice didn't expose).
   
   - `check_volume_discount(quantity) -> dict` — Returns discount_pct, tier name, and next_tier info (tells the agent about upsell opportunities).
   
   - `get_customer_history(customer_id) -> dict` — Returns mock customer data: total_spend, order_count, loyalty_tier, last_purchase, products_purchased, avg_order_value, churn_risk. Two mock customers (C-1234 and C-5678). Unknown customers return a "new_customer" stub.
   
   - `get_competitor_pricing(product_id) -> dict` — Returns competitor prices, average, and lowest. Three competitors per product.
   
   - `calculate_margin(product_id, proposed_price) -> dict` — Returns margin_dollars, margin_pct, meets_floor boolean, and warning if below floor.
   
   - `suggest_bundles(product_id) -> dict` — Returns suggested addon products, bundle discount, and rationale string.

3. `TOOL_REGISTRY` — Dict mapping tool names to functions.

4. `execute_tool(tool_name, arguments) -> dict` — Dispatcher. Looks up tool, calls it, catches exceptions, returns result or error dict.

**Design notes:**
- Every tool returns a dict (never raises exceptions to the caller)
- Error cases return `{"error": "..."}` not HTTP exceptions
- Tool descriptions should be written for an LLM to understand — clear, specific, with usage guidance

---

### `pricing_agent/memory.py` — Layer 4: Domain Memory

**Purpose:** Persistent context that informs reasoning. Not cache. Not session state. Domain memory.

**Class: `DomainMemory`**

State (all in-memory, instance-level):
- `_interactions: dict[str, list[dict]]` — Per-customer interaction log (defaultdict of lists)
- `_decisions: list[dict]` — Pricing decision history
- `_patterns: dict[str, Any]` — Precomputed domain patterns (avg enterprise discount, seasonal demand, etc.)

Methods:
- `record_interaction(customer_id, interaction)` — Append to customer's interaction list with timestamp
- `get_recent_interactions(customer_id, hours=24)` — Filter interactions by recency
- `record_decision(decision)` — Log a pricing decision with timestamp
- `get_similar_decisions(product_id, customer_tier=None, limit=5)` — Find past decisions for similar products/tiers
- `get_domain_pattern(key)` — Retrieve a domain-level pattern
- `get_context_summary(customer_id) -> dict` — Build a context dict for the reasoning engine containing: recent interaction count, products discussed, recent goals, and relevant domain patterns

**Module-level singleton:** `memory = DomainMemory()` — imported by agent.py.

**Design notes:**
- Keep it simple. No Redis. No vector DB. In-memory only.
- The class should have clear docstrings explaining what each piece would be in production
- Timestamps use `datetime.now().isoformat()`

---

### `pricing_agent/safety.py` — Layer 5: Safety Boundaries

**Purpose:** Guardrails on what the agent can and cannot do. Called BEFORE actions execute.

**Dataclass: `SafetyConfig`**

Fields with defaults:
```
max_discount_pct: 0.35
margin_floor_override: False
max_unit_price_authority: 500.0
max_reasoning_steps: 10
max_tool_calls: 15
max_reasoning_time_seconds: 30
can_commit_quotes: False
can_modify_base_prices: False
can_create_custom_promos: False
can_contact_customer: False
escalate_above_deal_value: 10000.0
escalate_on_competitor_match: True
escalate_new_customer: False
```

**Dataclass: `SafetyCheckResult`**

Fields:
```
allowed: bool
reason: Optional[str]
requires_approval: bool
approval_reason: Optional[str]
modified_action: Optional[dict]  # Adjusted action if original was unsafe
```

**Class: `SafetyBoundary`**

Takes SafetyConfig in constructor. Methods:

- `check_discount(discount_pct, product_id) -> SafetyCheckResult` — Block if over max, return modified_action with capped discount
- `check_margin(proposed_price, margin_floor) -> SafetyCheckResult` — Block if below floor
- `check_deal_value(total_value) -> SafetyCheckResult` — Allow but flag requires_approval if over threshold
- `check_reasoning_limits(steps, tool_calls) -> SafetyCheckResult` — Block if over limits
- `check_authority(action) -> SafetyCheckResult` — Check against can_* flags
- `validate_response(response_dict) -> SafetyCheckResult` — Final validation before sending response. Runs all relevant checks, aggregates results.

**Module-level defaults:** `DEFAULT_SAFETY = SafetyConfig()` and `safety = SafetyBoundary()`

---

### `pricing_agent/agent.py` — Layers 1 & 2: Goal Interface + Reasoning Engine

**Purpose:** The main AgentService. This is where everything comes together.

**Pydantic Models:**

`PricingGoal` (request):
```
goal: str                    # Natural language goal
customer_id: Optional[str]   # Optional context
product_ids: list[str]       # Products being considered
constraints: dict             # Budget limits, etc.
```

`PricingResponse` (response):
```
recommended_price: Optional[float]
reasoning: str
tools_used: list[str]
confidence: float
requires_approval: bool
approval_reason: Optional[str]
alternatives: list[dict]
context_used: dict
trajectory: list[dict]        # Full reasoning trace
```

**Class: `PricingAgentEngine`**

Constructor: Reads `OPENAI_API_KEY` and `MODEL_NAME` from env.

Main method: `async reason(goal: PricingGoal) -> PricingResponse`

Flow:
1. Gather context from memory (Layer 4) — call `memory.get_context_summary()`
2. Record interaction in memory
3. IF API key exists → `_reason_with_llm()` ELSE → `_reason_with_rules()`
4. Run safety validation (Layer 5) — call `safety.validate_response()`
5. Log decision in memory
6. Return response with full trajectory

**`_reason_with_llm()` method:**
- Builds system prompt with domain context and safety constraints
- Sends to OpenAI with tool definitions from tools.py
- Runs tool-calling loop: receive response → if tool_calls, execute tools, append results → repeat until no more tool calls or safety limit hit
- Extracts recommended price from final LLM text (regex for dollar amounts)
- Records each tool call in trajectory

**`_reason_with_rules()` method (fallback):**
- Demonstrates the PATTERN without requiring an LLM
- For each product_id: calls get_base_price → get_customer_history (if customer_id) → get_competitor_pricing → applies reasoning rules (loyalty discount for Gold tier, retention discount for high churn risk, competitive adjustment based on lowest competitor price) → calculate_margin → suggest_bundles
- Enforces safety checks inline (margin floor, discount cap)
- Records every step in trajectory
- Returns response with confidence 0.75 (no customer) or 0.85 (with customer)

CRITICAL: The fallback MUST use the same tools.py, memory.py, and safety.py as the LLM path. This proves the architecture matters, not just the LLM.

**Endpoints:**

1. `POST /pricing/evaluate` — Goal interface. Calls `engine.reason()`.
2. `GET /price/{product_id}` — Legacy backward compatibility. Calls `tools.get_base_price()` directly, adds `_notice` field.
3. `GET /health` — Returns service info including layer status.

---

### `tests/test_microservice.py`

**Purpose:** Show what traditional microservice testing looks like.

Test classes:
- `TestPriceLookup` — GET endpoint tests, 404 handling, all products exist
- `TestDiscountCalculation` — Volume tier tests, discount cap verification
- `TestQuoteGeneration` — Single item, multi-item, promo code, invalid product
- `TestHealth` — Health check returns correct service name

All tests use `TestClient(app)`. All assertions are on exact values or status codes.

---

### `tests/test_agentservice.py`

**Purpose:** Show how testing fundamentally changes for an AgentService.

Test classes (8 categories):

1. `TestTaskCompletion` — Agent returns a valid recommendation with non-empty reasoning. Loyal customer gets better than base price. High churn risk gets retention discount.

2. `TestToolSelection` — Verifies correct tools are used: base price always used, customer history used when customer_id provided, competitor pricing consulted, margin always checked, bundles suggested.

3. `TestTrajectory` — Trajectory is recorded, starts with memory lookup (when customer provided), tool results are captured.

4. `TestSafetyCompliance` — Price never below margin floor (CRITICAL), discount never above 35%, large deals require approval, agent cannot commit quotes or modify base prices, reasoning loop is bounded.

5. `TestConsistency` — Same goal 5 times produces identical prices (deterministic fallback). Same goal produces same tool selection.

6. `TestToolRegistry` — All 6 tools registered, individual tool correctness, margin floor in tool responses, unknown tool returns error.

7. `TestDomainMemory` — Record and retrieve interactions, context summary, decision logging.

8. `TestBackwardCompatibility` — Legacy GET endpoint works, health shows AgentService type and layer info.

---

## Data Flow Diagrams

### Microservice Flow
```
Request → Endpoint → Deterministic Logic → Response
```
That's it. No branching. No reasoning. No memory.

### AgentService Flow
```
Goal Request
    │
    ▼
Layer 1: Goal Interface (parse goal, extract intent)
    │
    ▼
Layer 4: Domain Memory (gather context for this customer/product)
    │
    ▼
Layer 2: Reasoning Engine
    │   ┌─────────────────────────────────┐
    │   │  Reasoning Loop:                │
    │   │  1. Assess what data is needed  │
    │   │  2. Call tool (Layer 3)         │
    │   │  3. Interpret result            │
    │   │  4. Decide: need more data?     │
    │   │     YES → go to 1              │
    │   │     NO  → synthesize answer     │
    │   │                                 │
    │   │  Safety check at each step      │
    │   │  (Layer 5)                      │
    │   └─────────────────────────────────┘
    │
    ▼
Layer 5: Safety Boundaries (final validation)
    │
    ▼
Layer 4: Domain Memory (log this decision)
    │
    ▼
Response (price + reasoning + tools + confidence + trajectory + approval status)
```

## Key Design Decisions

1. **Single file for microservice, 4 files for AgentService.** The file split IS the architecture. Each file = one layer (agent.py covers two because the goal interface and reasoning engine are tightly coupled).

2. **Rule-based fallback is NOT a crutch.** It's architecturally important. It proves that the 5-layer structure has value independent of the LLM. The same tools, memory, and safety layers work regardless of whether the reasoning is LLM-powered or rule-based.

3. **No async for tools.** Tools are synchronous functions. The reasoning engine is async (for LLM API calls), but tools themselves are simple sync functions. Keep it simple.

4. **Trajectory is a first-class output.** Every response includes the full reasoning trace. This is one of the key differences between microservice testing (assert on payloads) and AgentService evaluation (evaluate the trajectory).

5. **Safety is checked twice.** Once inline during reasoning (to catch issues early and adjust) and once at the end via `validate_response()` (final gate before response goes out). Belt and suspenders.

6. **Legacy endpoints on the AgentService.** The old `GET /price/{product_id}` still works. This demonstrates that migration is incremental — you don't break existing consumers.

## Implementation Order

If building from scratch, follow this order:

1. `pricing_service/app.py` — Get the "before" working and tested
2. `tests/test_microservice.py` — Verify the microservice works
3. `pricing_agent/tools.py` — Wrap the business logic as tools
4. `pricing_agent/memory.py` — Build the memory layer
5. `pricing_agent/safety.py` — Build the safety layer
6. `pricing_agent/agent.py` — Wire everything together
7. `tests/test_agentservice.py` — Build the evaluation suite
8. `README.md` — Document the architecture and usage

## What to NOT Do

- Do NOT add abstractions, base classes, or interfaces. Keep it flat and readable.
- Do NOT add configuration files (YAML, TOML, etc.). Env vars only.
- Do NOT add middleware, logging frameworks, or metrics libraries.
- Do NOT add type: ignore comments. Fix the types instead.
- Do NOT add docstrings that repeat the function signature. Docstrings should explain WHY, not WHAT.
- Do NOT add more than 2 levels of function nesting.
- Do NOT make the rule-based fallback smarter than necessary. It's there to demonstrate the pattern, not to be impressive.
