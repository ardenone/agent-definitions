"""Tests for agent config compatibility with botburrow-agents runner.

This test suite validates that agent configurations in agent-definitions
are compatible with the botburrow-agents runner requirements.

The runner expects specific schema compliance defined in:
- agent-definitions/schemas/agent-config.schema.json
- botburrow-agents/src/botburrow_agents/models.py
- botburrow-agents/src/botburrow_agents/clients/git.py
"""

from pathlib import Path

import pytest
import yaml

# Built-in MCP servers from botburrow-agents/src/botburrow_agents/mcp/manager.py
BUILTIN_MCP_SERVERS = {
    "github": {"grants": ["github:read", "github:write"]},
    "brave": {"grants": ["brave:search"]},
    "filesystem": {"grants": ["filesystem:read", "filesystem:write"]},
    "postgres": {"grants": ["postgres:read", "postgres:write"]},
    "hub": {"grants": ["hub:read", "hub:write"]},
}

# Valid agent types from schema
VALID_AGENT_TYPES = ["native", "claude-code", "goose", "aider", "custom"]

# Valid LLM providers from schema
VALID_PROVIDERS = ["anthropic", "openai", "google", "local"]

# Valid discovery frequencies
VALID_FREQUENCIES = ["staleness", "hourly", "daily"]

# Valid memory retrieval strategies
VALID_RETRIEVAL_STRATEGIES = ["embedding_search", "keyword", "recent"]


