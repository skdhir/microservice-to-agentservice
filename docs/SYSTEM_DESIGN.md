# System Design: AgentService Architecture

## Overview

This document explains the architectural reasoning behind the 5-layer AgentService pattern. It's intended for engineering leaders evaluating this approach for their own systems.

## The Problem

Microservices were designed for a world where all consumers are deterministic — frontends, other services, batch jobs. They send structured requests and expect structured responses. The contract is about *procedure*: call this endpoint with these parameters, get this result.

Three forces are breaking this model:

1. **AI agents are becoming API consumers.** An autonomous purchasing agent doesn't call your pricing API the way a frontend does. It negotiates, asks "what if," and needs to understand *why* — not just *what*.

2. **Business logic is drowning in edge cases.** Every conditional branch in your rules engine is an admission that deterministic code can't handle the complexity. The exception queue grows faster than the happy path.

3. **Services need to become autonomous actors.** A pricing service that just looks up prices is leaving money on the table. A pricing *agent* that reasons about customer history, competitor pressure, and margin targets creates real business value.

## Why 5 Layers?

The layers aren't arbitrary. Each one addresses a specific gap between what a microservice can do and what an AgentService needs to do.

### Layer 1: Goal Interface

**Gap:** Microservices accept procedures ("get price for product X"). AgentServices accept goals ("find the optimal price for this customer considering their history and competitor pressure").

**Design decision:** The goal interface translates natural language or structured goals into actionable objectives. It decouples the caller's *intent* from the service's *execution plan*.

**What this means in practice:** Your existing `GET /price/{id}` endpoint still works (backward compatibility). But new consumers — especially AI agents — use `POST /pricing/evaluate` with a goal. The same service handles both, at the same URL, with the same team.

### Layer 2: Reasoning Engine

**Gap:** Microservices follow a fixed execution path. AgentServices decide which path to take based on the goal and available context.

**Design decision:** The reasoning engine is the only layer that changes based on whether you use an LLM or a rule-based fallback. Everything else — tools, memory, safety — stays the same. This proves the architecture's value is in the layers, not just the LLM.

**Two modes:**
- **LLM mode** (with API key): Full reasoning with tool calling. The LLM decides which tools to invoke, interprets results, and synthesizes a recommendation.
- **Rule-based mode** (no API key): Follows a deterministic reasoning path using the same tools. Useful for testing, local development, and demonstrating the pattern.

**Why this matters:** If you can only get value from the architecture by adding an LLM, it's not an architecture — it's a wrapper. The rule-based fallback proves the 5-layer structure creates value independently.

### Layer 3: Tool Registry

**Gap:** Microservice business logic is embedded in endpoint handlers. It can't be composed, reused, or invoked by a reasoning engine.

**Design decision:** Wrap existing business logic as callable tools with OpenAI-compatible function definitions. The logic doesn't change — the way it's invoked changes.

**Key insight:** This is why the migration isn't a rewrite. Your discount rules, rate tables, and calculations become tools the reasoning engine can call. The functions are the same. The inputs and outputs are the same. But now they're composable — the engine decides which tools to use and in what order.

**Tool design principles:**
- Every tool returns a dict (never raises exceptions to the caller)
- Error cases return `{"error": "..."}` not HTTP exceptions
- Tool descriptions are written for an LLM to understand
- Tools expose more data than the microservice did (e.g., margin_floor)

### Layer 4: Domain Memory

**Gap:** Microservices are stateless per request. Every call starts from zero context.

