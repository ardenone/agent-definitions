"""Tests for register_agents.py script."""

import json

# Import from scripts directory
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from register_agents import (
    RegistrationResult,
    compute_config_hash,
    load_agent_configs,
    load_previous_manifest,
    save_registration_manifest,
)


class TestComputeConfigHash:
    def test_consistent_hash(self):
        config = {"name": "test", "type": "claude-code"}

        hash1 = compute_config_hash(config)
        hash2 = compute_config_hash(config)

        assert hash1 == hash2

    def test_different_configs_different_hash(self):
        config1 = {"name": "test1", "type": "claude-code"}
        config2 = {"name": "test2", "type": "claude-code"}

        assert compute_config_hash(config1) != compute_config_hash(config2)

    def test_order_independent(self):
        config1 = {"name": "test", "type": "claude-code"}
        config2 = {"type": "claude-code", "name": "test"}

        # Keys are sorted during hashing, so order shouldn't matter
        assert compute_config_hash(config1) == compute_config_hash(config2)


class TestLoadAgentConfigs:
    def test_loads_all_configs(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()

        # Create two agents
        for name in ["agent-1", "agent-2"]:
            agent_dir = agents_dir / name
            agent_dir.mkdir()
            config = {
                "name": name,
                "type": "claude-code",
                "brain": {"model": "test"},
                "capabilities": {},
            }
            (agent_dir / "config.yaml").write_text(yaml.dump(config))

        configs = load_agent_configs(tmp_path)

        assert len(configs) == 2
        names = {c["name"] for c in configs}
        assert names == {"agent-1", "agent-2"}

    def test_adds_dir_and_hash(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()

        agent_dir = agents_dir / "test-agent"
        agent_dir.mkdir()
        config = {"name": "test-agent", "type": "claude-code"}
        (agent_dir / "config.yaml").write_text(yaml.dump(config))

        configs = load_agent_configs(tmp_path)

        assert len(configs) == 1
        assert "_dir" in configs[0]
        assert "_hash" in configs[0]

    def test_empty_if_no_agents_dir(self, tmp_path):
        configs = load_agent_configs(tmp_path)
        assert configs == []

    def test_skips_non_directories(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()

        # Create a file in agents dir (should be skipped)
        (agents_dir / "not-a-dir.txt").write_text("test")

        configs = load_agent_configs(tmp_path)
        assert configs == []


class TestLoadPreviousManifest:
    def test_loads_existing_manifest(self, tmp_path):
        manifest = {
            "version": "1.0.0",
            "agents": {
                "agent-1": "hash1",
                "agent-2": "hash2",
            },
        }
        (tmp_path / ".registration-manifest.json").write_text(json.dumps(manifest))

        result = load_previous_manifest(tmp_path)

        assert result == {"agent-1": "hash1", "agent-2": "hash2"}

    def test_returns_empty_if_no_manifest(self, tmp_path):
        result = load_previous_manifest(tmp_path)
        assert result == {}


class TestSaveRegistrationManifest:
    def test_saves_manifest(self, tmp_path):
        agents = {"agent-1": "hash1", "agent-2": "hash2"}

        save_registration_manifest(tmp_path, agents)

        manifest_path = tmp_path / ".registration-manifest.json"
        assert manifest_path.exists()

        data = json.loads(manifest_path.read_text())
        assert data["version"] == "1.0.0"
        assert data["agents"] == agents


class TestRegistrationResult:
    def test_created_result(self):
        result = RegistrationResult(
            name="test-agent",
            status="created",
            message="Agent registered successfully",
            api_key="test-key-123",
        )

        assert result.name == "test-agent"
        assert result.status == "created"
        assert result.api_key == "test-key-123"

    def test_error_result(self):
        result = RegistrationResult(
            name="test-agent",
            status="error",
            message="Registration failed",
        )

        assert result.status == "error"
        assert result.api_key is None