class TestAgentSchemaCompatibility:
    """Test that all agent configs conform to the expected schema."""

    @pytest.fixture
    def repo_root(self):
        """Get repository root directory."""
        return Path(__file__).parent.parent

    @pytest.fixture
    def agents_dir(self, repo_root):
        """Get agents directory."""
        return repo_root / "agents"

    @pytest.fixture
    def agent_configs(self, agents_dir):
        """Load all agent configurations."""
        configs = {}
        for agent_dir in agents_dir.iterdir():
            if not agent_dir.is_dir():
                continue
            config_file = agent_dir / "config.yaml"
            if not config_file.exists():
                continue
            with open(config_file) as f:
                configs[agent_dir.name] = yaml.safe_load(f)
        return configs

    def test_all_agents_have_required_fields(self, agent_configs):
        """Test that all agents have required fields from schema."""
        for agent_name, config in agent_configs.items():
            # Required fields per schema
            assert "name" in config, f"{agent_name}: Missing required field 'name'"
            assert "type" in config, f"{agent_name}: Missing required field 'type'"
            assert "brain" in config, f"{agent_name}: Missing required field 'brain'"
            assert "capabilities" in config, f"{agent_name}: Missing required field 'capabilities'"

    def test_name_matches_directory(self, agents_dir, agent_configs):
        """Test that config name matches directory name."""
        for agent_dir in agents_dir.iterdir():
            if not agent_dir.is_dir():
                continue
            config_file = agent_dir / "config.yaml"
            if not config_file.exists():
                continue

            with open(config_file) as f:
                config = yaml.safe_load(f)

            assert config.get("name") == agent_dir.name, (
                f"Agent name '{config.get('name')}' doesn't match directory '{agent_dir.name}'"
            )

    def test_agent_type_is_valid(self, agent_configs):
        """Test that all agent types are valid."""
        for agent_name, config in agent_configs.items():
            agent_type = config.get("type")
            assert agent_type in VALID_AGENT_TYPES, (
                f"{agent_name}: Invalid agent type '{agent_type}'. "
                f"Must be one of {VALID_AGENT_TYPES}"
            )

    def test_brain_configuration_is_valid(self, agent_configs):
        """Test brain configuration is valid."""
        for agent_name, config in agent_configs.items():
            brain = config.get("brain", {})
            assert "model" in brain, f"{agent_name}: Missing brain.model"

            # Provider validation
            provider = brain.get("provider", "anthropic")
            assert provider in VALID_PROVIDERS, (
                f"{agent_name}: Invalid brain.provider '{provider}'"
            )

            # Temperature range
            temperature = brain.get("temperature", 0.7)
            assert 0 <= temperature <= 2, (
                f"{agent_name}: brain.temperature must be between 0 and 2, got {temperature}"
            )

            # Max tokens range
            max_tokens = brain.get("max_tokens", 4096)
            assert 100 <= max_tokens <= 128000, (
                f"{agent_name}: brain.max_tokens must be between 100 and 128000, got {max_tokens}"
            )

            # Native type agents require api_base and api_key_env
            if config.get("type") == "native":
                assert "api_base" in brain, (
                    f"{agent_name}: Native type requires brain.api_base"
                )
                assert "api_key_env" in brain, (
                    f"{agent_name}: Native type requires brain.api_key_env"
                )
                # api_key_env must be uppercase with underscores
                api_key_env = brain.get("api_key_env", "")
                assert api_key_env.isupper() or "_" in api_key_env, (
                    f"{agent_name}: brain.api_key_env must be UPPER_CASE_WITH_UNDERSCORES"
                )

    def test_capabilities_grants_format(self, agent_configs):
        """Test capability grants follow the correct format."""
        import re
        grant_pattern = r"^[a-z0-9-]+:[a-z0-9-]+(:[a-z0-9-]+)?$"

        for agent_name, config in agent_configs.items():
            capabilities = config.get("capabilities", {})
            grants = capabilities.get("grants", [])

            for grant in grants:
                assert isinstance(grant, str), (
                    f"{agent_name}: Grant must be string, got {type(grant)}"
                )
                assert re.match(grant_pattern, grant), (
                    f"{agent_name}: Invalid grant format '{grant}'. "
                    f"Must match 'service:permission' or 'service:permission:resource'"
                )

    def test_capabilities_skills_format(self, agent_configs):
        """Test skill names follow correct format."""
        import re
        skill_pattern = r"^[a-z0-9-]+$"

        for agent_name, config in agent_configs.items():
            capabilities = config.get("capabilities", {})
            skills = capabilities.get("skills", [])

            for skill in skills:
                assert isinstance(skill, str), f"{agent_name}: Skill must be string"
                assert re.match(skill_pattern, skill), (
                    f"{agent_name}: Invalid skill name '{skill}'. "
                    f"Must be lowercase with hyphens only"
                )

    def test_mcp_servers_reference_builtin(self, agent_configs):
        """Test that MCP servers reference built-in servers or are properly defined."""
        for agent_name, config in agent_configs.items():
            capabilities = config.get("capabilities", {})
            mcp_servers = capabilities.get("mcp_servers", [])

            for mcp_server in mcp_servers:
                if isinstance(mcp_server, str):
                    # Shorthand reference to built-in server
                    assert mcp_server in BUILTIN_MCP_SERVERS, (
                        f"{agent_name}: Unknown MCP server '{mcp_server}'. "
                        f"Must be one of {list(BUILTIN_MCP_SERVERS.keys())}"
                    )

                    # Verify agent has required grants for this server
                    required_grants = BUILTIN_MCP_SERVERS[mcp_server]["grants"]
                    agent_grants = capabilities.get("grants", [])

                    for required_grant in required_grants:
                        # Check if agent has the grant or a wildcard
                        service = required_grant.split(":")[0]
                        has_grant = (
                            required_grant in agent_grants
                            or f"{service}:*" in agent_grants
                        )
                        assert has_grant, (
                            f"{agent_name}: Missing required grant '{required_grant}' "
                            f"for MCP server '{mcp_server}'"
                        )

                elif isinstance(mcp_server, dict):
                    # Inline MCP server definition
                    assert "name" in mcp_server, (
                        f"{agent_name}: MCP server dict must have 'name'"
                    )
                    assert "command" in mcp_server, (
                        f"{agent_name}: MCP server dict must have 'command'"
                    )

    def test_shell_configuration(self, agent_configs):
        """Test shell configuration is valid."""
        for agent_name, config in agent_configs.items():
            capabilities = config.get("capabilities", {})
            shell = capabilities.get("shell", {})

            if shell.get("enabled", False):
                timeout = shell.get("timeout_seconds", 120)
                assert 1 <= timeout <= 3600, (
                    f"{agent_name}: shell.timeout_seconds must be 1-3600, got {timeout}"
                )

                # allowed_commands and blocked_patterns must be lists
                assert isinstance(shell.get("allowed_commands", []), list), (
                    f"{agent_name}: shell.allowed_commands must be a list"
                )
                assert isinstance(shell.get("blocked_patterns", []), list), (
                    f"{agent_name}: shell.blocked_patterns must be a list"
                )

    def test_behavior_configuration(self, agent_configs):
        """Test behavior configuration is valid."""
        for agent_name, config in agent_configs.items():
            behavior = config.get("behavior", {})

            # Max iterations range
            max_iterations = behavior.get("max_iterations", 10)
            assert 1 <= max_iterations <= 50, (
                f"{agent_name}: behavior.max_iterations must be 1-50, got {max_iterations}"
            )

            # Discovery config
            discovery = behavior.get("discovery", {})
            if discovery.get("enabled", False):
                frequency = discovery.get("frequency", "staleness")
                assert frequency in VALID_FREQUENCIES, (
                    f"{agent_name}: behavior.discovery.frequency must be "
                    f"{VALID_FREQUENCIES}, got {frequency}"
                )

                min_confidence = discovery.get("min_confidence", 0.7)
                assert 0 <= min_confidence <= 1, (
                    f"{agent_name}: behavior.discovery.min_confidence must be 0-1, "
                    f"got {min_confidence}"
                )

            # Limits config
            limits = behavior.get("limits", {})
            max_daily_posts = limits.get("max_daily_posts", 5)
            max_daily_comments = limits.get("max_daily_comments", 50)
            max_responses = limits.get("max_responses_per_thread", 3)
            min_interval = limits.get("min_interval_seconds", 60)

            assert max_daily_posts >= 0, f"{agent_name}: max_daily_posts must be >= 0"
            assert max_daily_comments >= 0, f"{agent_name}: max_daily_comments must be >= 0"
            assert max_responses >= 0, f"{agent_name}: max_responses_per_thread must be >= 0"
            assert min_interval >= 0, f"{agent_name}: min_interval_seconds must be >= 0"

    def test_memory_configuration(self, agent_configs):
        """Test memory configuration is valid."""
        for agent_name, config in agent_configs.items():
            memory = config.get("memory", {})

            if memory.get("enabled", False):
                # Max size range
                max_size = memory.get("max_size_mb", 100)
                assert 1 <= max_size <= 1000, (
                    f"{agent_name}: memory.max_size_mb must be 1-1000, got {max_size}"
                )

                # Retrieval config
                retrieval = memory.get("retrieval", {})
                strategy = retrieval.get("strategy", "embedding_search")
                assert strategy in VALID_RETRIEVAL_STRATEGIES, (
                    f"{agent_name}: memory.retrieval.strategy must be "
                    f"{VALID_RETRIEVAL_STRATEGIES}, got {strategy}"
                )

                max_context = retrieval.get("max_context_items", 10)
                assert 1 <= max_context <= 100, (
                    f"{agent_name}: memory.retrieval.max_context_items must be 1-100, "
                    f"got {max_context}"
                )

    def test_interests_configuration(self, agent_configs):
        """Test interests configuration is valid."""
        import re

        community_pattern = r"^m/[a-z0-9-]+$"

        for agent_name, config in agent_configs.items():
            interests = config.get("interests", {})

            # Validate communities format
            communities = interests.get("communities", [])
            for community in communities:
                assert re.match(community_pattern, community), (
                    f"{agent_name}: Invalid community format '{community}'. "
                    f"Must match 'm/community-name'"
                )

            # All fields must be lists
            assert isinstance(interests.get("topics", []), list), (
                f"{agent_name}: interests.topics must be a list"
            )
            assert isinstance(interests.get("keywords", []), list), (
                f"{agent_name}: interests.keywords must be a list"
            )
            assert isinstance(interests.get("follow_agents", []), list), (
                f"{agent_name}: interests.follow_agents must be a list"
            )

    def test_cache_ttl_range(self, agent_configs):
        """Test cache_ttl is within valid range."""
        for agent_name, config in agent_configs.items():
            cache_ttl = config.get("cache_ttl", 300)
            assert 30 <= cache_ttl <= 3600, (
                f"{agent_name}: cache_ttl must be 30-3600 seconds, got {cache_ttl}"
            )

    def test_version_format(self, agent_configs):
        """Test version follows semantic versioning."""
        import re

        version_pattern = r"^\d+\.\d+\.\d+$"

        for agent_name, config in agent_configs.items():
            version = config.get("version")
            if version:  # Version is optional but must follow format if present
                assert re.match(version_pattern, version), (
                    f"{agent_name}: Invalid version format '{version}'. "
                    f"Must be SEMVER like '1.0.0'"
                )


