# Migration Guide: Your Service to an AgentService

A practical checklist for migrating any microservice to the AgentService pattern. Each step is independently deployable — you don't need to complete all steps to get value.

## Prerequisites

Before starting, confirm your service is a good candidate:

- [ ] Business logic has 10+ conditional branches or a growing rules engine
- [ ] Human-in-the-loop is a bottleneck (exception queues, manual reviews)
- [ ] Edge cases are growing faster than your team can code for them
- [ ] Consumers are asking for flexibility your rigid API can't provide
- [ ] AI agents are (or will be) consuming your API

If none of these apply, your microservice is fine as-is. Don't migrate for the sake of migrating.

---

## Stage 1: Agent-Ready Interface

**Goal:** Accept goal-oriented requests alongside your existing API.

**Time:** 1-2 days

### Steps

- [ ] Define your `Goal` request model
  ```python
  class PricingGoal(BaseModel):
      goal: str                          # Natural language
      customer_id: Optional[str] = None  # Context
      product_ids: list[str] = []        # Subjects
      constraints: dict = {}             # Limits
  ```

- [ ] Define your `Response` model (richer than your current response)
  ```python
  class PricingResponse(BaseModel):
      recommended_price: Optional[float]
      reasoning: str           # WHY, not just WHAT
      tools_used: list[str]    # Transparency
      confidence: float        # How sure
      requires_approval: bool  # Human needed?
      trajectory: list[dict]   # Full reasoning trace
  ```

- [ ] Add new endpoint: `POST /pricing/evaluate`
- [ ] Keep ALL existing endpoints working (backward compatibility)
- [ ] Deploy — existing consumers aren't affected

### Validation
- Existing tests still pass
- New endpoint accepts a goal and returns a response (even if it just wraps existing logic for now)

---

## Stage 2: Tool Registry (Layer 3)

**Goal:** Wrap your existing business logic as callable tools.

**Time:** 1-3 days

### Steps

- [ ] Identify your core business functions (price lookup, discount calculation, etc.)
- [ ] For each function, create:
  - An OpenAI-compatible tool definition (name, description, parameters as JSON Schema)
  - A wrapper function that returns a dict (never raises exceptions)
- [ ] Create a `TOOL_REGISTRY` dict mapping tool names to functions
- [ ] Create an `execute_tool(name, args)` dispatcher
- [ ] Write unit tests for each tool independently

### Key Principle
**Your logic doesn't change. The wrapper is thin.** If your discount function takes `(product_id, quantity)` and returns a float, your tool takes the same inputs and returns `{"discount_pct": 0.15, "tier": "Gold", "next_tier": "..."}` — same calculation, richer output.

### Validation
- Every existing calculation produces the same result through the tool wrapper
- Tools return error dicts for invalid inputs (not exceptions)
- Tool definitions are clear enough for an LLM to understand

---

## Stage 3: Safety Boundaries (Layer 5)

**Goal:** Define explicit guardrails before adding reasoning.

**Time:** 1 day

### Steps

- [ ] Define your `SafetyConfig` with sensible defaults:
  - Max discount / price floor / authority limits
  - Reasoning limits (steps, tool calls, timeout)
  - Escalation thresholds (deal size, special cases)
  - Authority scope (what the agent can NOT do)
- [ ] Implement safety check methods:
  - `check_discount()` — caps at maximum
  - `check_margin()` — enforces floor
  - `check_deal_value()` — flags large deals
  - `check_reasoning_limits()` — prevents runaway loops
  - `check_authority()` — blocks unauthorized actions
  - `validate_response()` — final gate before sending response
- [ ] Write tests that verify safety is NEVER violated

### Key Principle
**Build the guardrails before you build the reasoning.** It's much harder to add safety after an agent is already making decisions.

### Validation
- No input can produce a response that violates safety boundaries
- Tests specifically try to break safety (adversarial inputs)
- Escalation triggers correctly flag for human review

---

## Stage 4: Domain Memory (Layer 4)

**Goal:** Give your service context awareness.

**Time:** 1-2 days

### Steps

- [ ] Define your memory categories:
  - Short-term: Recent interactions with this customer/entity
  - Medium-term: Past decisions for similar cases
  - Long-term: Domain patterns and insights
- [ ] Implement:
  - `record_interaction()` — log each request with context
  - `get_recent_interactions()` — retrieve recent history
  - `record_decision()` — log each response with outcome
  - `get_similar_decisions()` — find past decisions for similar inputs
  - `get_context_summary()` — build a context dict for the reasoning engine
- [ ] Start with in-memory implementation (upgrade to Redis/DB later)

### Key Principle
**Memory informs reasoning, it doesn't replace it.** The memory layer provides context; the reasoning engine decides what to do with it.

### Validation
- Context summary includes relevant recent interactions
- Decision log captures all recommendations
- Memory correctly filters by recency and relevance

---

## Stage 5: Reasoning Engine (Layer 2)

**Goal:** Add intelligent reasoning that uses tools, memory, and safety.

**Time:** 2-5 days

### Steps

- [ ] Implement rule-based reasoning FIRST (no LLM required)
  - Follows a deterministic path using your tools
  - Uses the SAME tool registry, memory, and safety layers
  - Records every step in the trajectory
  - This IS your production fallback

- [ ] Add LLM reasoning (optional, for full capability)
  - Build system prompt with domain context and safety constraints
  - Send tool definitions to LLM
  - Implement tool-calling loop (call tools, append results, repeat)
  - Extract recommendation from LLM response
  - Record trajectory

- [ ] Wire the main flow:
  1. Gather context from memory
  2. Record interaction
  3. Reason (LLM or fallback)
  4. Validate against safety
  5. Log decision in memory
  6. Return response with trajectory

### Key Principle
**The rule-based fallback must use the same layers as the LLM path.** This proves the architecture has value independent of the LLM. If your fallback bypasses tools or safety, you don't have an AgentService — you have a wrapper around an LLM.

### Validation
- Rule-based path produces valid recommendations with reasoning
- LLM path (if configured) uses tools appropriately
- Safety is never violated regardless of reasoning path
- Trajectory is always recorded
- Consistency test: same input produces same output (rule-based)

---

## Post-Migration Checklist

- [ ] All existing tests still pass (backward compatibility)
- [ ] New AgentService tests pass (8 categories):
  1. Task completion
  2. Tool selection
  3. Trajectory quality
  4. Safety compliance
  5. Consistency
  6. Tool unit tests
  7. Domain memory
  8. Backward compatibility
- [ ] Legacy endpoints return the same data (with optional `_notice` field)
- [ ] Health endpoint reports layer status
- [ ] README maps every file to the 5-layer architecture
- [ ] Team understands the testing shift (payload assertions -> trajectory evaluation)

---

## Common Pitfalls

1. **Migrating simple services.** Currency conversion doesn't need reasoning. Don't add complexity where determinism works.

2. **Skipping the rule-based fallback.** If your AgentService only works with an LLM, you can't test it reliably and you can't demonstrate the architecture's value.

3. **Adding safety after reasoning.** Build guardrails first. An unguarded agent in production is a liability.

4. **Rewriting business logic.** The whole point is that your logic becomes tools. Same functions, same calculations. Don't rewrite them.

5. **Over-engineering memory.** Start with in-memory dicts. Add Redis when you have a real scale need, not before.

6. **Ignoring cost.** LLM calls cost 100-1000x more than deterministic compute. Use the rule-based fallback for simple cases, LLM for complex ones. Not everything needs to "think."
