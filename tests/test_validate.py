"""Tests for validate.py script."""

import json
import tempfile
from pathlib import Path

import pytest
import yaml

# Import from scripts directory
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from validate import (
    ValidationError,
    extract_yaml_frontmatter,
    get_validator,
    validate_agent,
    validate_all,
    validate_skill,
)


@pytest.fixture
def temp_repo(tmp_path):
    """Create a temporary repository structure for testing."""
    # Create directories
    (tmp_path / "agents").mkdir()
    (tmp_path / "skills").mkdir()
    (tmp_path / "schemas").mkdir()

    # Copy schemas
    schemas_src = Path(__file__).parent.parent / "schemas"
    (tmp_path / "schemas" / "agent-config.schema.json").write_text(
        (schemas_src / "agent-config.schema.json").read_text()
    )
    (tmp_path / "schemas" / "skill.schema.json").write_text(
        (schemas_src / "skill.schema.json").read_text()
    )

    return tmp_path


@pytest.fixture
def valid_agent_config():
    """Return a valid agent configuration."""
    return {
        "version": "1.0.0",
        "name": "test-agent",
        "type": "claude-code",
        "brain": {
            "model": "claude-sonnet-4-20250514",
            "temperature": 0.7,
        },
        "capabilities": {
            "grants": ["hub:read", "hub:write"],
            "skills": ["hub-post"],
        },
        "cache_ttl": 300,
    }


@pytest.fixture
def valid_skill_frontmatter():
    """Return valid skill frontmatter."""
    return {
        "name": "test-skill",
        "description": "A test skill",
        "version": "1.0.0",
    }


class TestExtractYamlFrontmatter:
    def test_extracts_frontmatter(self):
        content = """---
name: test
description: A test
---

# Content here
"""
        result = extract_yaml_frontmatter(content)
        assert result == {"name": "test", "description": "A test"}

    def test_returns_none_without_frontmatter(self):
        content = "# Just markdown\n\nNo frontmatter here."
        result = extract_yaml_frontmatter(content)
        assert result is None

    def test_handles_empty_frontmatter(self):
        content = """---
---

# Content
"""
        result = extract_yaml_frontmatter(content)
        assert result is None


class TestValidateAgent:
    def test_valid_agent_passes(self, temp_repo, valid_agent_config):
        # Create agent directory
        agent_dir = temp_repo / "agents" / "test-agent"
        agent_dir.mkdir()

        # Write config
        (agent_dir / "config.yaml").write_text(yaml.dump(valid_agent_config))
        (agent_dir / "system-prompt.md").write_text("# Test Agent\n\nYou are a test agent.")

        # Validate
        schema_path = temp_repo / "schemas" / "agent-config.schema.json"
        errors = validate_agent(agent_dir, schema_path)
        assert errors == []

    def test_missing_config_fails(self, temp_repo):
        agent_dir = temp_repo / "agents" / "no-config"
        agent_dir.mkdir()

        schema_path = temp_repo / "schemas" / "agent-config.schema.json"
        errors = validate_agent(agent_dir, schema_path)

        assert len(errors) == 1
        assert "Missing config.yaml" in errors[0].message

    def test_missing_system_prompt_fails(self, temp_repo, valid_agent_config):
        agent_dir = temp_repo / "agents" / "no-prompt"
        agent_dir.mkdir()
        valid_agent_config["name"] = "no-prompt"
        (agent_dir / "config.yaml").write_text(yaml.dump(valid_agent_config))

        schema_path = temp_repo / "schemas" / "agent-config.schema.json"
        errors = validate_agent(agent_dir, schema_path)

        assert any("Missing system-prompt.md" in e.message for e in errors)

    def test_name_mismatch_fails(self, temp_repo, valid_agent_config):
        agent_dir = temp_repo / "agents" / "different-name"
        agent_dir.mkdir()
        # Config has name "test-agent" but directory is "different-name"
        (agent_dir / "config.yaml").write_text(yaml.dump(valid_agent_config))
        (agent_dir / "system-prompt.md").write_text("# Test")

        schema_path = temp_repo / "schemas" / "agent-config.schema.json"
        errors = validate_agent(agent_dir, schema_path)

        assert any("must match directory name" in e.message for e in errors)

    def test_invalid_yaml_fails(self, temp_repo):
        agent_dir = temp_repo / "agents" / "bad-yaml"
        agent_dir.mkdir()
        (agent_dir / "config.yaml").write_text("name: bad\n  indentation: wrong")

        schema_path = temp_repo / "schemas" / "agent-config.schema.json"
        errors = validate_agent(agent_dir, schema_path)

        assert any("Invalid YAML" in e.message for e in errors)

    def test_missing_required_fields_fails(self, temp_repo):
        agent_dir = temp_repo / "agents" / "incomplete"
        agent_dir.mkdir()
        (agent_dir / "config.yaml").write_text(yaml.dump({"name": "incomplete"}))
        (agent_dir / "system-prompt.md").write_text("# Test")

        schema_path = temp_repo / "schemas" / "agent-config.schema.json"
        errors = validate_agent(agent_dir, schema_path)

        # Should fail on missing 'type', 'brain', 'capabilities'
        assert len(errors) >= 3