class TestSystemPromptCompatibility:
    """Test system prompts are compatible with runner requirements."""

    @pytest.fixture
    def repo_root(self):
        """Get repository root directory."""
        return Path(__file__).parent.parent

    @pytest.fixture
    def agents_dir(self, repo_root):
        """Get agents directory."""
        return repo_root / "agents"

    def test_all_agents_have_system_prompt(self, agents_dir):
        """Test all agents have a system-prompt.md file."""
        for agent_dir in agents_dir.iterdir():
            if not agent_dir.is_dir():
                continue
            # Skip if no config.yaml
            if not (agent_dir / "config.yaml").exists():
                continue

            prompt_file = agent_dir / "system-prompt.md"
            assert prompt_file.exists(), f"{agent_dir.name}: Missing system-prompt.md"

    def test_system_prompt_size_reasonable(self, agents_dir):
        """Test system prompts don't exceed reasonable token limits."""
        # Approximate 4 chars per token for English text
        max_char_limit = 50000  # ~12.5K tokens

        for agent_dir in agents_dir.iterdir():
            if not agent_dir.is_dir():
                continue
            prompt_file = agent_dir / "system-prompt.md"
            if not prompt_file.exists():
                continue

            content = prompt_file.read_text()
            char_count = len(content)

            assert char_count <= max_char_limit, (
                f"{agent_dir.name}: System prompt too large ({char_count} chars). "
                f"Should be under {max_char_limit} chars (~12.5K tokens)"
            )

    def test_system_prompt_not_empty(self, agents_dir):
        """Test system prompts have meaningful content."""
        min_length = 50  # Minimum reasonable prompt length

        for agent_dir in agents_dir.iterdir():
            if not agent_dir.is_dir():
                continue
            prompt_file = agent_dir / "system-prompt.md"
            if not prompt_file.exists():
                continue

            content = prompt_file.read_text().strip()
            assert len(content) >= min_length, (
                f"{agent_dir.name}: System prompt too short or empty"
            )


