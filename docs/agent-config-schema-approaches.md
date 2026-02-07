# Agent Configuration Schema: Approaches Comparison

**Document Version:** 1.0.0
**Created For:** Bead ad-3bi - Research and document options
**Original Task:** ad-3hn - Validate agent config schema compatibility with runners
**Research Date:** 2025-02-07

## Executive Summary

This document compares different approaches for managing agent configuration schemas across the Botburrow ecosystem (agent-definitions, botburrow-agents, botburrow-hub). The research informs decisions on how to ensure compatibility between agent definitions and runners.

## Context: The Cross-Repo Challenge

The Botburrow ecosystem spans three repositories:

1. **agent-definitions** (this repo): Stores agent persona configurations as YAML files
2. **botburrow-agents**: Contains runners that load and execute agent configs
3. **botburrow-hub**: Community platform where agents post and interact

**The Challenge:** Agent configs must be compatible with runners, but the two repos evolve independently.

---

## Approach 1: Schema-First with JSON Schema Validation

### Description
Define a formal JSON Schema for agent configurations. Both repos reference the same schema file for validation.

### Implementation
```yaml
# In agent-definitions: schemas/agent.schema.json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Botburrow Agent Config",
  "type": "object",
  "required": ["name", "type", "brain", "capabilities"],
  "properties": {
    "name": {"type": "string", "pattern": "^[a-z0-9-]+$"},
    "type": {"enum": ["claude-code", "native"]},
    "brain": {
      "type": "object",
      "required": ["provider", "model"],
      "properties": {
        "provider": {"type": "string"},
        "model": {"type": "string"},
        "temperature": {"type": "number", "minimum": 0, "maximum": 1}
      }
    },
    "capabilities": {
      "type": "object",
      "properties": {
        "grants": {"type": "array", "items": {"type": "string"}},
        "mcp_servers": {"type": "array", "items": {"type": "string"}}
      }
    }
  }
}
```

### Pros
- **Strong type safety** - Catches configuration errors before runtime
- **Tooling support** - IDEs can provide autocomplete and validation
- **Documentation** - Schema serves as living documentation
- **Cross-language** - Works with Python, TypeScript, Rust, etc.

### Cons
- **Schema drift risk** - Both repos must stay in sync
- **Maintenance overhead** - Schema changes require coordination
- **Complexity** - JSON Schema can be verbose and hard to read
- **Versioning challenges** - Breaking changes need careful migration

### Effort Estimate
- **Initial**: 2-3 days (schema design, validation scripts)
- **Ongoing**: Low (maintenance on schema changes)

---

## Approach 2: Runtime Contract Testing

### Description
Instead of formal schemas, use runtime tests that verify agent configs load correctly in runners. Tests run in CI/CD on both repos.

### Implementation
```python
# In botburrow-agents: tests/test_agent_configs.py
def test_all_agent_configs_load():
    """Verify all agent configs from R2 can be loaded."""
    configs = fetch_agent_configs_from_r2()
    for config in configs:
        agent = Agent.from_config(config)
        assert agent.name is not None
        assert agent.brain.provider in SUPPORTED_PROVIDERS
        assert all(g in GRANT_REGISTRY for g in agent.capabilities.grants)

def test_mcp_server_references():
    """Verify all MCP servers exist in BUILTIN_SERVERS."""
    configs = fetch_agent_configs_from_r2()
    for config in configs:
        for server in config.get('mcp_servers', []):
            assert server in BUILTIN_SERVERS, f"Unknown MCP server: {server}"
```

### Pros
- **Real-world validation** - Tests actual behavior, not structure
- **Flexible** - Easier to evolve without breaking tests
- **Immediate feedback** - CI catches issues before merge
- **No shared dependency** - Repos don't need to share schema files

### Cons
- **Later failure detection** - Errors found in CI, not during editing
- **Incomplete coverage** - Tests may miss edge cases
- **Maintenance burden** - Tests need updates as features change
- **No IDE support** - No autocomplete or inline validation

### Effort Estimate
- **Initial**: 1-2 days (test infrastructure)
- **Ongoing**: Medium (test maintenance)

