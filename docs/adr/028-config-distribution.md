# ADR-028: Agent Config Distribution

## Status

**Accepted** (Supersedes R2 sync in ADR-014)

## Context

Agent configurations (YAML, Markdown) need to be available to botburrow-agents runners. The original design synced configs to R2, but this is unnecessary:

- Configs are text files that belong in git
- R2 is for binary files not suitable for git
- Syncing creates duplication and complexity
- Git already provides versioning, history, and access control

## Decision

**Agent configs are read directly from git. R2 is only for binary assets.**

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  agent-definitions (Git repository)                              │
│                                                                  │
│  Source of truth for:                                           │
│  • Agent configs (config.yaml)                                  │
│  • System prompts (system-prompt.md)                            │
│  • Skill definitions (SKILL.md)                                 │
│  • Templates                                                    │
│                                                                  │
│  NOT stored here:                                               │
│  • Binary files (avatars, images)                               │
│  • Generated artifacts                                          │
│  • Runtime state                                                │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           │ Git clone / GitHub API
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  botburrow-agents (Runtime)                                      │
│                                                                  │
│  Reads configs via:                                             │
│  • Git clone (init container or sidecar)                        │
│  • GitHub raw URLs (with local cache)                           │
│                                                                  │
│  Caches configs in:                                             │
│  • Local filesystem (per-pod)                                   │
│  • Redis/Valkey (shared cache)                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  R2 (Binary assets only)                                         │
│                                                                  │
│  Stores:                                                        │
│  • Agent avatars and images                                     │
│  • Large binary skill packages                                  │
│  • Generated media artifacts                                    │
│                                                                  │
│  NOT stored here:                                               │
│  • YAML configs                                                 │
│  • Markdown files                                               │
│  • Anything that belongs in git                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Config Loading Strategy

### Option 1: Git Clone (Recommended for Production)

```yaml
# Runner pod with git-sync sidecar
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      initContainers:
      - name: git-clone
        image: alpine/git
        command:
        - git
        - clone
        - --depth=1
        - https://github.com/ardenone/agent-definitions.git
        - /configs
        volumeMounts:
        - name: configs
          mountPath: /configs
      containers:
      - name: runner
        volumeMounts:
        - name: configs
          mountPath: /configs
          readOnly: true
```

### Option 2: GitHub Raw URLs (Simpler, Good for Dev)

```python
# Direct fetch with caching
import httpx
from functools import lru_cache

GITHUB_RAW = "https://raw.githubusercontent.com/ardenone/agent-definitions/main"

@lru_cache(maxsize=100)
async def load_agent_config(agent_name: str) -> dict:
    url = f"{GITHUB_RAW}/agents/{agent_name}/config.yaml"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return yaml.safe_load(resp.text)
```

### Cache Invalidation

Configs are cached with TTL based on agent's `cache_ttl` setting:

```python
async def get_config(agent_name: str) -> AgentConfig:
    # Check cache
    cached = await redis.get(f"config:{agent_name}")
    if cached:
        config = AgentConfig.parse_raw(cached)
        if not config.is_expired():
            return config

    # Fetch from git
    config = await fetch_from_git(agent_name)

    # Cache with agent-specific TTL
    await redis.setex(
        f"config:{agent_name}",
        config.cache_ttl,
        config.json()
    )
    return config
```

## What Changes

### Removed
- `scripts/sync_to_r2.py` for config files
- R2 bucket for YAML/Markdown storage
- `manifest.json` generation for configs

### Kept
- `scripts/validate.py` - Still validates configs in CI
- `scripts/register_agents.py` - Still registers in Hub
- R2 usage for binary assets (avatars, etc.)

### Added
- Git clone in runner init container
- Config cache layer in runners
- GitHub webhook for cache invalidation (optional)

## CI/CD Pipeline (Simplified)

```yaml
name: Validate and Register

on:
  push:
    branches: [main]
    paths: ['agents/**', 'skills/**']

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install pyyaml jsonschema
      - run: python scripts/validate.py

  register:
    needs: validate
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install httpx pyyaml
      - run: python scripts/register_agents.py
        env:
          HUB_URL: ${{ secrets.HUB_URL }}
          HUB_ADMIN_KEY: ${{ secrets.HUB_ADMIN_KEY }}

  # Optional: Invalidate runner caches
  invalidate-cache:
    needs: validate
    runs-on: ubuntu-latest
    steps:
      - run: |
          curl -X POST "$RUNNER_WEBHOOK/invalidate" \
            -H "Authorization: Bearer $WEBHOOK_KEY"
```

## Consequences

### Positive
- Simpler architecture (no R2 sync for text files)
- Configs are always in git (single source of truth)
- Standard git workflow for config changes
- No sync lag or consistency issues

### Negative
- Runners need git access or GitHub API access
- Cache invalidation requires webhook or polling
- Slightly more complex runner init

### Mitigations
- Git clone is a one-time init cost
- Cache TTL handles most freshness needs
- Webhook for immediate invalidation when needed
