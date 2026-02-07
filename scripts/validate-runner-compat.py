#!/usr/bin/env python3
"""
Validate agent configs for botburrow-agents runner compatibility.

This script checks:
1. JSON schema validation (via validate.py)
2. MCP server references exist in runner's BUILTIN_SERVERS
3. Required fields for specific agent types (e.g., native needs api_base)
4. Shell/spawning config validation
5. System prompt token limits
6. Behavior limits are reasonable

Usage:
    python scripts/validate-runner-compat.py [--root PATH] [--fail-fast]
"""

import argparse
import sys
from pathlib import Path

import yaml

# BUILTIN_SERVERS from botburrow-agents mcp/manager.py
BUILTIN_SERVERS = {
    "github": {
        "name": "github",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "grants": ["github:read", "github:write"],
    },
    "brave": {
        "name": "brave-search",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "grants": ["brave:search"],
    },
    "filesystem": {
        "name": "filesystem",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem"],
        "grants": ["filesystem:read", "filesystem:write"],
    },
    "postgres": {
        "name": "postgres",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-postgres"],
        "grants": ["postgres:read", "postgres:write"],
    },
    "hub": {
        "name": "hub",
        "command": "python",
        "args": ["-m", "botburrow_agents.mcp.servers.hub"],
        "grants": ["hub:read", "hub:write"],
    },
}


class ValidationError:
    """A validation error with context."""

    def __init__(self, agent_id: str, field: str, message: str, severity: str = "error"):
        self.agent_id = agent_id
        self.field = field
        self.message = message
        self.severity = severity  # error, warning, info

    def __str__(self):
        severity_str = self.severity.upper().ljust(7)
        return f"{severity_str} [{self.agent_id}] {self.field}: {self.message}"


def estimate_tokens(text: str) -> int:
    """Rough token estimation (1 token ≈ 4 characters)."""
    return len(text) // 4


def validate_mcp_servers(agent_id: str, config: dict) -> list[ValidationError]:
    """Validate MCP server references exist in BUILTIN_SERVERS."""
    errors = []

    mcp_servers = config.get("capabilities", {}).get("mcp_servers", [])

    for server in mcp_servers:
        server_name = None

        # Handle both string and object formats
        if isinstance(server, str):
            server_name = server
        elif isinstance(server, dict):
            server_name = server.get("name", "")

        # Check if server exists in BUILTIN_SERVERS
        if server_name not in BUILTIN_SERVERS:
            # Check common aliases
            aliases = {
                "brave-search": "brave",
                "github": "github",
                "filesystem": "filesystem",
                "postgres": "postgres",
                "hub": "hub",
                "kubernetes": None,  # Not in builtin
            }

            if server_name in aliases:
                suggested = aliases[server_name]
                if suggested:
                    errors.append(ValidationError(
                        agent_id,
                        "mcp_servers",
                        f"Server '{server_name}' not in BUILTIN_SERVERS. "
                        f"Use '{suggested}' instead.",
                        severity="warning"
                    ))
                else:
                    errors.append(ValidationError(
                        agent_id,
                        "mcp_servers",
                        f"Server '{server_name}' not in BUILTIN_SERVERS "
                        f"and no alias known.",
                        severity="warning"
                    ))
            else:
                errors.append(ValidationError(
                    agent_id,
                    "mcp_servers",
                    f"Server '{server_name}' not in BUILTIN_SERVERS.",
                    severity="warning"
                ))

    return errors


def validate_native_agent_config(agent_id: str, config: dict) -> list[ValidationError]:
    """Validate native-type agent has required fields."""
    errors = []

    if config.get("type") != "native":
        return errors

    brain = config.get("brain", {})

    # Native agents need api_base and api_key_env for custom providers
    if brain.get("provider") not in ["anthropic", "openai"]:
        if not brain.get("api_base"):
            errors.append(ValidationError(
                agent_id,
                "brain.api_base",
                "Native agents with custom providers need 'api_base' in brain config.",
                severity="error"
            ))

    # Check if api_base is set but model doesn't support it
    if brain.get("api_base") and brain.get("provider") == "anthropic":
        errors.append(ValidationError(
            agent_id,
            "brain.api_base",
            "api_base set but provider is 'anthropic'. Anthropic doesn't support custom api_base.",
            severity="warning"
        ))

    return errors


def validate_shell_config(agent_id: str, config: dict) -> list[ValidationError]:
    """Validate shell configuration is reasonable."""
    errors = []

    shell = config.get("capabilities", {}).get("shell", {})

    if not shell.get("enabled", False):
        return errors

    timeout = shell.get("timeout_seconds", 120)
    if timeout < 1:
        errors.append(ValidationError(
            agent_id,
            "capabilities.shell.timeout_seconds",
            f"timeout_seconds ({timeout}) must be at least 1.",
            severity="error"
        ))
    elif timeout > 3600:
        errors.append(ValidationError(
            agent_id,
            "capabilities.shell.timeout_seconds",
            f"timeout_seconds ({timeout}) exceeds 3600 (1 hour).",
            severity="warning"
        ))

    # Check blocked_patterns for dangerous commands
    blocked = shell.get("blocked_patterns", [])
    dangerous_patterns = ["rm -rf", "sudo", "format", "mkfs"]
    for pattern in dangerous_patterns:
        if pattern not in str(blocked):
            errors.append(ValidationError(
                agent_id,
                "capabilities.shell.blocked_patterns",
                f"Consider blocking dangerous pattern: '{pattern}'",
                severity="info"
            ))

    return errors


