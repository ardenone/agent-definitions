# Agent Config Schema Compatibility: Approaches & Trade-offs

**Generated:** 2026-02-07
**Task:** ad-148 - Alternative research for ad-3hn (Validate agent config schema compatibility with runners)
**Status:** Research Complete

---

## Executive Summary

This document analyzes different approaches for maintaining schema compatibility between `agent-definitions` (configuration repository) and `botburrow-agents` (runtime system). The analysis is based on current implementations of both repositories and identifies gaps, risks, and recommended strategies.

**Key Finding:** The current implementation already handles schema compatibility well through manual synchronization and comprehensive field extraction in the GitClient. However, there are several risks and opportunities for improvement.

---

## Current State Analysis

### What Works

1. **Comprehensive Field Extraction**: The `GitClient.load_agent_config()` method in `botburrow-agents` manually extracts all fields from the agent-definitions schema, including nested configs (shell, spawning, discovery, limits, memory).

2. **Schema-First Development**: The `agent-config.schema.json` is the source of truth, and both repositories reference it in comments.

3. **Default Values**: The Pydantic models in `botburrow-agents` provide sensible defaults for all optional fields.

4. **Existing Validation**: `scripts/validate.py` in agent-definitions validates against JSON schema.

### Current Gaps

| Feature | agent-definitions Schema | botburrow-agents Model | Status |
|---------|--------------------------|------------------------|--------|
| `type: "custom"` | Supported | Not explicitly validated | ⚠️ Silent acceptance |
| `type: "native"` enum | Has enum value | Not in model validation | ⚠️ No validation |
| `brain.api_base` | Has field | Model has field, extracts it | ✅ Handled |
| `brain.api_key_env` | Has field | Model has field, extracts it | ✅ Handled |
| `capabilities.mcp_servers` object | Supports object dict | Model accepts `str \| dict` | ✅ Handled |
| `capabilities.shell` | Full config | Model has ShellConfig | ✅ Handled |
| `capabilities.spawning` | Full config | Model has SpawningConfig | ✅ Handled |
| `interests` | Full config | Model has InterestConfig | ✅ Handled |
| `behavior.discovery` | Nested config | Model has DiscoveryConfig | ✅ Handled |
| `behavior.limits` | Nested config | Model has BehaviorLimitsConfig | ✅ Handled |
| `memory` | Full config | Model has MemoryConfig | ✅ Handled |
| Schema version | `version` field exists | Not used for validation | ⚠️ No version checking |

### MCP Server Registry Mismatch

**Problem**: Agent configs reference MCP servers that may not exist in the runner's `BUILTIN_SERVERS` registry.

| Server | In Agent Config | In BUILTIN_SERVERS | Impact |
|--------|-----------------|-------------------|--------|
| `github` | Yes | Yes | ✅ Works |
| `filesystem` | Yes | Yes | ✅ Works |
| `brave-search` | Used in configs | Registry has `brave` | ⚠️ Name mismatch |
| `kubernetes` | Used in configs | No | ❌ Ignored by runner |

---

## Approaches Analysis

### Approach 1: Manual Synchronization (Current)

**Description**: Keep current approach where developers manually update Pydantic models when schema changes.

**Implementation**:
```python
# botburrow-agents/src/botburrow_agents/models.py
# Comments reference the schema version
# Synced with agent-definitions schema v1.0.0

class AgentConfig(BaseModel):
    # Manually keep in sync with schema
    name: str
    type: str = "claude-code"
    # ... all fields manually defined
```

**Pros**:
- ✅ Simple, no tooling overhead
- ✅ Full control over model definitions
- ✅ Can add runner-specific fields (like `r2_path` legacy support)
- ✅ Can maintain backwards compatibility easily
- ✅ Works now

**Cons**:
- ❌ Manual process error-prone
- ❌ No automated validation that models match schema
- ❌ Schema drift can go unnoticed
- ❌ Requires developer discipline to sync
- ❌ No version checking at runtime

**Risk Level**: **Medium** - Works but prone to drift over time

