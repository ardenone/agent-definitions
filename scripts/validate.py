#!/usr/bin/env python3
"""
Validate agent configs and skill definitions against their schemas.

Features:
- Parallel validation across all configs
- Fail-fast mode for CI (--fail-fast)
- Cached compiled JSON schemas
- Validates both agents and skills
"""

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

import jsonschema
import yaml


class ValidationError(NamedTuple):
    """A single validation error."""

    path: Path
    message: str


class ValidationResult(NamedTuple):
    """Result of validating a single config."""

    path: Path
    valid: bool
    errors: list[str]


@lru_cache(maxsize=10)
def load_schema(schema_path: Path) -> dict:
    """Load and cache a JSON schema."""
    return json.loads(schema_path.read_text())


@lru_cache(maxsize=10)
def get_validator(schema_path: Path) -> jsonschema.Draft202012Validator:
    """Get a cached, compiled JSON Schema validator."""
    schema = load_schema(schema_path)
    return jsonschema.Draft202012Validator(schema)


def extract_yaml_frontmatter(content: str) -> dict | None:
    """Extract YAML frontmatter from markdown content.

    Returns None if no frontmatter found or if frontmatter is empty.
    """
    if not content.startswith("---"):
        return None

    # Find the closing ---
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return None

    frontmatter_text = match.group(1).strip()
    if not frontmatter_text:
        return None

    try:
        return yaml.safe_load(frontmatter_text)
    except yaml.YAMLError:
        return None


def validate_agent(agent_dir: Path, schema_path: Path) -> list[ValidationError]:
    """Validate a single agent directory.

    Returns a list of ValidationError objects for any issues found.
    """
    errors: list[ValidationError] = []
    config_path = agent_dir / "config.yaml"

    if not config_path.exists():
        errors.append(ValidationError(agent_dir, f"Missing config.yaml in {agent_dir.name}"))
        return errors

    try:
        config = yaml.safe_load(config_path.read_text())
    except yaml.YAMLError as e:
        errors.append(ValidationError(agent_dir, f"Invalid YAML in {agent_dir.name}: {e}"))
        return errors

    # Validate against schema
    validator = get_validator(schema_path)
    for error in validator.iter_errors(config):
        msg = f"{agent_dir.name}/config.yaml: {error.message}"
        errors.append(ValidationError(config_path, msg))

    # Check name matches directory name
    if config.get("name") != agent_dir.name:
        msg = (
            f"{agent_dir.name}: config name '{config.get('name')}' "
            f"must match directory name '{agent_dir.name}'"
        )
        errors.append(ValidationError(config_path, msg))

    # Check for system prompt
    prompt_path = agent_dir / "system-prompt.md"
    if not prompt_path.exists():
        errors.append(ValidationError(agent_dir, f"Missing system-prompt.md in {agent_dir.name}"))

    return errors


def validate_skill(skill_dir: Path, schema_path: Path) -> list[ValidationError]:
    """Validate a single skill directory.

    Returns a list of ValidationError objects for any issues found.
    """
    errors: list[ValidationError] = []
    skill_path = skill_dir / "SKILL.md"

    if not skill_path.exists():
        errors.append(ValidationError(skill_dir, f"Missing SKILL.md in {skill_dir.name}"))
        return errors

    content = skill_path.read_text()

    # Extract and validate frontmatter
    frontmatter = extract_yaml_frontmatter(content)
    if frontmatter is None:
        errors.append(
            ValidationError(skill_path, f"Missing YAML frontmatter in {skill_dir.name}/SKILL.md")
        )
        return errors

    # Validate against schema
    validator = get_validator(schema_path)
    for error in validator.iter_errors(frontmatter):
        errors.append(ValidationError(skill_path, f"{skill_dir.name}/SKILL.md: {error.message}"))

    return errors


