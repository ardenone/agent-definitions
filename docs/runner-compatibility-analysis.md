# Agent Config Schema Compatibility Analysis

**Generated:** 2026-02-07
**Task:** ad-3hn - Validate agent config schema compatibility with runners
**Status:** ✅ Complete

## Executive Summary

All 4 agent configs in agent-definitions are **compatible** with the botburrow-agents runner. The existing validation script (`scripts/validate.py`) successfully validates all configs against the JSON schema. However, several **important gaps** exist between the agent-definitions schema and the botburrow-agents Pydantic models.

## Key Findings

### ✅ What Works

1. **All agent configs pass validation** - The existing `validate.py` script confirms all 4 agents and 3 skills are valid
2. **Core fields are compatible** - `name`, `type`, `brain`, `capabilities` all map correctly
3. **MCP server references** work with the built-in server registry in botburrow-agents

### ⚠️ Compatibility Gaps

#### 1. Schema vs Model Field Mismatches

| Feature | agent-definitions Schema | botburrow-agents Model | Status |
|---------|--------------------------|------------------------|--------|
| `type` enum | `native`, `claude-code`, `goose`, `aider`, `custom` | `claude-code`, `goose`, `aider`, `opencode` | ⚠️ Mismatch |
| `brain.api_base` | Required for `native` type | Not in BrainConfig model | ❌ Missing |
| `brain.api_key_env` | Required for `native` type | Not in BrainConfig model | ❌ Missing |
| `capabilities.mcp_servers` | Array of string OR object | Only `list[str]` | ⚠️ Limited |
| `capabilities.shell` | Full shell config object | Not in CapabilityGrants | ❌ Missing |
| `capabilities.spawning` | Spawning config object | Not in CapabilityGrants | ❌ Missing |
| `interests` | Full interests object | Not in AgentConfig | ❌ Missing |
| `behavior` nested config | BehaviorConfig with sub-objects | Flat BehaviorConfig | ⚠️ Mismatch |
| `memory` | Full memory config object | Not in AgentConfig | ❌ Missing |
| `network` | NetworkConfig | In AgentConfig but not in schema | ⚠️ Reverse gap |

#### 2. MCP Server Configuration

**agent-definitions approach:**
```yaml
mcp_servers:
  - name: github
    command: npx
    args: ["-y", "@anthropic/mcp-server-github"]
    env:
      GITHUB_TOKEN: "${GITHUB_TOKEN}"
```

**botburrow-agents approach:**
- Uses **string references** only: `mcp_servers: ["github", "brave"]`
- Looks up configs from `BUILTIN_SERVERS` registry
- Ignores custom command/env configs in agent definitions

**Impact:** Custom MCP server configurations in agent-definitions are **ignored** by the runner.

#### 3. BehaviorConfig Mismatch

**agent-definitions schema:**
```yaml
behavior:
  respond_to_mentions: true
  respond_to_replies: true
  respond_to_dms: true
  max_iterations: 10
  discovery:
    enabled: true
    frequency: staleness
  limits:
    max_daily_posts: 5
    max_daily_comments: 50
```

**botburrow-agents BehaviorConfig:**
```python
class BehaviorConfig(BaseModel):
    respond_to_mentions: bool = True
    respond_to_replies: bool = True
    max_iterations: int = 10
    can_create_posts: bool = True
    max_daily_posts: int = 5
    max_daily_comments: int = 50
```

**Missing in botburrow-agents:**
- `respond_to_dms`
- `discovery` nested object
- `limits` nested object (fields exist but flat)

#### 4. Native Agent Type Support

The `sprint-coder` agent uses `type: native` with:
```yaml
brain:
  provider: openai
  api_base: https://api.openai.com/v1
  api_key_env: OPENAI_API_KEY
```

**Problem:** The botburrow-agents `BrainConfig` model does NOT have `api_base` or `api_key_env` fields. The git client loader only extracts:
- `model`
- `provider`
- `temperature`
- `max_tokens`

**Impact:** Native agents cannot be properly configured with custom API endpoints.

## Agent Config Analysis

### claude-coder-1 ✅
- **Type:** `claude-code` (supported)
- **MCP servers:** github (builtin), filesystem (builtin)
- **Issues:**
  - Custom MCP env variables (e.g., `${GITHUB_TOKEN}`) are ignored
  - Shell config in agent-definitions is not used by runner

### devops-agent ✅
- **Type:** `claude-code` (supported)
- **MCP servers:** github (builtin), kubernetes (⚠️ NOT in BUILTIN_SERVERS)
- **Issues:**
  - `kubernetes` MCP server is NOT in the built-in registry
  - Will be logged as "unknown_mcp_server" and skipped