---

### Approach 2: Generate Models from Schema

**Description**: Use a code generator (datamodel-code-generator, pydantic-gen) to generate Pydantic models from JSON schema.

**Implementation**:
```bash
# Generate models from schema
datamodel-codegen \
  --input agent-definitions/schemas/agent-config.schema.json \
  --output botburrow-agents/src/botburrow_agents/models_generated.py \
  --output-model-type pydantic_v2.BaseModel
```

**Pros**:
- ✅ Guaranteed schema-to-model consistency
- ✅ Automated process (can run in CI)
- ✅ Single source of truth (JSON schema)
- ✅ Catch schema changes immediately

**Cons**:
- ❌ Loses custom fields (need mixin pattern)
- ❌ Generated code may need post-processing
- ❌ Adds build step dependency
- ❌ Harder to maintain backwards compatibility
- ❌ Generated code can be verbose/ugly

**Risk Level**: **Low** - But adds complexity

---

### Approach 3: Runtime Schema Validation

**Description**: Validate loaded configs against JSON schema at runtime in the runner.

**Implementation**:
```python
# botburrow-agents/src/botburrow_agents/clients/git.py
import jsonschema

async def load_agent_config(self, agent_id: str) -> AgentConfig:
    config_data = await self.get_agent_config(agent_id)

    # Validate against schema before parsing
    schema = await self._load_schema()
    jsonschema.validate(config_data, schema)

    # Parse with Pydantic
    return AgentConfig(**config_data)
```

**Pros**:
- ✅ Catches schema violations at load time
- ✅ Clear error messages for invalid configs
- ✅ Can use schema for validation in tests
- ✅ Single source of truth enforced at runtime

**Cons**:
- ❌ Performance overhead (JSON schema validation)
- ❌ Requires fetching/storing schema in runner
- ❌ Adds dependency (jsonschema)
- ❌ Validation errors at runtime (vs. CI time)

**Risk Level**: **Low** - Good defense-in-depth

---

### Approach 4: Schema Version Negotiation

**Description**: Use the `version` field in configs to handle backwards/forwards compatibility.

**Implementation**:
```python
# botburrow-agents/src/botburrow_agents/models.py
SUPPORTED_SCHEMA_VERSIONS = {"1.0.0", "1.1.0"}

class AgentConfig(BaseModel):
    version: str | None = None

    def check_version(self) -> None:
        if self.version not in SUPPORTED_SCHEMA_VERSIONS:
            raise ConfigVersionError(
                f"Unsupported schema version: {self.version}. "
                f"Supported: {SUPPORTED_SCHEMA_VERSIONS}"
            )
```

**Pros**:
- ✅ Clear compatibility contract
- ✅ Can support multiple schema versions
- ✅ Graceful degradation for old configs
- ✅ Migration path for breaking changes

**Cons**:
- ❌ Requires maintaining multiple parsers
- ❌ Version management overhead
- ❌ Risk of version sprawl
- ❌ More complex code

**Risk Level**: **Medium** - Adds complexity but useful

---

### Approach 5: Hybrid (Recommended)

**Description**: Combine manual synchronization with runtime validation and version checking.

**Implementation**:
1. Keep manual Pydantic models (for custom fields/compat)
2. Add runtime schema validation (defense-in-depth)
3. Add version checking (fail fast on incompatible)
4. Add CI validation (generate models, compare, warn)

**Components**:
```python
# 1. Version check at load time
async def load_agent_config(self, agent_id: str) -> AgentConfig:
    config_data = await self.get_agent_config(agent_id)
    self._check_schema_version(config_data)

    # 2. Runtime validation (optional, configurable)
    if self.settings.validate_schema:
        self._validate_against_schema(config_data)

    # 3. Parse with Pydantic (existing)
    return self._parse_with_pydantic(config_data)

# 4. CI check: compare schema with models
def verify_schema_sync():
    """Run in CI to warn if schema and models drift."""
    generated = generate_from_schema()
    current = read_current_models()
    diff = compare(generated, current)
    if diff:
        print(f"WARNING: Models may be out of sync with schema")
        print(diff)
```

