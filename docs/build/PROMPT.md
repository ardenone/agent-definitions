<!--
_meta:
  updated: 2026-02-01T14:30:00Z
  version: 1.2.0
  status: active
-->

<!-- HOT RELOAD: Re-read this file periodically. Check _meta.updated for changes. -->

# Agent Definitions - Marathon Coding Session

<!-- CURRENT FOCUS: Initial project setup, schemas, and validation scripts -->

---

## Mission

Build **agent-definitions**, the source of truth for Botburrow agent configurations. This repo syncs to R2 and registers agents in the Hub.

## Deliverables

1. **Config Schema** - JSON Schema for agent configs
2. **Validation Scripts** - Validate configs before sync
3. **Sync Scripts** - Push configs to R2
4. **Registration Scripts** - Register agents in Hub
5. **Example Agents** - Working agent definitions
6. **CI/CD Pipeline** - Automate validation and sync

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  AGENT DEFINITIONS FLOW                                              │
│                                                                      │
│  ┌───────────────────┐                                              │
│  │  Git Repository   │  (source of truth)                          │
│  │  agents/          │                                              │
│  │  ├── claude-coder │                                              │
│  │  ├── research-bot │                                              │
│  │  └── devops-agent │                                              │
│  └─────────┬─────────┘                                              │
│            │                                                         │
│            │ CI/CD on push                                          │
│            ▼                                                         │
│  ┌───────────────────┐     ┌───────────────────┐                   │
│  │  Validate         │────▶│  Sync to R2       │                   │
│  │  (JSON Schema)    │     │                   │                   │
│  └───────────────────┘     └─────────┬─────────┘                   │
│                                      │                              │
│                                      ▼                              │
│  ┌───────────────────┐     ┌───────────────────┐                   │
│  │  Cloudflare R2    │     │  Register in Hub  │                   │
│  │  (runtime copy)   │     │  POST /agents     │                   │
│  └───────────────────┘     └───────────────────┘                   │
│                                                                      │
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
│   ├── sync_to_r2.py
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

### sync_to_r2.py

```python
#!/usr/bin/env python3
"""Sync agent definitions to R2."""

import boto3
from pathlib import Path

def sync_to_r2():
    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY"],
        aws_secret_access_key=os.environ["R2_SECRET_KEY"],
    )

    bucket = "botburrow-agents"

    # Sync agents
    for agent_dir in Path("agents").iterdir():
        if agent_dir.is_dir():
            for file in agent_dir.glob("*"):
                key = f"agents/{agent_dir.name}/{file.name}"
                s3.upload_file(str(file), bucket, key)
                print(f"Uploaded {key}")

    # Sync skills
    for skill_dir in Path("skills").iterdir():
        if skill_dir.is_dir():
            for file in skill_dir.glob("*"):
                key = f"skills/{skill_dir.name}/{file.name}"
                s3.upload_file(str(file), bucket, key)
                print(f"Uploaded {key}")

if __name__ == "__main__":
    sync_to_r2()
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

  sync:
    needs: validate
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install boto3 pyyaml
      - name: Sync to R2
        env:
          R2_ENDPOINT: ${{ secrets.R2_ENDPOINT }}
          R2_ACCESS_KEY: ${{ secrets.R2_ACCESS_KEY }}
          R2_SECRET_KEY: ${{ secrets.R2_SECRET_KEY }}
        run: python scripts/sync_to_r2.py

  register:
    needs: sync
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
| **botburrow-agents** | Loads your configs | They read from R2 at runtime |

Update `CLAUDE.md` if you change the config schema.

---

## Success Criteria

- [ ] JSON Schema for agent configs
- [ ] JSON Schema for skills
- [ ] Validation script working
- [ ] R2 sync script working
- [ ] Hub registration script working
- [ ] 3 example agents defined
- [ ] Native Botburrow skills defined
- [ ] CI/CD pipeline configured

---

## Live Directives

<!--
Use these sections to provide real-time guidance during the session.
The coding session will check for updates periodically.
-->

### Priority Queue
<!-- PRIORITY: SCALABILITY - Configs will be read thousands of times per minute -->

**CRITICAL SCALABILITY REQUIREMENTS:**

1. **R2 Sync Optimization**
   - Use content-based hashing for change detection (don't re-upload unchanged)
   - Set aggressive Cache-Control headers: `public, max-age=300, stale-while-revalidate=60`
   - Sync produces a manifest.json with all agent hashes for bulk cache invalidation

2. **Config Schema**
   - Add `version` field to all configs for schema evolution
   - Design for backward compatibility (new fields optional with defaults)
   - Include `cache_ttl` per agent (some agents need fresher configs)

3. **Validation Performance**
   - Parallel validation of all agent configs
   - Exit early on first error in CI (fail fast)
   - Cache compiled JSON schemas

4. **Registration Efficiency**
   - Batch registration: `POST /api/v1/agents/register/batch` (coordinate with Hub)
   - Only register changed agents (compare with previous manifest)
   - Idempotent registration (re-register same agent = no-op)

5. **Skill Loading**
   - Skills are loaded by runners - ensure small file sizes
   - Consider bundling related skills into single file
   - Add skill dependencies to avoid duplicate fetches

6. **CI/CD Pipeline**
   - Validate in parallel across all agents
   - Sync only changed files (delta sync)
   - Use GitHub Actions cache for faster runs

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
| 2026-02-01T04:45:00Z | Added SCALABILITY priority directives - optimize for thousands of config reads/min |
| 2026-02-01T04:30:00Z | Initial prompt created |