def validate_behavior_limits(agent_id: str, config: dict) -> list[ValidationError]:
    """Validate behavior limits are reasonable."""
    errors = []

    behavior = config.get("behavior", {})
    limits = behavior.get("limits", {})

    # Check max_iterations
    max_iter = behavior.get("max_iterations", 10)
    if max_iter > 50:
        errors.append(ValidationError(
            agent_id,
            "behavior.max_iterations",
            f"max_iterations ({max_iter}) exceeds 50. May cause runaway agents.",
            severity="warning"
        ))

    # Check daily limits
    max_posts = limits.get("max_daily_posts", 5)
    if max_posts > 100:
        errors.append(ValidationError(
            agent_id,
            "behavior.limits.max_daily_posts",
            f"max_daily_posts ({max_posts}) is very high.",
            severity="info"
        ))

    # Check min_interval
    min_interval = limits.get("min_interval_seconds", 60)
    if min_interval < 10:
        errors.append(ValidationError(
            agent_id,
            "behavior.limits.min_interval_seconds",
            f"min_interval_seconds ({min_interval}) is very low. May spam.",
            severity="warning"
        ))

    return errors


def validate_system_prompt(agent_id: str, agent_dir: Path) -> list[ValidationError]:
    """Validate system prompt exists and is within token limits."""
    errors = []

    prompt_path = agent_dir / "system-prompt.md"

    if not prompt_path.exists():
        errors.append(ValidationError(
            agent_id,
            "system-prompt.md",
            "System prompt file not found.",
            severity="error"
        ))
        return errors

    content = prompt_path.read_text()
    tokens = estimate_tokens(content)

    # System prompts should be concise (< 2000 tokens ≈ 8000 chars)
    if tokens > 2000:
        errors.append(ValidationError(
            agent_id,
            "system-prompt.md",
            f"System prompt is ~{tokens} tokens. Consider reducing to < 2000 for efficiency.",
            severity="warning"
        ))

    if len(content) < 50:
        errors.append(ValidationError(
            agent_id,
            "system-prompt.md",
            "System prompt is very short (< 50 chars).",
            severity="info"
        ))

    return errors


def validate_agent_config(agent_dir: Path) -> list[ValidationError]:
    """Validate a single agent for runner compatibility."""
    errors = []
    agent_id = agent_dir.name
    config_path = agent_dir / "config.yaml"

    if not config_path.exists():
        errors.append(ValidationError(
            agent_id,
            "config.yaml",
            "Config file not found.",
            severity="error"
        ))
        return errors

    try:
        config = yaml.safe_load(config_path.read_text())
    except yaml.YAMLError as e:
        errors.append(ValidationError(
            agent_id,
            "config.yaml",
            f"Invalid YAML: {e}",
            severity="error"
        ))
        return errors

    # Run all validations
    errors.extend(validate_mcp_servers(agent_id, config))
    errors.extend(validate_native_agent_config(agent_id, config))
    errors.extend(validate_shell_config(agent_id, config))
    errors.extend(validate_behavior_limits(agent_id, config))
    errors.extend(validate_system_prompt(agent_id, agent_dir))

    return errors


def validate_all(
    root: Path,
    fail_fast: bool = False,
) -> tuple[list[ValidationError], int]:
    """
    Validate all agents for runner compatibility.

    Returns:
        Tuple of (errors, agent_count)
    """
    agents_dir = root / "agents"

    if not agents_dir.exists():
        print(f"WARNING: {agents_dir} does not exist")
        return [], 0

    agent_dirs = [d for d in agents_dir.iterdir() if d.is_dir()]

    all_errors = []
    agent_count = 0

    for agent_dir in agent_dirs:
        agent_count += 1
        errors = validate_agent_config(agent_dir)
        all_errors.extend(errors)

        if fail_fast and any(e.severity == "error" for e in errors):
            break

    return all_errors, agent_count


def main():
    parser = argparse.ArgumentParser(
        description="Validate agent configs for botburrow-agents runner compatibility"
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Exit on first error",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Root directory of agent-definitions repo",
    )
    parser.add_argument(
        "--severity",
        choices=["error", "warning", "info", "all"],
        default="error",
        help="Minimum severity to display",
    )
    args = parser.parse_args()

    root = args.root
    if not (root / "schemas").exists():
        print(f"ERROR: {root} does not appear to be agent-definitions root")
        sys.exit(1)

    severity_order = {"error": 0, "warning": 1, "info": 2, "all": 3}
    min_severity = severity_order[args.severity]

    all_errors, agent_count = validate_all(root, fail_fast=args.fail_fast)

    # Filter by severity
    filtered_errors = [
        e for e in all_errors
        if severity_order.get(e.severity, 0) <= min_severity
    ]

    if filtered_errors:
        print(f"Validation found {len(filtered_errors)} issue(s):")
        for error in filtered_errors:
            print(f"  {error}")

        # Exit with error if there are error-severity issues
        if any(e.severity == "error" for e in filtered_errors):
            sys.exit(1)
    else:
        print(f"All agents compatible with runner! ({agent_count} agents)")
        if all_errors:
            # Show lower severity messages
            warnings = [e for e in all_errors if e.severity in ["warning", "info"]]
            if warnings:
                print(f"\nAdditional notes ({len(warnings)}):")
                for w in warnings:
                    print(f"  {w}")


if __name__ == "__main__":
    main()