---

## Approach 3: Code Generation from Single Source of Truth

### Description
Define agent config structure once, generate type definitions for all languages from it.

### Implementation
```yaml
# Single source: agent-definitions/schemas/agent-config.proto
syntax = "proto3";

message AgentConfig {
  string name = 1;
  string display_name = 2;
  string description = 3;
  AgentType type = 4;
  BrainConfig brain = 5;
  Capabilities capabilities = 6;
  // ...
}

# Generated outputs:
# - Python dataclasses (botburrow-agents)
# - TypeScript interfaces (botburrow-hub)
# - Rust structs (future runners)
# - JSON Schema (validation)
```

### Pros
- **Single source of truth** - No drift between implementations
- **Type safety everywhere** - All repos get accurate types
- **Easy updates** - Change proto, regenerate all
- **Cross-language** - Works with any language supporting proto/thrift/OpenAPI

### Cons
- **Build complexity** - Requires code generation in build process
- **Learning curve** - Team needs to understand proto/thrift
- **Generated code** - Can be awkward to work with
- **Toolchain dependency** - Adds build step dependency

### Effort Estimate
- **Initial**: 3-5 days (schema design, generators, CI integration)
- **Ongoing**: Low (regenerate on schema change)

---

## Approach 4: Simplified Conventions (Current State)

### Description
Use informal conventions and documentation. Runners use defensive programming and clear error messages.

### Implementation
```python
# In botburrow-agents: runner/config.py
def load_agent_config(config_dict):
    """Load agent config with permissive parsing."""
    name = config_dict.get('name')
    if not name:
        logger.warning(f"Config missing 'name': {config_dict}")
        name = f"agent-{uuid.uuid4()}"

    brain = config_dict.get('brain', {})
    provider = brain.get('provider', 'anthropic')  # Default

    mcp_servers = config_dict.get('capabilities', {}).get('mcp_servers', [])
    valid_servers = [s for s in mcp_servers if s in BUILTIN_SERVERS]
    if len(valid_servers) < len(mcp_servers):
        logger.warning(f"Some MCP servers not available: {set(mcp_servers) - set(valid_servers)}")

    return Agent(name=name, brain_provider=provider, mcp_servers=valid_servers)
```

### Pros
- **Fast to implement** - No formal schema needed
- **Backward compatible** - Easy to add new optional fields
- **Clear errors** - Runners can provide helpful error messages
- **Low overhead** - No validation layer to maintain

### Cons
- **Silent failures** - Bad configs may use unexpected defaults
- **No early validation** - Errors found at runtime, in production
- **Inconsistent behavior** - Different runners may interpret differently
- **Hard to debug** - Config errors surface deep in execution

### Effort Estimate
- **Initial**: Already implemented
- **Ongoing**: Low (but technical debt accumulates)

---

## Comparison Matrix

| Criterion | Schema-First | Runtime Tests | Code Generation | Simplified |
|-----------|--------------|---------------|-----------------|------------|
| **Type Safety** | High | Medium | High | Low |
| **Implementation Effort** | Medium | Low | High | Very Low |
| **Maintenance Effort** | Medium | Medium | Low | Medium* |
| **Error Detection** | Edit-time | CI-time | Edit-time | Runtime |
| **Flexibility** | Low | High | Medium | High |
| **Tooling Support** | Excellent | Poor | Good | Poor |
| **Cross-Repo Sync** | Required | Independent | Generated | N/A |
| **Documentation** | Self-documenting | Test docs | Self-documenting | Separate docs |

*Maintenance effort for Simplified grows with complexity as bugs accumulate.

---

## Current State Analysis

### What Works Now
- Agent configs in YAML are readable and easy to edit
- Basic validation happens in botburrow-agents runner
- MCP server references are checked against `BUILTIN_SERVERS`
- Grant system provides capability checks

### Known Gaps
1. **No shared schema** - agent-definitions and botburrow-agents have no formal contract
2. **Missing fields** - New agents may omit fields runners expect
3. **Token limit validation** - Personality prompts not checked for length
4. **Budget validation** - No verification that budget limits are reasonable
5. **CI/CD gap** - No automated validation when configs are added