**Pros**:
- ✅ Best of all worlds
- ✅ Runtime safety without breaking changes
- ✅ CI catches drift early
- ✅ Maintains flexibility for custom fields
- ✅ Can enable/disable runtime validation

**Cons**:
- ⚠️ More moving parts
- ⚠️ Need to maintain CI check
- ⚠️ Slight performance overhead (if runtime validation enabled)

**Risk Level**: **Low** - Most robust approach

---

## MCP Server Configuration Strategies

### Current Problem

Agent configs can reference MCP servers in two ways:

1. **String reference** (shorthand): `mcp_servers: ["github", "brave"]`
2. **Object definition** (inline): `mcp_servers: [{name: "custom", command: "..." }]`

The runner has a `BUILTIN_SERVERS` registry for shorthand references. If an agent references a server not in the registry, it's silently ignored.

### Strategy 1: Strict Registry (Fail Fast)

**Description**: Only allow servers in BUILTIN_SERVERS. Fail on unknown references.

```python
BUILTIN_SERVERS = {
    "github": MCPServerConfig(...),
    "brave": MCPServerConfig(...),
    "filesystem": MCPServerConfig(...),
}

def validate_mcp_servers(servers: list[str | dict]) -> list[MCPServerConfig]:
    for server in servers:
        if isinstance(server, str):
            if server not in BUILTIN_SERVERS:
                raise ValueError(f"Unknown MCP server: {server}")
    # ...
```

**Pros**:
- ✅ Fail fast on bad configs
- ✅ Clear list of supported servers
- ✅ Prevents silent failures

**Cons**:
- ❌ Can't use custom MCP servers
- ❌ Requires registry updates for new servers
- ❌ Breaks agent portability

---

### Strategy 2: Inline Definitions Only (Current, Partial)

**Description**: Allow inline object definitions for custom servers, string references for built-in.

```yaml
mcp_servers:
  - github  # Uses built-in config
  - name: my-custom-server
    command: npx
    args: ["-y", "@myorg/mcp-server"]
```

**Pros**:
- ✅ Supports custom servers
- ✅ Shorthand for common servers
- ✅ Agent configs are self-contained

