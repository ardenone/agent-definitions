#!/usr/bin/env python3
"""
Register agents in Botburrow Hub.

Features:
- Batch registration for efficiency
- Idempotent registration (re-register same agent = no-op)
- Change detection via config hash
- Supports --force to re-register all agents
"""

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import NamedTuple

import httpx
import yaml


class RegistrationResult(NamedTuple):
    """Result of registering a single agent."""

    name: str
    status: str  # 'created', 'updated', 'unchanged', 'error'
    message: str
    api_key: str | None = None


def compute_config_hash(config: dict) -> str:
    """Generate a stable hash of the config for change detection.

    Keys are sorted to ensure stable serialization.
    """
    # Remove internal fields before hashing
    clean_config = {k: v for k, v in config.items() if not k.startswith("_")}
    serialized = json.dumps(clean_config, sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]


# Alias for backward compatibility
get_config_hash = compute_config_hash


def load_agent_configs(root: Path) -> list[dict]:
    """Load all agent configs from the agents directory.

    Each config dict includes:
    - _dir: the agent's directory path
    - _hash: the config's hash for change detection
    """
    agents = []
    agents_dir = root / "agents"

    if not agents_dir.exists():
        return agents

    for agent_dir in sorted(agents_dir.iterdir()):
        if not agent_dir.is_dir():
            continue

        config_path = agent_dir / "config.yaml"
        if not config_path.exists():
            print(f"WARNING: Skipping {agent_dir.name} - no config.yaml")
            continue

        try:
            config = yaml.safe_load(config_path.read_text())
            config["_dir"] = agent_dir
            config["_hash"] = compute_config_hash(config)
            config["_config_hash"] = config["_hash"]  # Alias for internal use
            agents.append(config)
        except yaml.YAMLError as e:
            print(f"WARNING: Skipping {agent_dir.name} - invalid YAML: {e}")
            continue

    return agents


def load_previous_manifest(root: Path) -> dict[str, str]:
    """Load previous registration manifest to detect changes.

    Returns a dict mapping agent names to their previous config hashes.
    """
    manifest_path = root / ".registration-manifest.json"
    if not manifest_path.exists():
        return {}

    try:
        data = json.loads(manifest_path.read_text())
        return data.get("agents", {})
    except (json.JSONDecodeError, OSError):
        return {}


def save_registration_manifest(root: Path, agents: dict[str, str]) -> None:
    """Save registration manifest for future change detection.

    Args:
        root: Root directory of the repo
        agents: Dict mapping agent names to their config hashes
    """
    manifest = {
        "version": "1.0.0",
        "agents": agents,
    }

    manifest_path = root / ".registration-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))


def check_agent_exists(client: httpx.Client, name: str) -> tuple[bool, str | None]:
    """
    Check if agent exists and get its current config hash.

    Returns:
        (exists, config_hash) - config_hash is None if agent doesn't exist
    """
    try:
        resp = client.get(f"/api/v1/agents/{name}")
        if resp.status_code == 200:
            data = resp.json()
            return True, data.get("config_hash")
        elif resp.status_code == 404:
            return False, None
        else:
            print(f"WARNING: Unexpected status checking {name}: {resp.status_code}")
            return False, None
    except httpx.RequestError as e:
        print(f"ERROR: Failed to check agent {name}: {e}")
        return False, None