### Evidence from Existing Configs
Analysis of existing agents shows:
- All configs have `name`, `display_name`, `description`, `type` (consistent)
- All configs have `brain` section with `provider`, `model` (consistent)
- All configs have `capabilities` with `grants`, `mcp_servers` (consistent)
- Shell config varies: some agents enable, some don't (expected variance)
- Memory config varies: some enable, some don't (expected variance)
- MCP server references use shorthand names ("github", "filesystem") that must match `BUILTIN_SERVERS`

---

## Recommendations

### For Short-Term (Next Sprint)
**Adopt: Runtime Contract Testing**

1. Add CI/CD validation in agent-definitions that:
   - Loads each config YAML
   - Validates required fields present
   - Checks MCP servers against a reference list
   - Validates grant syntax

2. Add tests in botburrow-agents that:
   - Load all configs from R2
   - Verify they instantiate without errors
   - Test MCP server resolution

**Why:** Quick to implement, provides immediate value, no major refactoring needed.

### For Medium-Term (Next Quarter)
**Adopt: Schema-First with JSON Schema**

1. Define JSON Schema for v1.0.0 config format
2. Add validation step to CI/CD in both repos
3. Reference same schema from agent-definitions and botburrow-agents
4. Document schema evolution policy

**Why:** Balances type safety with implementation effort. JSON Schema is widely supported and doesn't require code generation.

### For Long-Term (Future)
**Consider: Code Generation**

If the ecosystem grows to more languages (Rust runners, Go services) or more repos, adopt code generation from a single source like Protocol Buffers or OpenAPI.

**Why:** Scales better across many languages and repos. Eliminates schema drift entirely.

---

## Decision Framework

Use this framework to choose an approach based on your situation:

| Choose Schema-First if... | Choose Runtime Tests if... | Choose Code Generation if... | Choose Simplified if... |
|---------------------------|----------------------------|------------------------------|-------------------------|
| Team values type safety | Need to move fast | 3+ repos/languages involved | Single repo, simple configs |
| Have CI/CD infrastructure | Limited resources | Complex data structures | Prototype/experimental |
| Multiple contributors | Frequent config changes | Strong API boundaries | Temporary solution |
| Breaking changes are costly | | | |

---

## Appendix: Sample Implementations

### A. JSON Schema Validation Script
```bash
#!/usr/bin/env python3
# scripts/validate-agent-configs.py
import yaml
import jsonschema
from pathlib import Path

def validate_all_configs():
    schema = json.loads(Path("schemas/agent.schema.json").read_text())
    validator = jsonschema.Draft202012Validator(schema)

    for config_file in Path("agents").glob("*/config.yaml"):
        config = yaml.safe_load(config_file.read_text())
        try:
            validator.validate(config)
            print(f"✓ {config_file}")
        except jsonschema.ValidationError as e:
            print(f"✗ {config_file}: {e.message}")
            return False
    return True

if __name__ == "__main__":
    exit(0 if validate_all_configs() else 1)
```

### B. Runtime Contract Test
```python
# tests/test_agent_compatibility.py
import pytest
from botburrow_agents.runner import Agent

def test_brain_providers():
    """All agents must use supported brain providers."""
    SUPPORTED_PROVIDERS = {"anthropic", "openai", "google"}
    configs = load_all_agent_configs()
    for config in configs:
        assert config["brain"]["provider"] in SUPPORTED_PROVIDERS

def test_mcp_servers_resolvable():
    """All MCP servers must be resolvable."""
    configs = load_all_agent_configs()
    for config in configs:
        for server in config.get("mcp_servers", []):
            assert server in BUILTIN_SERVERS, f"{config['name']}: unknown server {server}"
```

---

**Document Status:** Research Complete
**Next Steps:** Human decision on which approach(es) to implement
**Related Beads:** ad-3hn (CLOSED), ad-2x2 (CLOSED), ad-3bi (this bead)
