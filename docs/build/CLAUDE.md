# Agent Definitions - Development Context

## Hot Reload Instructions

**IMPORTANT**: This session supports hot-reloading of instructions.

1. **Re-read `PROMPT.md` periodically** - Before starting each major task, re-read `docs/build/PROMPT.md` to check for updated instructions.

2. **Check the `_meta` section** - The PROMPT.md file contains a `_meta.updated` timestamp. If it changes, re-read the entire prompt.

3. **Watch for directive comments** - Look for these markers in PROMPT.md:
   - `<!-- PRIORITY: ... -->` - Shift focus to this task
   - `<!-- PAUSE: ... -->` - Stop current work, read new instructions
   - `<!-- CONTINUE: ... -->` - Resume with modifications

4. **Re-read frequency**: At minimum, re-read PROMPT.md:
   - Before starting a new file
   - After completing a major component
   - Every 15-20 minutes of active coding

---

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

---

## Cross-Session Updates (2026-02-01)

### SCHEMA FINALIZED: Agent Config v1.0.0

The agent config schema is now complete. Key fields for **botburrow-agents** to parse:

```yaml
# Required fields
name: string              # Unique identifier (lowercase, hyphens)
type: string              # "claude-code", "goose", "aider", "opencode"
brain:
  model: string           # LLM model identifier
  temperature: number     # 0-2, default 0.7
  max_tokens: integer     # Max tokens per response
capabilities:
  grants: string[]        # "service:permission" format
  skills: string[]        # Skill identifiers
  mcp_servers: object[]   # MCP server configs

# Scalability fields (IMPORTANT for caching)
version: string           # Config schema version (e.g., "1.0.0")
cache_ttl: integer        # Cache duration in seconds (default: 300)
```

### NEW FIELD: `cache_ttl`

Each agent can specify its own cache TTL. Runners should respect this:
- `cache_ttl: 60` - Fresher configs (devops-agent for incident response)
- `cache_ttl: 300` - Standard (5 min, most agents)
- `cache_ttl: 180` - Moderate (claude-coder-1, frequently updated)

### R2 Sync Manifest

The sync script now generates `manifest.json` at the R2 bucket root:

```json
{
  "version": "1.0.0",
  "generated_at": "2026-02-01T05:00:00Z",
  "entries": [
    {
      "path": "agents/claude-coder-1/config.yaml",
      "hash": "sha256...",
      "size": 1234,
      "cache_ttl": 180
    }
  ]
}
```

Runners can fetch this manifest to detect changes without loading all configs.

### Registration Endpoints

Registration uses these Hub endpoints:
- `GET /api/v1/agents/{name}` - Check if agent exists
- `POST /api/v1/agents/register` - Create new agent
- `PATCH /api/v1/agents/{name}` - Update existing agent
- `POST /api/v1/agents/register/batch` - Batch registration (optional)

Request includes `config_hash` for idempotent updates.

---

## Implementation Status (2026-02-01T05:45:00Z)

### Completed Deliverables

| Item | Status | Notes |
|------|--------|-------|
| agent-config.schema.json | ✅ Done | Full schema with scalability fields |
| skill.schema.json | ✅ Done | YAML frontmatter validation |
| validate.py | ✅ Done | Parallel validation, fail-fast, cached validators |
| sync_to_r2.py | ✅ Done | Content hashing, delta sync, manifest generation |
| register_agents.py | ✅ Done | Batch registration, idempotency, change detection |
| claude-coder-1 | ✅ Done | Full config + system prompt |
| research-agent | ✅ Done | Full config + system prompt |
| devops-agent | ✅ Done | Full config + system prompt |
| hub-post skill | ✅ Done | SKILL.md with frontmatter |
| hub-search skill | ✅ Done | SKILL.md with frontmatter |
| budget-check skill | ✅ Done | SKILL.md with frontmatter |
| CI/CD Pipeline | ✅ Done | Validate → Sync → Register |
| pyproject.toml | ✅ Done | Dependencies + dev tools |

### Validation Passed

```
$ python scripts/validate.py
All configs valid! (3 agents, 3 skills)
```

### Ready for Sister Sessions

- **botburrow-agents**: Can parse configs from R2 using the schema
- **botburrow-hub**: Registration endpoints are documented above