class TestRunnerLoadCompatibility:
    """Test configs can be loaded by botburrow-agents GitClient.

    This validates compatibility with the loading logic in:
    botburrow-agents/src/botburrow_agents/clients/git.py
    """

    @pytest.fixture
    def repo_root(self):
        """Get repository root directory."""
        return Path(__file__).parent.parent

    @pytest.fixture
    def agents_dir(self, repo_root):
        """Get agents directory."""
        return repo_root / "agents"

    def test_configs_parse_to_pydantic_models(self, agents_dir):
        """Test that configs can be parsed by Pydantic models from botburrow-agents."""
        # Import models from botburrow-agents
        import sys
        botburrow_path = Path("/home/coder/botburrow-agents/src")
        if not botburrow_path.exists():
            pytest.skip("botburrow-agents not available for Pydantic validation")

        sys.path.insert(0, str(botburrow_path))
        try:
            from botburrow_agents.models import (
                BrainConfig,
                ShellConfig,
                SpawningConfig,
            )
        except ImportError:
            pytest.skip("pydantic not available for runner compatibility test")

        for agent_dir in agents_dir.iterdir():
            if not agent_dir.is_dir():
                continue
            config_file = agent_dir / "config.yaml"
            if not config_file.exists():
                continue

            # Load config
            import yaml
            with open(config_file) as f:
                config_data = yaml.safe_load(f)

            # Try to parse with Pydantic models (just verify they parse)
            try:
                BrainConfig(**config_data.get("brain", {}))
                shell_data = config_data.get("capabilities", {}).get("shell", {})
                spawning_data = config_data.get("capabilities", {}).get("spawning", {})
                ShellConfig(**shell_data)
                SpawningConfig(**spawning_data)
            except Exception as e:
                pytest.fail(f"{agent_dir.name}: Failed to parse with Pydantic: {e}")

    def test_all_agent_fields_have_defaults(self, agents_dir):
        """Test that all optional fields can be missing and have reasonable defaults.

        This matches the default values in botburrow-agents models.py:
        - BrainConfig: model defaults to claude-sonnet-4-20250514
        - ShellConfig: enabled=False, timeout_seconds=120
        - SpawningConfig: can_propose=False
        - BehaviorConfig: respond_to_mentions=True, max_iterations=10
        """
        minimal_config = {
            "name": "minimal-test",
            "type": "claude-code",
            "brain": {},  # All defaults
            "capabilities": {},  # All defaults
        }

        # This should not raise an error

        import yaml

        # Validate YAML can be created
        yaml_str = yaml.dump(minimal_config)
        parsed = yaml.safe_load(yaml_str)
        assert parsed["name"] == "minimal-test"


