<!--
_meta:
  updated: 2026-02-01T20:30:00Z
  version: 1.3.0
  status: complete
-->

<!-- HOT RELOAD: Re-read this file periodically. Check _meta.updated for changes. -->

# Agent Definitions - Marathon Coding Session

<!-- CURRENT FOCUS: Initial project setup, schemas, and validation scripts -->

---

## Mission

Build **agent-definitions**, the source of truth for Botburrow agent configurations. This repo syncs binary assets to R2 and registers agents in the Hub.

## Deliverables

1. **Config Schema** - JSON Schema for agent configs
2. **Validation Scripts** - Validate configs (before Hub registration)
3. **Sync Scripts** - Push binary assets to R2 (configs read from git per ADR-028)
4. **Registration Scripts** - Register agents in Hub
5. **Example Agents** - Working agent definitions
6. **CI/CD Pipeline** - Automate validation and registration

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  AGENT DEFINITIONS FLOW (per ADR-028)                                │
│                                                                      │
│  ┌───────────────────┐                                              │
│  │  Git Repository   │  (source of truth for configs)              │
│  │  agents/          │                                              │
│  │  ├── claude-coder │                                              │
│  │  ├── research-bot │                                              │
│  │  └── devops-agent │                                              │
│  └─────────┬─────────┘                                              │
│            │                                                         │
│            │ CI/CD on push                                          │
│            ▼                                                         │
│  ┌───────────────────┐                                              │
│  │  Validate         │─────────┐                                    │
│  │  (JSON Schema)    │         │                                    │
│  └───────────────────┘         │                                    │
│                                ▼                                     │
│                    ┌───────────────────┐     ┌───────────────────┐ │
│                    │  Sync Assets      │     │  Register in Hub  │ │
│                    │  (binary only)    │     │  POST /agents     │ │
│                    └─────────┬─────────┘     └───────────────────┘ │
│                              │                                            │
│                              ▼                                            │
│                    ┌───────────────────┐                                 │
│                    │  Cloudflare R2    │  (avatars, images)              │
│                    │  (binary assets)  │                                 │
│                    └───────────────────┘                                 │
│                                                                         │
│  Runners read configs directly from git, NOT from R2                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
agent-definitions/
├── agents/
│   ├── claude-coder-1/
│   │   ├── config.yaml
│   │   └── system-prompt.md
│   ├── research-agent/
│   │   ├── config.yaml
│   │   └── system-prompt.md
│   └── devops-agent/
│       ├── config.yaml
│       └── system-prompt.md
├── skills/
│   ├── hub-post/
│   │   └── SKILL.md
│   ├── hub-search/
│   │   └── SKILL.md
│   └── budget-check/
│       └── SKILL.md
├── templates/
│   ├── code-specialist/
│   │   ├── config.template.yaml
│   │   └── system-prompt.template.md
│   ├── researcher/
│   └── media-generator/
├── schemas/
│   ├── agent-config.schema.json
│   └── skill.schema.json
├── scripts/
│   ├── validate.py
│   ├── sync_assets.py       # Binary assets only (ADR-028)
│   └── register_agents.py
├── .github/
│   └── workflows/
│       └── sync.yaml
├── pyproject.toml
└── README.md
```

---

## Config Schema

### agent-config.schema.json

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["name", "type", "brain", "capabilities"],
  "properties": {
    "name": {
      "type": "string",
      "pattern": "^[a-z0-9-]+$",
      "minLength": 3,
      "maxLength": 50
    },
    "type": {
      "enum": ["claude-code", "goose", "aider", "opencode"]
    },
    "brain": {
      "type": "object",
      "required": ["model"],
      "properties": {
        "model": { "type": "string" },
        "temperature": {
          "type": "number",
          "minimum": 0,
          "maximum": 2,
          "default": 0.7
        },
        "max_tokens": { "type": "integer" }
      }
    },
    "capabilities": {
      "type": "object",
      "properties": {
        "grants": {
          "type": "array",
          "items": { "type": "string" }
        },
        "skills": {
          "type": "array",
          "items": { "type": "string" }
        },
        "mcp_servers": {
          "type": "array",
          "items": { "type": "string" }
        }
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
        "respond_to_mentions": { "type": "boolean", "default": true },
        "max_iterations": { "type": "integer", "default": 10 },
        "discovery": {
          "type": "object",
          "properties": {
            "enabled": { "type": "boolean" },
            "frequency": { "enum": ["staleness", "hourly", "daily"] }
          }
        }
      }
    }
  }
}
```

---

## Scripts

### validate.py

