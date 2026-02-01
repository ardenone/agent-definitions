# ADR-030: Supported Orchestration Types

## Status

**Accepted**

## Context

Agent definitions specify a `type` field that determines which coding orchestration (CLI tool) the runner uses to execute the agent. We need to define:

1. What orchestrations are supported
2. Criteria for adding new ones
3. How the runner invokes each type

## Decision

**Support two orchestration modes:**

1. **CLI-based** - External tools with headless CLI (Claude Code, Aider, Goose)
2. **Native** - Internal agentic loop using direct LLM API calls (OpenClaw-style)

The `type` field maps to an executor implementation in botburrow-agents.

## Orchestration Categories

### Native Type (Direct API)

The `native` type implements an internal OpenClaw-style agentic loop:

- **No external CLI dependency** - Lighter containers, faster startup
- **Direct LLM API calls** - Works with any OpenAI-compatible endpoint
- **Useful for free API sprints** - Spin up many agents when providers offer free credits
- **Model-agnostic** - Easily switch between providers/models

```yaml
# Example: Agent using native type with free API
name: sprint-coder
type: native
brain:
  model: gpt-4o-mini
  api_base: https://api.openai.com/v1  # Or any compatible endpoint
  temperature: 0.7
```

### CLI-based Types

CLI-based orchestrations require an external tool and must:

1. **Has a headless CLI** - Can be invoked without GUI/IDE
2. **Accepts prompt input** - Via stdin, argument, or file
3. **Returns structured output** - Exit code, stdout, or JSON
4. **Supports non-interactive mode** - No TTY required
5. **Can be containerized** - Runs in Docker/Kubernetes

## Currently Supported Types

| Type | Tool | CLI Command | Status |
|------|------|-------------|--------|
| `native` | Internal loop | Direct API calls | ✅ Supported |
| `claude-code` | Claude Code | `claude -p "prompt" --print` | ✅ Supported |
| `goose` | Goose (Block) | `goose run --prompt "..."` | ✅ Supported |
| `aider` | Aider | `aider --message "..." --yes` | ✅ Supported |

## Candidate Types (To Evaluate)

| Type | Tool | CLI Support | Notes |
|------|------|-------------|-------|
| `amp` | Sourcegraph Amp | `amp "prompt"` | Has CLI, evaluate |
| `codebuff` | Codebuff | TBD | Check for CLI mode |
| `mentat` | Mentat | `mentat --message "..."` | Has CLI |
| `gpt-engineer` | GPT Engineer | `gpt-engineer "prompt"` | Has CLI |
| `smol-developer` | Smol Developer | Python script | Scriptable |
| `opencode` | OpenCode | TBD | Placeholder, verify exists |

## Not Supported (No Headless CLI)

| Tool | Reason |
|------|--------|
| Cursor | IDE-only, no headless mode |
| Windsurf | IDE-only, no headless mode |
| Cline | VS Code extension only |
| Continue | VS Code extension only |
| Copilot | IDE integration only |
| Kilocode | VS Code extension only |

## Schema Definition

```json
{
  "type": {
    "type": "string",
    "enum": [
      "native",
      "claude-code",
      "goose",
      "aider",
      "amp",
      "mentat",
      "custom"
    ],
    "description": "Orchestration type: 'native' for direct API, others for CLI tools"
  }
}
```

### Native Type Configuration

```yaml
type: native
brain:
  model: gpt-4o-mini           # Model identifier
  api_base: https://api.openai.com/v1  # OpenAI-compatible endpoint
  api_key_env: OPENAI_API_KEY  # Environment variable for API key
  temperature: 0.7
  max_tokens: 4096
```

### Custom Type Configuration

The `custom` type allows specifying a custom command:

```yaml
type: custom
executor:
  command: /usr/local/bin/my-agent
  args: ["--prompt", "${PROMPT}", "--output", "json"]
  env:
    MY_API_KEY: "${MY_API_KEY}"
```

## Executor Interface

Each orchestration type has an executor in botburrow-agents:

```python
# botburrow-agents/executors/base.py
from abc import ABC, abstractmethod

class Executor(ABC):
    """Base class for coding orchestration executors."""

    @abstractmethod
    async def run(
        self,
        prompt: str,
        system_prompt: str,
        working_dir: Path,
        env: dict[str, str],
        timeout: int = 300,
    ) -> ExecutorResult:
        """Execute the orchestration with the given prompt."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this executor is available (CLI installed)."""
        pass
```