**Cons**:
- ⚠️ Runner doesn't currently extract inline configs
- ⚠️ Validation mismatch (schema allows, runner doesn't use)

**Fix Required**: Update `GitClient.load_agent_config()` to extract and use inline MCP server configs.

---

### Strategy 3: Alias Support

**Description**: Add alias mapping for common naming mismatches.

```python
MCP_SERVER_ALIASES = {
    "brave-search": "brave",
    "gh": "github",
    "fs": "filesystem",
}

def resolve_mcp_server(name: str) -> str:
    return MCP_SERVER_ALIASES.get(name, name)
```

**Pros**:
- ✅ Backwards compatible
- ✅ Handles naming drift
- ✅ Simple to implement

**Cons**:
- ⚠️ Accumulates technical debt
- ⚠️ Doesn't solve missing servers

---

### Strategy 4: Registry Sync (Recommended)

**Description**: Keep BUILTIN_SERVERS in sync with a registry file in agent-definitions.

```yaml
# agent-definitions/mcp-registry.yml
servers:
  github:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-github"]
    grants: ["github:read", "github:write"]
  brave:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-brave-search"]
    grants: ["brave:search"]
  kubernetes:
    command: mcp-server-kubernetes
    args: []
    grants: ["kubernetes:read", "kubernetes:write"]
```

**Pros**:
- ✅ Single source of truth
- ✅ Shared between repos
- ✅ Can validate in CI
- ✅ Easy to add new servers

**Cons**:
- ❌ Needs sync mechanism (file copy / git submodule)
- ❌ Two repos need to agree on format

---

## Decision Matrix

| Approach | Implementation Effort | Maintenance | Runtime Overhead | Safety | Flexibility | Recommendation |
|----------|----------------------|-------------|------------------|---------|-------------|----------------|
| 1. Manual Sync | Low (current) | Medium | None | Medium | High | Keep as baseline |
| 2. Generate Models | Medium | Low | None | High | Low | CI check only |
| 3. Runtime Validation | Low | Low | Low | High | High | **Recommended** |
| 4. Version Negotiation | Medium | Medium | None | Medium | Medium | Optional add-on |
| 5. Hybrid | High | Medium | Low | **Very High** | High | **Best Overall** |

---

## Recommended Implementation Path

### Phase 1: Immediate (No Breaking Changes)

1. **Add version checking** (low risk, high value):
   ```python
   # In GitClient.load_agent_config()
   if config_version not in SUPPORTED_VERSIONS:
       logger.warning("unsupported_schema_version", version=config_version)
   ```

2. **Fix MCP server name mismatch**:
   - Update `research-agent/config.yaml`: `brave-search` → `brave`
   - Add alias for backwards compatibility

3. **Add CI validation**:
   ```yaml
   # .github/workflows/sync-check.yml
   - name: Check schema-model sync
     run: python scripts/verify-model-sync.py
   ```

### Phase 2: Enhanced Safety (Optional)

4. **Add runtime schema validation** (configurable):
   ```python
   class Settings(BaseSettings):
       validate_schema: bool = False  # Default off for performance
   ```

5. **Add MCP server registry sync**:
   - Create `agent-definitions/mcp-registry.yml`
   - Sync to `botburrow-agents` via copy or git submodule

### Phase 3: Long-term (Future)

6. **Consider model generation** for CI validation:
   - Generate models from schema in CI
   - Compare with actual models
   - Warn on drift

---

## Action Items for Human Decision

### Question 1: Runtime Schema Validation

**Should we add JSON schema validation at config load time?**

- **Option A**: Yes, validate every load (safest, slower)
- **Option B**: Yes, but only in dev/staging (balance)
- **Option C**: No, rely on CI validation (fastest)

**Recommendation**: Option B - Validate in non-production, make configurable.

### Question 2: MCP Server Strategy

**How should we handle MCP servers not in BUILTIN_SERVERS?**

- **Option A**: Fail on unknown servers (strictest)
- **Option B**: Log warning and skip (current)
- **Option C**: Support inline definitions (most flexible)
- **Option D**: Sync registry file (single source of truth)

**Recommendation**: Option C + D - Support inline configs AND sync registry.

### Question 3: Schema Version Enforcement

**Should we enforce schema version checking?**

- **Option A**: Hard fail on unsupported versions
- **Option B**: Log warning and continue
- **Option C**: Ignore version field (current)

**Recommendation**: Option B - Log warning for visibility, don't break agents.

### Question 4: Breaking Changes

**How should we handle breaking schema changes in the future?**

- **Option A**: Increment major version, support multiple versions
- **Option B**: Always maintain backwards compatibility
- **Option C**: Use deprecation period before removing fields

**Recommendation**: Option A + C - Semantic versioning with deprecation.

---

## Conclusion

The current manual synchronization approach works but has risks of drift over time. The recommended path is:

1. **Keep manual sync** for flexibility
2. **Add version checking** for safety
3. **Add runtime validation** (configurable) for defense-in-depth
4. **Add CI checks** to catch drift early
5. **Fix MCP server** handling with inline definitions + registry sync

This hybrid approach provides the best balance of safety, flexibility, and maintainability.

---

**Next Steps**:
1. Review this document and decide on approaches
2. Create implementation beads for approved strategies
3. Close alternative bead ad-148 if choosing different approach
4. Update original bead ad-3hn with implementation plan

---

**Document References**:
- `schemas/agent-config.schema.json` - Source schema
- `botburrow-agents/src/botburrow_agents/models.py` - Pydantic models
- `botburrow-agents/src/botburrow_agents/clients/git.py` - Config loader
- `docs/runner-compatibility-analysis.md` - Previous compatibility analysis
- `tests/test_runner_compatibility.py` - Existing tests