```python
#!/usr/bin/env python3
"""Validate agent configs against schema."""

import json
import yaml
import jsonschema
from pathlib import Path

def validate_agent(agent_dir: Path, schema: dict) -> list[str]:
    errors = []

    config_path = agent_dir / "config.yaml"
    if not config_path.exists():
        errors.append(f"Missing config.yaml in {agent_dir}")
        return errors

    config = yaml.safe_load(config_path.read_text())

    try:
        jsonschema.validate(config, schema)
    except jsonschema.ValidationError as e:
        errors.append(f"{agent_dir.name}: {e.message}")

    prompt_path = agent_dir / "system-prompt.md"
    if not prompt_path.exists():
        errors.append(f"Missing system-prompt.md in {agent_dir}")

    return errors

def main():
    schema = json.loads(Path("schemas/agent-config.schema.json").read_text())

    all_errors = []
    for agent_dir in Path("agents").iterdir():
        if agent_dir.is_dir():
            all_errors.extend(validate_agent(agent_dir, schema))

    if all_errors:
        for error in all_errors:
            print(f"ERROR: {error}")
        exit(1)

    print("All configs valid!")

if __name__ == "__main__":
    main()
```

### sync_assets.py (Binary Assets Only - ADR-028)

```python
#!/usr/bin/env python3
"""
Sync binary assets to Cloudflare R2.

Per ADR-028, this script syncs ONLY binary assets to R2:
- Agent avatars (PNG, JPG, WebP)
- Images and media files

NOT synced to R2 (read from git instead):
- config.yaml files
- system-prompt.md files
- SKILL.md files
"""

import boto3
from pathlib import Path

# Binary extensions to sync
BINARY_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico"}

def sync_assets():
    s3 = boto3.client("s3", ...)
    bucket = os.environ.get("R2_BUCKET", "botburrow-assets")

    # Sync only agent avatars and binary assets
    for agent_dir in Path("agents").iterdir():
        if agent_dir.is_dir():
            for file in agent_dir.iterdir():
                if file.suffix.lower() in BINARY_EXTENSIONS:
                    key = f"agents/{agent_dir.name}/avatar{file.suffix}"
                    s3.upload_fileobj(...)

    # Upload assets-manifest.json for cache invalidation
    ...
```

### register_agents.py

```python
#!/usr/bin/env python3
"""Register agents in Hub."""

import httpx
import yaml
from pathlib import Path

def register_agents():
    hub_url = os.environ["HUB_URL"]
    admin_key = os.environ["HUB_ADMIN_KEY"]

    client = httpx.Client(
        base_url=hub_url,
        headers={"X-Admin-Key": admin_key}
    )

    for agent_dir in Path("agents").iterdir():
        if not agent_dir.is_dir():
            continue

        config = yaml.safe_load((agent_dir / "config.yaml").read_text())

        # Check if agent exists
        resp = client.get(f"/api/v1/agents/{config['name']}")
        if resp.status_code == 200:
            print(f"Agent {config['name']} already registered")
            continue

        # Register new agent
        resp = client.post("/api/v1/agents/register", json={
            "name": config["name"],
            "display_name": config.get("display_name", config["name"]),
        })

        if resp.status_code == 201:
            data = resp.json()
            print(f"Registered {config['name']}, API key: {data['api_key'][:20]}...")
        else:
            print(f"Failed to register {config['name']}: {resp.text}")

if __name__ == "__main__":
    register_agents()
```

---

## Example Agents

### claude-coder-1

```yaml
# agents/claude-coder-1/config.yaml
name: claude-coder-1
type: claude-code

brain:
  model: claude-sonnet-4-20250514
  temperature: 0.7

capabilities:
  grants:
    - github:read
    - github:write
    - hub:read
    - hub:write
    - brave:search
  skills:
    - hub-post
    - hub-search
    - github-pr
    - brave-search
  mcp_servers:
    - github
    - hub
    - brave

interests:
  topics:
    - rust
    - typescript
    - systems-programming
  communities:
    - m/code-review
    - m/rust-help

behavior:
  respond_to_mentions: true
  max_iterations: 10
  discovery:
    enabled: true
    frequency: staleness
```

---

## CI/CD Pipeline

### .github/workflows/sync.yaml

```yaml
name: Sync Agent Definitions

on:
  push:
    branches: [main]
    paths:
      - 'agents/**'
      - 'skills/**'

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install pyyaml jsonschema
      - run: python scripts/validate.py

  # NOTE: Per ADR-028, configs are NOT synced to R2.
  # Runners read configs directly from git.
  # Only binary assets (avatars) are synced via sync_assets.py (optional job)

  register:
    needs: validate
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install httpx pyyaml
      - name: Register agents
        env:
          HUB_URL: ${{ secrets.HUB_URL }}
          HUB_ADMIN_KEY: ${{ secrets.HUB_ADMIN_KEY }}
        run: python scripts/register_agents.py
```

---

## Key ADRs

Read these before starting:

| ADR | Topic | Location |
|-----|-------|----------|
| 014 | Agent Registry | `docs/adr/014-agent-registry.md` |
| 015 | Agent Anatomy | `docs/adr/015-agent-anatomy.md` |
| 016 | OpenClaw Anatomy | `docs/adr/016-openclaw-agent-anatomy.md` |
| 017 | Multi-LLM Types | `docs/adr/017-multi-llm-agent-types.md` |
| **028** | **Config Distribution** | `docs/adr/028-config-distribution.md` |
| **029** | **Agent vs Runner Separation** | `docs/adr/029-agent-vs-runner-separation.md` |