```python
# botburrow-agents/executors/native.py
class NativeExecutor(Executor):
    """
    OpenClaw-style agentic loop using direct LLM API calls.

    Advantages:
    - No external CLI dependency (lighter containers)
    - Works with any OpenAI-compatible API
    - Perfect for free API sprints or new model testing
    """

    async def run(self, prompt: str, **kwargs) -> ExecutorResult:
        api_base = kwargs.get("api_base", "https://api.anthropic.com/v1")
        api_key = os.environ.get(kwargs.get("api_key_env", "ANTHROPIC_API_KEY"))
        model = kwargs.get("model", "claude-sonnet-4-20250514")

        # Core tools (OpenClaw minimal set)
        tools = [
            {"name": "read", "description": "Read file contents"},
            {"name": "write", "description": "Write/create files"},
            {"name": "edit", "description": "Modify existing files"},
            {"name": "bash", "description": "Execute shell commands"},
        ]

        context = []
        iterations = 0
        max_iterations = kwargs.get("max_iterations", 10)

        while iterations < max_iterations:
            response = await self.llm_call(api_base, api_key, model, prompt, context, tools)

            if response.has_tool_calls:
                for tool_call in response.tool_calls:
                    result = await self.execute_tool(tool_call, kwargs["working_dir"])
                    context.append({"role": "tool", "content": result})
            else:
                return ExecutorResult(
                    exit_code=0,
                    output=response.content,
                    error="",
                )
            iterations += 1

        return ExecutorResult(exit_code=1, output="", error="Max iterations exceeded")

    def is_available(self) -> bool:
        # Native executor is always available (no external CLI)
        return True
```

```python
# botburrow-agents/executors/claude_code.py
class ClaudeCodeExecutor(Executor):
    async def run(self, prompt: str, **kwargs) -> ExecutorResult:
        proc = await asyncio.create_subprocess_exec(
            "claude",
            "--print",
            "--dangerously-skip-permissions",
            "--output-format", "stream-json",
            "-p", prompt,
            cwd=kwargs["working_dir"],
            env={**os.environ, **kwargs["env"]},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return ExecutorResult(
            exit_code=proc.returncode,
            output=stdout.decode(),
            error=stderr.decode(),
        )
```

```python
# botburrow-agents/executors/aider.py
class AiderExecutor(Executor):
    async def run(self, prompt: str, **kwargs) -> ExecutorResult:
        proc = await asyncio.create_subprocess_exec(
            "aider",
            "--message", prompt,
            "--yes",  # Non-interactive
            "--no-git",  # Don't auto-commit
            cwd=kwargs["working_dir"],
            env={**os.environ, **kwargs["env"]},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return ExecutorResult(
            exit_code=proc.returncode,
            output=stdout.decode(),
            error=stderr.decode(),
        )
```

## Adding a New Orchestration

1. **Verify CLI support** - Test headless invocation
2. **Add to schema** - Update `agent-config.schema.json` enum
3. **Implement executor** - Create `executors/{type}.py`
4. **Add to container** - Install CLI in runner Dockerfile
5. **Document** - Add to this ADR

## Container Requirements

Each orchestration needs its CLI available in the runner container:

```dockerfile
# botburrow-agents/docker/Dockerfile.runner

# Claude Code
RUN npm install -g @anthropic-ai/claude-code

# Aider
RUN pip install aider-chat

# Goose
RUN pip install goose-ai

# Add more as needed
```

Or use separate container images per executor type:

```yaml
# Runner can select image based on agent type
images:
  claude-code: ghcr.io/botburrow/runner-claude:latest
  aider: ghcr.io/botburrow/runner-aider:latest
  goose: ghcr.io/botburrow/runner-goose:latest
```

## Consequences

### Positive
- Flexible orchestration choice per agent
- Easy to add new orchestrations
- Agents can use best tool for their purpose
- **Native type enables free API sprints** - Spin up many agents without CLI overhead
- **Model-agnostic native executor** - Test new models instantly

### Negative
- Must maintain multiple executor implementations
- Container size grows with each CLI (not native)
- Different CLIs have different output formats

### Mitigations
- Normalize output in executor layer
- Use multi-image strategy to keep containers small
- **Native type has minimal dependencies** - Use for rapid scaling
- Automated testing for each executor

## Use Case: Free API Sprint

When a provider offers free credits or rate limits are lifted:

```yaml
# Quick agent config for free sprint
name: sprint-agent-001
type: native
brain:
  model: gemini-2.0-flash
  api_base: https://generativelanguage.googleapis.com/v1beta/openai
  api_key_env: GOOGLE_API_KEY
  temperature: 0.7
behavior:
  max_iterations: 20  # Higher limit for complex tasks
```

Benefits:
- **No CLI installation needed** - Containers start instantly
- **Easy to clone** - Just change name and scale horizontally
- **Provider-agnostic** - Switch API endpoints without rebuilding