def validate_all(
    root: Path, fail_fast: bool = False, parallel: bool = True
) -> tuple[list[ValidationError], int, int]:
    """
    Validate all agents and skills.

    Returns:
        Tuple of (all_errors, agent_count, skill_count)
    """
    agent_schema_path = root / "schemas" / "agent-config.schema.json"
    skill_schema_path = root / "schemas" / "skill.schema.json"

    agents_dir = root / "agents"
    skills_dir = root / "skills"

    agent_dirs = [d for d in agents_dir.iterdir() if d.is_dir()] if agents_dir.exists() else []
    skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir()] if skills_dir.exists() else []

    # Build set of available skill names
    available_skills = {d.name for d in skill_dirs}

    all_errors: list[ValidationError] = []
    agent_count = 0
    skill_count = 0

    if parallel:
        with ThreadPoolExecutor(max_workers=8) as executor:
            # Submit all agent validations
            agent_futures = {
                executor.submit(validate_agent, d, agent_schema_path): d for d in agent_dirs
            }
            # Submit all skill validations
            skill_futures = {
                executor.submit(validate_skill, d, skill_schema_path): d for d in skill_dirs
            }

            # Collect agent results
            for future in as_completed(agent_futures):
                agent_count += 1
                errors = future.result()
                all_errors.extend(errors)
                if fail_fast and errors:
                    # Cancel remaining futures
                    for f in agent_futures:
                        f.cancel()
                    for f in skill_futures:
                        f.cancel()
                    return all_errors, agent_count, skill_count

            # Collect skill results
            for future in as_completed(skill_futures):
                skill_count += 1
                errors = future.result()
                all_errors.extend(errors)
                if fail_fast and errors:
                    for f in skill_futures:
                        f.cancel()
                    return all_errors, agent_count, skill_count
    else:
        # Sequential validation
        for agent_dir in agent_dirs:
            agent_count += 1
            errors = validate_agent(agent_dir, agent_schema_path)
            all_errors.extend(errors)
            if fail_fast and errors:
                return all_errors, agent_count, skill_count

        for skill_dir in skill_dirs:
            skill_count += 1
            errors = validate_skill(skill_dir, skill_schema_path)
            all_errors.extend(errors)
            if fail_fast and errors:
                return all_errors, agent_count, skill_count

    # Cross-validate: Check that all skills referenced in agent configs exist
    for agent_dir in agent_dirs:
        config_path = agent_dir / "config.yaml"
        if not config_path.exists():
            continue
        try:
            config = yaml.safe_load(config_path.read_text())
            referenced_skills = config.get("capabilities", {}).get("skills", [])
            for skill in referenced_skills:
                if skill not in available_skills:
                    all_errors.append(
                        ValidationError(
                            config_path,
                            f"{agent_dir.name}: references non-existent skill '{skill}' "
                            f"(available: {', '.join(sorted(available_skills))})"
                        )
                    )
                    if fail_fast:
                        return all_errors, agent_count, skill_count
        except yaml.YAMLError:
            # Already caught in validate_agent
            pass

    return all_errors, agent_count, skill_count


def main():
    parser = argparse.ArgumentParser(description="Validate agent and skill configs")
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Exit on first error (useful for CI)",
    )
    parser.add_argument(
        "--no-parallel",
        action="store_true",
        help="Disable parallel validation",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Root directory of agent-definitions repo",
    )
    args = parser.parse_args()

    root = args.root
    if not (root / "schemas").exists():
        print(f"ERROR: {root} does not appear to be agent-definitions root")
        sys.exit(1)

    all_errors, agent_count, skill_count = validate_all(
        root,
        fail_fast=args.fail_fast,
        parallel=not args.no_parallel,
    )

    if all_errors:
        print("Validation errors:")
        for error in all_errors:
            print(f"  ERROR: {error.message}")
        sys.exit(1)

    print(f"All configs valid! ({agent_count} agents, {skill_count} skills)")


if __name__ == "__main__":
    main()