class TestValidateSkill:
    def test_valid_skill_passes(self, temp_repo, valid_skill_frontmatter):
        skill_dir = temp_repo / "skills" / "test-skill"
        skill_dir.mkdir()

        content = f"""---
{yaml.dump(valid_skill_frontmatter)}---

# Test Skill

This is a test skill.
"""
        (skill_dir / "SKILL.md").write_text(content)

        schema_path = temp_repo / "schemas" / "skill.schema.json"
        errors = validate_skill(skill_dir, schema_path)
        assert errors == []

    def test_missing_skill_md_fails(self, temp_repo):
        skill_dir = temp_repo / "skills" / "no-skill"
        skill_dir.mkdir()

        schema_path = temp_repo / "schemas" / "skill.schema.json"
        errors = validate_skill(skill_dir, schema_path)

        assert len(errors) == 1
        assert "Missing SKILL.md" in errors[0].message

    def test_missing_frontmatter_fails(self, temp_repo):
        skill_dir = temp_repo / "skills" / "no-frontmatter"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Just markdown\n\nNo frontmatter here.")

        schema_path = temp_repo / "schemas" / "skill.schema.json"
        errors = validate_skill(skill_dir, schema_path)

        assert any("Missing YAML frontmatter" in e.message for e in errors)


class TestValidateAll:
    def test_validates_all_agents_and_skills(self, temp_repo, valid_agent_config, valid_skill_frontmatter):
        # Create valid agent
        agent_dir = temp_repo / "agents" / "test-agent"
        agent_dir.mkdir()
        (agent_dir / "config.yaml").write_text(yaml.dump(valid_agent_config))
        (agent_dir / "system-prompt.md").write_text("# Test")

        # Create valid skill
        skill_dir = temp_repo / "skills" / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(f"---\n{yaml.dump(valid_skill_frontmatter)}---\n# Test")

        errors, agent_count, skill_count = validate_all(temp_repo)

        assert errors == []
        assert agent_count == 1
        assert skill_count == 1

    def test_fail_fast_stops_on_first_error(self, temp_repo):
        # Create multiple invalid agents
        for i in range(3):
            agent_dir = temp_repo / "agents" / f"broken-{i}"
            agent_dir.mkdir()
            (agent_dir / "config.yaml").write_text(yaml.dump({"name": f"broken-{i}"}))

        errors, _, _ = validate_all(temp_repo, fail_fast=True)

        # Should have at least one error but potentially fewer than all due to fail-fast
        assert len(errors) >= 1


class TestGetValidator:
    def test_caches_validators(self, temp_repo):
        schema_path = temp_repo / "schemas" / "agent-config.schema.json"

        validator1 = get_validator(schema_path)
        validator2 = get_validator(schema_path)

        # Should be the same cached instance
        assert validator1 is validator2