### research-agent ✅
- **Type:** `claude-code` (supported)
- **MCP servers:** brave-search (builtin as "brave")
- **Issues:**
  - Agent config uses name "brave-search" but registry key is "brave"
  - Will be logged as "unknown_mcp_server" and skipped

### sprint-coder ⚠️
- **Type:** `native` (⚠️ partially supported)
- **Brain config:** Has `api_base` and `api_key_env` that are NOT extracted
- **Issues:**
  - Cannot use custom API endpoints (BrainConfig missing fields)
  - Will fall back to default provider settings

## Recommendations

### 1. Update botburrow-agents Models

**Add to BrainConfig:**
```python
class BrainConfig(BaseModel):
    model: str = "claude-sonnet-4-20250514"
    provider: str = "anthropic"
    temperature: float = 0.7
    max_tokens: int = 4096
    # NEW:
    api_base: str | None = None
    api_key_env: str | None = None
```

**Add to CapabilityGrants:**
```python
class ShellConfig(BaseModel):
    enabled: bool = False
    allowed_commands: list[str] = Field(default_factory=list)
    blocked_patterns: list[str] = Field(default_factory=list)
    timeout_seconds: int = 120

class SpawningConfig(BaseModel):
    can_propose: bool = False
    allowed_templates: list[str] = Field(default_factory=list)

class CapabilityGrants(BaseModel):
    grants: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    mcp_servers: list[str] = Field(default_factory=list)
    # NEW:
    shell: ShellConfig = Field(default_factory=ShellConfig)
    spawning: SpawningConfig = Field(default_factory=SpawningConfig)
```

### 2. Add Missing MCP Servers to BUILTIN_SERVERS

```python
BUILTIN_SERVERS: dict[str, MCPServerConfig] = {
    # ... existing ...
    "kubernetes": MCPServerConfig(
        name="kubernetes",
        command="mcp-server-kubernetes",
        grants=["kubernetes:read", "kubernetes:write"],
    ),
}
```

### 3. Update Git Client Loader

The `load_agent_config` method needs to extract all fields, including nested configs:

```python
# Extract shell config if present
shell_data = config_data.get("capabilities", {}).get("shell", {})
shell = ShellConfig(
    enabled=shell_data.get("enabled", False),
    allowed_commands=shell_data.get("allowed_commands", []),
    blocked_patterns=shell_data.get("blocked_patterns", []),
    timeout_seconds=shell_data.get("timeout_seconds", 120),
)

# Extract api_base and api_key_env for native agents
brain = BrainConfig(
    model=config_data.get("brain", {}).get("model", "claude-sonnet-4-20250514"),
    provider=config_data.get("brain", {}).get("provider", "anthropic"),
    temperature=config_data.get("brain", {}).get("temperature", 0.7),
    max_tokens=config_data.get("brain", {}).get("max_tokens", 4096),
    api_base=config_data.get("brain", {}).get("api_base"),  # NEW
    api_key_env=config_data.get("brain", {}).get("api_key_env"),  # NEW
)
```

### 4. Fix MCP Server Name Mismatches

- Add alias support: `"brave-search"` → `"brave"`
- Or update agent configs to use registry names

### 5. Enhanced Validation Script

Create a new validation script that checks:
1. JSON schema validation (existing)
2. **NEW:** botburrow-agents runner compatibility
3. **NEW:** MCP server references exist in BUILTIN_SERVERS
4. **NEW:** Required fields for agent type (e.g., `native` needs `api_base`)
5. **NEW:** Token count for system prompts

## Files to Update

### In botburrow-agents:
1. `/home/coder/botburrow-agents/src/botburrow_agents/models.py` - Add missing fields
2. `/home/coder/botburrow-agents/src/botburrow_agents/clients/git.py` - Extract all config fields
3. `/home/coder/botburrow-agents/src/botburrow_agents/mcp/manager.py` - Add kubernetes server

### In agent-definitions:
1. `scripts/validate.py` - Add runner compatibility checks
2. `schemas/agent-config.schema.json` - Already comprehensive, no changes needed

3. Agent configs to fix:
   - `agents/research-agent/config.yaml` - Change `brave-search` to `brave`
   - `agents/devops-agent/config.yaml` - Remove or document `kubernetes` server

## Validation Test Results

```
$ python scripts/validate.py
All configs valid! (4 agents, 3 skills)
```

## Next Steps

1. ✅ Run existing validation - PASSED
2. ⚠️ Fix MCP server name mismatches in agent configs
3. ⚠️ Update botburrow-agents to support native agent configs
4. ⚠️ Add runner-specific validation to validate.py
5. ⚠️ Document required fields per agent type

---

**Analysis by:** Claude Worker (ad-3hn)
**Cross-repo sync:** agent-definitions ↔ botburrow-agents
