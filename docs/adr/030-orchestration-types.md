# ADR-030: Supported Orchestration Types

## Status

**Accepted**

## Context

Agent definitions specify a `type` field that determines which coding orchestration (CLI tool) the runner uses to execute the agent. We need to define:

1. What orchestrations are supported
2. Criteria for adding new ones
3. How the runner invokes each type

## Decision

**Support any coding orchestration that provides a headless CLI mode. The `type` field maps to an executor implementation in botburrow-agents.**

## Criteria for Supported Orchestrations

An orchestration can be added if it:

1. **Has a headless CLI** - Can be invoked without GUI/IDE
2. **Accepts prompt input** - Via stdin, argument, or file
3. **Returns structured output** - Exit code, stdout, or JSON
4. **Supports non-interactive mode** - No TTY required
5. **Can be containerized** - Runs in Docker/Kubernetes

## Currently Supported Types

| Type | Tool | CLI Command | Status |
|------|------|-------------|--------|
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
      "claude-code",
      "goose",
      "aider",
      "amp",
      "mentat",
      "custom"
    ],
    "description": "Coding orchestration CLI to use"
  }
}
```

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

### Negative
- Must maintain multiple executor implementations
- Container size grows with each CLI
- Different CLIs have different output formats

### Mitigations
- Normalize output in executor layer
- Use multi-image strategy to keep containers small
- Automated testing for each executor
