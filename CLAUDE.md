# Microservice to AgentService — Ways of Working

## Identity

You are the agent for this repository. This is a published blog companion — the codebase that accompanies Sanat's article on migrating from microservice to agent-service architecture.

**Sanat Dhir** — Author. Decision-maker.

## Project Overview

Companion code for the blog post "From Microservice to AgentService." Demonstrates the architectural patterns described in the article using a real working example.

**Repo:** github.com/skdhir/microservice-to-agentservice
**Stage:** Published — no active development. Changes are rare and documentation-driven.

## Canonical References

- **Cross-cutting conventions:** `~/skdorg/claude/phoenix-bridge-claude/shared/multi-agent-conventions.md` — trigger phrases, branch/commit conventions, review rules
- **Session protocol:** `~/skdorg/toolkit/SESSION_PROTOCOL.md`
- **Permissions policy:** `shared/permission-policy.md` (Tier 1 applied via `.claude/settings.json`)

## Session Protocol

### Welcome
When Sanat says **"Welcome"** (or any session-opening greeting):
1. Silently re-read this CLAUDE.md
2. Run `git status` and `git log --oneline -5`
3. Ask what to focus on

### Signing Off
When Sanat says **"Signing off"**, **"Logging off"**, **"Taking a break"**, or **"Wrapping up"**:
1. Commit and push any changes
2. Confirm: "State saved."

## CRITICAL — Read Before Every Task

**STOP. Before writing ANY code, you MUST:**

1. **Brainstorm**: Present 2-3 options with trade-offs.
2. **Agree**: Wait for Sanat to pick an option.
3. **Plan**: Get explicit approval.
4. **Implement**: Only after steps 1-3.

## Git Workflow

- Branch from `main`: `feat/{description}` or `fix/{description}`
- Never force-push
- **Open a PR and wait for Sanat to merge**

## What's Here

```
microservice-to-agentservice/
├── pricing_service/    # Original microservice implementation
├── pricing_agent/      # Agent-service implementation
├── tests/              # Comparison tests
├── docs/               # Architecture diagrams and explanations
└── README.md           # Article companion guide
```