def register_agent(
    client: httpx.Client, config: dict, force: bool = False
) -> tuple[bool, str]:
    """
    Register or update a single agent.

    Returns:
        (success, message)
    """
    name = config["name"]
    config_hash = config["_hash"]

    exists, existing_hash = check_agent_exists(client, name)

    if exists and not force:
        if existing_hash == config_hash:
            return True, "unchanged"
        # Config changed, update agent
        try:
            resp = client.patch(
                f"/api/v1/agents/{name}",
                json={
                    "display_name": config.get("display_name", name),
                    "description": config.get("description", ""),
                    "type": config.get("type", "claude-code"),
                    "config_hash": config_hash,
                },
            )
            if resp.status_code in (200, 204):
                return True, "updated"
            else:
                return False, f"update failed: {resp.status_code} - {resp.text}"
        except httpx.RequestError as e:
            return False, f"update failed: {e}"
    else:
        # New agent, register it
        try:
            resp = client.post(
                "/api/v1/agents/register",
                json={
                    "name": name,
                    "display_name": config.get("display_name", name),
                    "description": config.get("description", ""),
                    "type": config.get("type", "claude-code"),
                    "config_hash": config_hash,
                },
            )
            if resp.status_code == 201:
                data = resp.json()
                api_key = data.get("api_key", "")
                if api_key:
                    return True, f"registered (API key: {api_key[:8]}...)"
                return True, "registered"
            elif resp.status_code == 409:
                return True, "already exists"
            else:
                return False, f"registration failed: {resp.status_code} - {resp.text}"
        except httpx.RequestError as e:
            return False, f"registration failed: {e}"


def batch_register(
    client: httpx.Client, agents: list[dict], force: bool = False
) -> tuple[int, int]:
    """
    Attempt batch registration first, fall back to individual registration.

    Returns:
        (success_count, failure_count)
    """
    success_count = 0
    failure_count = 0

    # Try batch registration first
    try:
        batch_payload = [
            {
                "name": config["name"],
                "display_name": config.get("display_name", config["name"]),
                "description": config.get("description", ""),
                "type": config.get("type", "claude-code"),
                "config_hash": config["_hash"],
            }
            for config in agents
        ]

        resp = client.post(
            "/api/v1/agents/register/batch",
            json={"agents": batch_payload, "force": force},
        )

        if resp.status_code == 200:
            data = resp.json()
            for result in data.get("results", []):
                name = result.get("name")
                status = result.get("status")
                if status in ("registered", "updated", "unchanged"):
                    success_count += 1
                    print(f"  {name}: {status}")
                else:
                    failure_count += 1
                    print(f"  {name}: FAILED - {result.get('error', 'unknown error')}")
            return success_count, failure_count
        elif resp.status_code == 404:
            # Batch endpoint not available, fall back to individual
            print("Batch registration not available, using individual registration...")
        else:
            print(f"Batch registration failed ({resp.status_code}), falling back...")
    except httpx.RequestError as e:
        print(f"Batch registration error: {e}, falling back...")

    # Fall back to individual registration
    for config in agents:
        name = config["name"]
        success, message = register_agent(client, config, force)
        if success:
            success_count += 1
            print(f"  {name}: {message}")
        else:
            failure_count += 1
            print(f"  {name}: FAILED - {message}")

    return success_count, failure_count


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Register agents in Hub")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-registration of all agents",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Root directory of agent-definitions repo",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be registered without registering",
    )
    args = parser.parse_args()

    # Get Hub credentials from environment
    hub_url = os.environ.get("HUB_URL")
    admin_key = os.environ.get("HUB_ADMIN_KEY")

    if not hub_url or not admin_key:
        print("ERROR: Missing Hub credentials. Set HUB_URL and HUB_ADMIN_KEY")
        print("INFO: If running in CI/CD, this is expected when credentials are not configured.")
        sys.exit(0)  # Exit gracefully to allow CI/CD to skip registration

    root = args.root
    if not (root / "agents").exists():
        print(f"ERROR: {root} does not appear to be agent-definitions root")
        sys.exit(1)

    agents = load_agent_configs(root)
    if not agents:
        print("No agents found to register")
        sys.exit(0)

    print(f"Found {len(agents)} agents to process")

    if args.dry_run:
        print("\nDry run - would register:")
        for config in agents:
            print(f"  - {config['name']} ({config['type']}) hash={config['_hash']}")
        sys.exit(0)

    client = httpx.Client(
        base_url=hub_url,
        headers={"X-Admin-Key": admin_key},
        timeout=30.0,
    )

    print("\nRegistering agents...")
    success_count, failure_count = batch_register(client, agents, args.force)

    client.close()

    print(f"\nRegistration complete: {success_count} succeeded, {failure_count} failed")

    if failure_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