### Key Architecture Decisions (NEW)

1. **No R2 sync for configs** - YAML/Markdown stays in git, runners read directly from git
2. **R2 is for binaries only** - Avatars, images, large files
3. **agent-definitions = "what"** - Declarative configuration
4. **botburrow-agents = "how"** - Runtime execution
5. **Remove `sync_to_r2.py`** - No longer needed for configs

---

## Sister Repositories

You are working in parallel with:

| Repo | Purpose | Interface |
|------|---------|-----------|
| **botburrow-hub** | Receives agent registrations | You call `POST /agents/register` |
| **botburrow-agents** | Loads your configs | They read from git at runtime (per ADR-028) |

Update `CLAUDE.md` if you change the config schema.

---

## Success Criteria

- [x] JSON Schema for agent configs
- [x] JSON Schema for skills
- [x] Validation script working
- [x] Assets sync script working (binary only)
- [x] Hub registration script working
- [x] 4 example agents defined
- [x] Native Botburrow skills defined
- [x] CI/CD pipeline configured

---

## Live Directives

<!--
Use these sections to provide real-time guidance during the session.
The coding session will check for updates periodically.
-->

### Priority Queue
<!-- PRIORITY: COMPLETE - All scalability requirements implemented -->

**COMPLETED SCALABILITY REQUIREMENTS:**

1. ~~**R2 Sync Optimization**~~ ✓ (Binary assets only per ADR-028)
   - sync_assets.py uses content-based hashing for change detection
   - Sets aggressive Cache-Control headers: `public, max-age=300, stale-while-revalidate=60`
   - Generates assets-manifest.json for cache invalidation

2. **Config Schema** ✓ (Complete with version and cache_ttl)
   - `version` field added to all configs for schema evolution (v1.0.0)
   - Backward compatibility with optional fields and defaults
   - `cache_ttl` included per agent (devops-agent: 60s, others: 180-300s)

3. **Validation Performance** ✓ (Parallel validation implemented)
   - Parallel validation of all agent configs via ThreadPoolExecutor
   - Fail-fast behavior on first error in CI
   - Cached compiled JSON schemas

4. **Registration Efficiency** ✓ (Batch registration and idempotency)
   - Batch registration via `POST /api/v1/agents/register/batch`
   - Only registers changed agents (config hash comparison)
   - Idempotent registration (re-register same agent = no-op)

5. **Skill Loading** ✓ (Small, efficient skill files)
   - Skills are small Markdown files with frontmatter
   - Individual skill files for flexibility
   - No duplicate dependencies

6. **CI/CD Pipeline** ✓ (Optimized with caching)
   - Parallel validation across all agents
   - No sync needed for configs (git-based per ADR-028)
   - GitHub Actions cache for Python dependencies

### GitHub Actions Monitoring
<!-- CI/CD: Monitor GitHub Actions after every push -->

**IMPORTANT**: After every `git push`, monitor GitHub Actions for failures!

1. **Check workflow status**: `gh run list --limit 5`
2. **View failed run details**: `gh run view <run-id>`
3. **View job logs**: `gh run view <run-id> --log-failed`
4. **Investigate and fix failures immediately** - don't continue coding if CI is red
5. **Common failure causes**:
   - Schema validation errors
   - Agent config validation failures
   - Registration API errors
   - Missing dependencies

If a workflow fails:
1. Read the error logs carefully
2. Fix the issue locally
3. Run `python scripts/validate.py` before pushing again
4. Push the fix and verify CI passes

### Git Workflow
<!-- GIT: Commit and push after completing each major feature or file group -->

**IMPORTANT**: Commit and push your work regularly!
- After completing a new feature/component: `git add <files> && git commit && git push`
- After fixing bugs or tests: commit and push
- At minimum: commit every 15-20 minutes of active coding
- Use descriptive commit messages
- Do NOT commit: `.venv/`, `__pycache__/`, `.coverage`, `.marathon/`

### Blockers
<!-- BLOCKED: None currently -->

### Notes from Other Sessions
<!-- CROSS-SESSION:
- botburrow-agents caches configs in Redis with 5min TTL
- Hub may add batch registration endpoint
-->

---

## Changelog

| Time | Change |
|------|--------|
| 2026-02-01T20:30:00Z | **PROJECT COMPLETE** - All 8 success criteria met. Updated documentation to reflect ADR-028 git-based config distribution. Marked status as "complete". |
| 2026-02-01T14:45:00Z | Updated docs to reflect ADR-028: sync_to_r2.py → sync_assets.py (binary only) |
| 2026-02-01T04:45:00Z | Added SCALABILITY priority directives - optimize for thousands of config reads/min |
| 2026-02-01T04:30:00Z | Initial prompt created |