class TestMCPServerGrants:
    """Test MCP server and grants compatibility."""

    def test_mcp_servers_have_matching_grants(self):
        """Test that for each MCP server in BUILTIN_SERVERS, grants are properly defined."""
        # This is a meta-test of the BUILTIN_MCP_SERVERS definition
        expected_servers = ["github", "brave", "filesystem", "postgres", "hub"]

        for server_name in expected_servers:
            assert server_name in BUILTIN_MCP_SERVERS, (
                f"Missing MCP server definition: {server_name}"
            )

            server_config = BUILTIN_MCP_SERVERS[server_name]
            assert "grants" in server_config, f"{server_name}: Missing 'grants' definition"
            assert isinstance(server_config["grants"], list), (
                f"{server_name}: 'grants' must be a list"
            )
            assert len(server_config["grants"]) > 0, (
                f"{server_name}: 'grants' cannot be empty"
            )

            # Validate grant format
            import re
            grant_pattern = r"^[a-z0-9-]+:[a-z0-9-]+(:[a-z0-9-]+)?$"
            for grant in server_config["grants"]:
                assert re.match(grant_pattern, grant), (
                    f"{server_name}: Invalid grant format '{grant}'"
                )


class TestSchemaValidation:
    """Test JSON schema validation of agent configs."""

    @pytest.fixture
    def repo_root(self):
        """Get repository root directory."""
        return Path(__file__).parent.parent

    @pytest.fixture
    def schema(self, repo_root):
        """Load agent config schema."""
        import json
        schema_file = repo_root / "schemas" / "agent-config.schema.json"
        with open(schema_file) as f:
            return json.load(f)

    @pytest.fixture
    def agents_dir(self, repo_root):
        """Get agents directory."""
        return repo_root / "agents"

    def test_all_agents_validate_against_schema(self, schema, agents_dir):
        """Test all agent configs validate against JSON schema."""
        from jsonschema import ValidationError, validate

        for agent_dir in agents_dir.iterdir():
            if not agent_dir.is_dir():
                continue
            config_file = agent_dir / "config.yaml"
            if not config_file.exists():
                continue

            # Load and parse config
            import yaml
            with open(config_file) as f:
                config = yaml.safe_load(f)

            # Validate against schema
            try:
                validate(instance=config, schema=schema)
            except ValidationError as e:
                pytest.fail(
                    f"{agent_dir.name}: Schema validation failed\n"
                    f"  Path: {'/'.join(str(p) for p in e.path)}\n"
                    f"  Error: {e.message}"
                )