**Design decision:** Domain memory provides operational context that informs reasoning. It's not session state (that's the caller's job). It's not cache (that's infrastructure). It's domain knowledge that accumulates over time.

**Three types of memory:**
- **Interactions** (short-term): What has this customer asked about recently?
- **Decisions** (medium-term): What prices have we recommended for similar products/customers?
- **Patterns** (long-term): What's the average enterprise discount? What's seasonal demand?

**Production considerations:** This implementation uses in-memory dicts. In production, you'd use Redis for interactions, Postgres for decisions, and a periodic batch job for patterns. The interface stays the same — the agent doesn't care about the storage backend.

### Layer 5: Safety Boundaries

**Gap:** Microservices have implicit boundaries (input validation, business rules). AgentServices need explicit boundaries because the reasoning engine might do unexpected things.

**Design decision:** Safety is checked twice — inline during reasoning (catch issues early) and as a final gate before the response goes out. Belt and suspenders.

**Boundary categories:**
- **Pricing limits:** Max discount (35%), margin floor enforcement
- **Reasoning limits:** Max steps (10), max tool calls (15), timeout (30s)
- **Authority scope:** Cannot commit quotes, modify base prices, create promos, or contact customers
- **Escalation triggers:** Deal value > $10K, competitor price matching, new customers

**Why safety is a first-class layer:** In a microservice, safety is implicit in the code — the function simply doesn't have a path that violates margins. In an AgentService, the reasoning engine might find a path you didn't anticipate. The safety layer is the architectural guarantee that even if reasoning goes wrong, the output stays within bounds.

## Data Flow

### Microservice
```
Request -> Endpoint -> Deterministic Logic -> Response
```
One path. No branching. No reasoning. No memory.

### AgentService
```
Goal Request
    |
    v
Layer 1: Goal Interface (parse goal, extract intent)
    |
    v
Layer 4: Domain Memory (gather context)
    |
    v
Layer 2: Reasoning Engine
    |   +-----------------------------------+
    |   | Reasoning Loop:                   |
    |   | 1. Assess what data is needed     |
    |   | 2. Call tool (Layer 3)            |
    |   | 3. Interpret result               |
    |   | 4. Safety check (Layer 5)         |
    |   | 5. Need more? YES -> 1, NO -> 6   |
    |   | 6. Synthesize recommendation      |
    |   +-----------------------------------+
    |
    v
Layer 5: Safety Boundaries (final validation)
    |
    v
Layer 4: Domain Memory (log decision)
    |
    v
Response (price + reasoning + tools + confidence + trajectory + approval)
```

## What Changes vs. What Stays the Same

### Changes

| Aspect | Microservice | AgentService |
|--------|-------------|-------------|
| Contract | Procedure-oriented (do X) | Goal-oriented (achieve Y) |
| State | Stateless per request | Domain memory across requests |
| Logic | Deterministic rules | Reasoning over rules-as-tools |
| Error handling | Status codes | Intelligent recovery and escalation |
| Testing | Payload assertions | Trajectory evaluation |
| Observability | Request tracing | Reasoning traces (decision logs) |
| Cost model | Linear (compute * traffic) | Variable (reasoning complexity) |

### Stays the Same

| Aspect | Why |
|--------|-----|
| Service boundaries | Domain decomposition is still valid |
| Infrastructure | Containers, API gateways, CI/CD — same stack |
| Team ownership | Same team owns the PricingAgent as owned the PricingService |
| Core business logic | Discount rules, rate tables — now wrapped as tools, not rewritten |
| Deployment model | Same deployment pipeline, same monitoring, same alerting |

## When NOT to Migrate

Not every microservice should become an AgentService. Migrate services where:

- Business logic is complex and exception-heavy
- Human-in-the-loop creates bottlenecks
- Edge cases are growing faster than your rules engine
- Consumers need flexibility, not rigid contracts
- Unstructured data requires interpretation

Leave services alone where:

- Logic is simple and deterministic (currency conversion, email validation)
- Predictability is more valuable than flexibility
- Cost sensitivity is extreme (LLM calls cost money)
- Regulatory requirements demand fully auditable, deterministic paths

## Cost Implications

| Scenario | Microservice Cost | AgentService Cost |
|----------|------------------|-------------------|
| Simple price lookup | ~$0.0001 (compute) | ~$0.0001 (same — uses legacy endpoint) |
| Standard pricing decision | ~$0.0001 (compute) | ~$0.01-0.05 (rule-based fallback) |
| Complex multi-factor pricing | ~$0.0001 (compute + human time) | ~$0.05-0.50 (LLM reasoning) |

The cost increase is real but offset by: reduced human-in-the-loop time, fewer exception queue items, better pricing decisions, and faster response to competitive pressure.

## Migration Stages

1. **Agent-Ready Interface** — Add goal-oriented endpoint alongside existing ones. No behavior change.
2. **Reasoning Layer** — Add LLM reasoning with rule-based fallback. Existing logic becomes tools.
3. **Memory and Context** — Add domain memory. Service starts learning from interactions.
4. **Inter-Agent Collaboration** — Services communicate goals, not just data.
5. **Autonomy Expansion** — Gradually expand agent authority as trust is established.

Each stage is independently deployable. You don't need to reach Stage 5 to get value. Stage 1 alone makes your service ready for AI agent consumers.
