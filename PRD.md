# PRD: microservice-to-agentservice

## What This Is

A companion GitHub repository for the blog post "From Microservice to AgentService: Your Services Need to Think Now." The repo demonstrates the complete migration of a traditional microservice (PricingService) to an AgentService (PricingAgent) using a 5-layer architecture.

This is NOT a framework, library, or product. It is a teaching repo — a concrete, runnable, forkable example that proves the AgentService concept with real code.

## Who It's For

Engineering leaders and senior engineers evaluating how to evolve their microservice architectures for the agentic AI era. They should be able to:

1. Clone the repo
2. Run the microservice ("before") and understand it in 5 minutes
3. Run the AgentService ("after") and see every architectural difference
4. Run the test suites and understand how testing changes
5. Map every file to the 5-layer AgentService architecture from the blog

## Goals

- Prove that "AgentService" is a real architectural concept, not a buzzword
- Show the migration is incremental, not a rewrite
- Demonstrate that existing business logic becomes tools, not throwaway code
- Show how testing fundamentally changes (payload assertions → trajectory evaluation)
- Work out of the box with zero API keys (rule-based fallback) AND with an OpenAI key for full LLM reasoning

## Non-Goals

- This is NOT a production-ready framework
- This is NOT meant to handle real pricing at scale
- This does NOT need auth, deployment configs, Docker, or CI/CD
- This does NOT need a frontend or UI
- This does NOT need multiple LLM provider support (OpenAI only is fine)

## Scope

### In Scope

1. **PricingService (the "before")** — A vanilla FastAPI microservice with:
   - `GET /price/{product_id}` — base price lookup
   - `GET /price/{product_id}/discount` — deterministic discount calculation
   - `POST /quote` — multi-item quote generation with promo codes
   - `GET /health` — health check
   - 5 products, 4 volume discount tiers, 3 promo codes
   - ~150 lines, no external dependencies beyond FastAPI

2. **PricingAgent (the "after")** — An AgentService with 5 distinct layers:
   - **Layer 1 — Goal Interface** (`agent.py`): `POST /pricing/evaluate` accepts a natural language goal, optional customer ID, product IDs, and constraints. Returns recommendation + reasoning + tools used + confidence + approval status + trajectory.
   - **Layer 2 — Reasoning Engine** (`agent.py`): LLM-powered reasoning with tool calling (OpenAI) OR rule-based fallback (no API key). The fallback must use the SAME tool registry and safety layer as the LLM path — this proves the architecture's value is in the layers, not just the LLM.
   - **Layer 3 — Tool Registry** (`tools.py`): 6 tools wrapping existing + new business logic: `get_base_price`, `check_volume_discount`, `get_customer_history`, `get_competitor_pricing`, `calculate_margin`, `suggest_bundles`. Each tool has an OpenAI-compatible function definition and a Python implementation.
   - **Layer 4 — Domain Memory** (`memory.py`): In-memory implementation (not Redis/Postgres — keep it simple). Records customer interactions, logs pricing decisions, stores domain patterns, provides context summaries to the reasoning engine.
   - **Layer 5 — Safety Boundaries** (`safety.py`): Configurable guardrails — max discount cap (35%), margin floor enforcement, deal value escalation threshold ($10K), reasoning loop limits (10 steps, 15 tool calls), authority scope (cannot commit quotes, modify base prices, create promos, or contact customers).
   - **Legacy compatibility**: `GET /price/{product_id}` still works on the AgentService, returns same data plus a notice pointing to the new endpoint.
   - `GET /health` returns layer status information.

3. **Test Suites** — Two fundamentally different testing approaches:
   - `test_microservice.py`: Traditional payload assertions. ~15 tests covering price lookup, discount calculation, quote generation, error handling.
   - `test_agentservice.py`: AgentService evaluation across 8 categories:
     - Task completion (did the agent achieve the goal?)
     - Tool selection (did it use appropriate tools?)
     - Trajectory evaluation (was the reasoning path recorded and sound?)
     - Safety compliance (did it respect all boundaries?)
     - Consistency (same goal, multiple runs, same result for deterministic fallback?)
     - Tool unit tests (individual tool correctness)
     - Domain memory tests (store/retrieve/summarize)
     - Backward compatibility (legacy endpoints still work)

4. **README** — Maps every file to the 5-layer architecture. Includes:
   - Directory structure
   - Quick start (3 commands)
   - Before/after API comparison with example request/response
   - What changed vs. what stayed the same
   - Environment variables
   - Testing philosophy explanation

5. **Supporting files**: `requirements.txt`, `.gitignore`, `LICENSE` (MIT)

### Out of Scope

- Docker / docker-compose
- CI/CD pipeline
- Database (all data is in-memory or hardcoded dicts)
- Authentication / authorization
- Rate limiting
- Multiple LLM providers (only OpenAI for the LLM path)
- Frontend / UI / Streamlit / Gradio
- Deployment to any cloud provider
- Logging framework (print statements are fine)
- API versioning
- OpenAPI spec customization

## Success Criteria

1. `pip install -r requirements.txt` works cleanly
2. `uvicorn pricing_service.app:app --port 8000` starts the microservice
3. `uvicorn pricing_agent.agent:app --port 8001` starts the AgentService
4. `pytest tests/test_microservice.py -v` — all tests pass
5. `pytest tests/test_agentservice.py -v` — all tests pass (without API key, using fallback)
6. The AgentService returns a recommended price with reasoning, tools used, confidence, and trajectory for any valid goal
7. Safety boundaries are never violated (price never below margin floor, discount never above 35%, reasoning never exceeds 10 steps)
8. Legacy `GET /price/{product_id}` works on both services
9. Total codebase is under 800 lines (excluding tests and README)
10. A senior engineer can read and understand the entire repo in 30 minutes

## Mock Data

### Products (5)

| ID | Name | Base Price | Category | Margin Floor |
|----|------|-----------|----------|-------------|
| WIDGET-PRO | Widget Pro | $99.99 | premium | $65.00 |
| WIDGET-BASIC | Widget Basic | $49.99 | standard | $30.00 |
| WIDGET-ENT | Widget Enterprise | $299.99 | enterprise | $180.00 |
| ADDON-SUPPORT | Premium Support | $29.99 | addon | $15.00 |
| ADDON-ANALYTICS | Analytics Pack | $19.99 | addon | $10.00 |

### Volume Discount Tiers (4)

| Tier | Min Quantity | Discount |
|------|-------------|---------|
| Bronze | 5 | 5% |
| Silver | 10 | 10% |
| Gold | 25 | 15% |
| Platinum | 50 | 20% |

### Mock Customers (2)

| ID | Name | Spend | Orders | Tier | Churn Risk |
|----|------|-------|--------|------|-----------|
| C-1234 | Acme Corp | $12,450 | 15 | Gold | Low |
| C-5678 | Startup Inc | $499.90 | 2 | None | High |

### Competitor Pricing (3 competitors, 3 products)

Competitors A, B, C with pricing that is sometimes above, sometimes below our base price. The data should create interesting pricing decisions where the agent needs to balance competitive pressure against margin floors.

### Promo Codes (microservice only)

| Code | Discount |
|------|---------|
| SAVE10 | 10% |
| WELCOME5 | 5% |
| ENTERPRISE20 | 20% |
