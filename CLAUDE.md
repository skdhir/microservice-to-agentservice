# Microservice to AgentService — Ways of Working

## Identity

You are Claude, the solo coding agent for this repository inside the Phoenix Bridge multi-agent workspace. This is a published blog companion — the codebase that accompanies Sanat's article on migrating from microservice to agent-service architecture.

**Sanat Dhir** — Author. Decision-maker.

## Canonical Pointers

For cross-cutting workspace rules (trigger phrases, branch/commit conventions, review rules, memory model, cross-clone boundaries), read `../shared/multi-agent-conventions.md`. It is the canonical source and overrides any stale local process.

- **Cross-cutting conventions:** `../shared/multi-agent-conventions.md`
- **Session protocol:** `~/skdorg/toolkit/SESSION_PROTOCOL.md`
- **Ops runbook:** `~/skdorg/toolkit/RUNBOOK.md`
- **Permissions policy:** `../shared/permission-policy.md` (Tier 1 applied via `.claude/settings.json`)

Do not recreate shared policy here. This file holds only project-specific context.

## Project Status

**Repo:** github.com/skdhir/microservice-to-agentservice
**Stage:** Published — no active development. Changes are rare and documentation-driven.
**Mode:** Solo-Claude (no Codex partner on this repo).

## Project-Specific Context

```
microservice-to-agentservice/
├── pricing_service/    # Original microservice implementation
├── pricing_agent/      # Agent-service implementation
├── tests/              # Comparison tests
├── docs/               # Architecture diagrams and explanations
└── README.md           # Article companion guide
```

Since this repo is dormant/published, typical changes are doc corrections or minor example updates. For any non-trivial code change, brainstorm options with Sanat before implementing.
