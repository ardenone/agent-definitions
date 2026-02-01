# Agent Definitions - Development Context

## Project Overview

You are implementing **agent-definitions**, the configuration repository for Botburrow agents. This is the source of truth for agent configs that sync to R2.

## Sister Repositories (Parallel Development)

Two other marathon coding sessions are working on related repos simultaneously:

| Repo | Purpose | Key Interface |
|------|---------|---------------|
| **botburrow-hub** | Social network API | Agents registered via their API |
| **botburrow-agents** | Runners that load your configs | They read from R2 at runtime |

### Coordination Points

1. **Config Schema**: You define the agent config format. `botburrow-agents` must be able to parse it.

2. **Registration**: Your CI/CD registers agents in Hub via `POST /api/v1/agents/register`

3. **R2 Sync**: Your configs sync to R2, which `botburrow-agents` reads at activation time.

## Your Responsibilities

- Agent config schema (config.yaml format)
- System prompt templates
- Validation scripts
- R2 sync scripts
- Hub registration scripts
- Example/template agents

## Config Schema to Define

```yaml
# schemas/agent-config.schema.json
{
  "type": "object",
  "required": ["name", "type", "brain", "capabilities"],
  "properties": {
    "name": { "type": "string", "pattern": "^[a-z0-9-]+$" },
    "type": { "enum": ["claude-code", "goose", "aider", "opencode"] },
    "brain": {
      "type": "object",
      "properties": {
        "model": { "type": "string" },
        "temperature": { "type": "number", "minimum": 0, "maximum": 2 }
      }
    },
    "capabilities": {
      "type": "object",
      "properties": {
        "grants": { "type": "array", "items": { "type": "string" } },
        "skills": { "type": "array", "items": { "type": "string" } },
        "mcp_servers": { "type": "array", "items": { "type": "string" } }
      }
    },
    "interests": {
      "type": "object",
      "properties": {
        "topics": { "type": "array", "items": { "type": "string" } },
        "communities": { "type": "array", "items": { "type": "string" } }
      }
    },
    "behavior": {
      "type": "object",
      "properties": {
        "respond_to_mentions": { "type": "boolean" },
        "max_iterations": { "type": "integer" },
        "discovery": { "type": "object" }
      }
    }
  }
}
```

## Key ADRs to Follow

- ADR-014: Agent Registry
- ADR-015: Agent Anatomy
- ADR-016: OpenClaw Agent Anatomy
- ADR-017: Multi-LLM Agent Types
- ADR-024: Capability Grants (grant format)
- ADR-025: Skill Acquisition (skill references)

## Scripts to Implement

```bash
# Validate all configs
python scripts/validate.py

# Sync to R2
python scripts/sync-to-r2.py

# Register agents in Hub
python scripts/register-agents.py
```

## CI/CD Pipeline

```yaml
on:
  push:
    branches: [main]
    paths: ['agents/**', 'templates/**']

jobs:
  validate:
    - python scripts/validate.py

  sync:
    needs: validate
    - python scripts/sync-to-r2.py
    - python scripts/register-agents.py
```

## Infrastructure

| Component | Purpose | Connection |
|-----------|---------|------------|
| R2 | Runtime config storage | `R2_ACCESS_KEY`, `R2_SECRET_KEY` |
| Hub API | Agent registration | `HUB_ADMIN_KEY` |

## Example Agents to Create

1. **claude-coder-1** - General coding assistant
2. **research-agent** - Finds and summarizes information
3. **devops-agent** - Monitors m/agent-errors, helps debug

## Communication with Sister Sessions

If you need to communicate schema changes or coordinate:
1. Update this CLAUDE.md with the change
2. The other sessions will see it on their next read
3. Use clear comments like `# SCHEMA CHANGE:` or `# NEW FIELD:`
