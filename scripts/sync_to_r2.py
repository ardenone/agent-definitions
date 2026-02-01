#!/usr/bin/env python3
"""
Sync agent definitions to Cloudflare R2.

Features:
- Content-based hashing for change detection (delta sync)
- Generates manifest.json with all file hashes
- Sets Cache-Control headers for optimal caching
- Extracts cache_ttl from agent configs
"""

import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple

import boto3
import yaml


class ManifestEntry(NamedTuple):
    """Entry in the sync manifest."""

    path: str
    hash: str
    size: int
    last_modified: str
    cache_ttl: int


@dataclass
class SyncStats:
    """Statistics for a sync operation."""

    uploaded: int = 0
    skipped: int = 0
    deleted: int = 0
    errors: list[str] = field(default_factory=list)


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA256 hash of a file."""
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def get_content_hash(content: bytes) -> str:
    """Generate SHA256 hash of content."""
    return hashlib.sha256(content).hexdigest()


def get_content_type(file_path: Path) -> str:
    """Get the content type for a file based on its extension."""
    suffix = file_path.suffix.lower()
    content_types = {
        ".yaml": "application/x-yaml",
        ".yml": "application/x-yaml",
        ".json": "application/json",
        ".md": "text/markdown",
        ".txt": "text/plain",
    }
    return content_types.get(suffix, "application/octet-stream")


def get_cache_control(file_path: Path, config: dict | None = None) -> str:
    """Get Cache-Control header for a file.

    Uses cache_ttl from config if provided, otherwise defaults based on file type.
    """
    # Manifest files get shorter TTL
    if file_path.name == "manifest.json":
        ttl = 60
    elif config and "cache_ttl" in config:
        ttl = config["cache_ttl"]
    else:
        ttl = 300  # Default 5 minutes

    return f"public, max-age={ttl}, stale-while-revalidate=60"


def load_agent_config(agent_dir: Path) -> dict | None:
    """Load an agent's config.yaml if it exists."""
    config_path = agent_dir / "config.yaml"
    if not config_path.exists():
        return None
    try:
        return yaml.safe_load(config_path.read_text())
    except yaml.YAMLError:
        return None


def get_cache_ttl(config_path: Path) -> int:
    """Extract cache_ttl from agent config, default to 300."""
    try:
        config = yaml.safe_load(config_path.read_text())
        return config.get("cache_ttl", 300)
    except Exception:
        return 300


def should_upload(s3_client, bucket: str, key: str, content_hash: str) -> bool:
    """Check if file needs to be uploaded by comparing ETags."""
    try:
        response = s3_client.head_object(Bucket=bucket, Key=key)
        # R2/S3 ETag for single-part uploads is the MD5, not SHA256
        # We store our hash in metadata instead
        existing_hash = response.get("Metadata", {}).get("content-sha256", "")
        return existing_hash != content_hash
    except s3_client.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return True
        raise


def sync_file(
    s3_client,
    bucket: str,
    local_path: Path,
    key: str,
    cache_ttl: int = 300,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Sync a single file to R2.

    Returns manifest entry for this file.
    """
    content = local_path.read_bytes()
    content_hash = get_content_hash(content)
    size = len(content)

    # Determine content type
    content_type = get_content_type(local_path)

    # Check if upload needed
    needs_upload = should_upload(s3_client, bucket, key, content_hash)

    if needs_upload and not dry_run:
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
            CacheControl=f"public, max-age={cache_ttl}, stale-while-revalidate=60",
            Metadata={"content-sha256": content_hash},
        )
        print(f"Uploaded: {key}")
    elif needs_upload:
        print(f"Would upload: {key}")
    else:
        print(f"Unchanged: {key}")

    return {
        "path": key,
        "hash": content_hash,
        "size": size,
        "cache_ttl": cache_ttl,
        "uploaded": needs_upload,
    }


def sync_directory(
    s3_client,
    bucket: str,
    local_dir: Path,
    prefix: str,
    cache_ttl: int = 300,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Sync all files in a directory to R2."""
    entries = []

    if not local_dir.exists():
        return entries

    for file_path in local_dir.rglob("*"):
        if file_path.is_file():
            rel_path = file_path.relative_to(local_dir)
            key = f"{prefix}/{rel_path}"
            entry = sync_file(s3_client, bucket, file_path, key, cache_ttl, dry_run)
            entries.append(entry)

    return entries


def sync_agents(
    s3_client, bucket: str, root: Path, dry_run: bool = False
) -> list[dict[str, Any]]:
    """Sync all agents with per-agent cache_ttl."""
    entries = []
    agents_dir = root / "agents"

    if not agents_dir.exists():
        return entries

    for agent_dir in agents_dir.iterdir():
        if not agent_dir.is_dir():
            continue

        config_path = agent_dir / "config.yaml"
        cache_ttl = get_cache_ttl(config_path) if config_path.exists() else 300

        for file_path in agent_dir.glob("*"):
            if file_path.is_file():
                key = f"agents/{agent_dir.name}/{file_path.name}"
                entry = sync_file(s3_client, bucket, file_path, key, cache_ttl, dry_run)
                entries.append(entry)

    return entries


def sync_skills(
    s3_client, bucket: str, root: Path, dry_run: bool = False
) -> list[dict[str, Any]]:
    """Sync all skills."""
    entries = []
    skills_dir = root / "skills"

    if not skills_dir.exists():
        return entries

    for skill_dir in skills_dir.iterdir():
        if not skill_dir.is_dir():
            continue

        for file_path in skill_dir.glob("*"):
            if file_path.is_file():
                key = f"skills/{skill_dir.name}/{file_path.name}"
                # Skills use default cache TTL
                entry = sync_file(s3_client, bucket, file_path, key, 300, dry_run)
                entries.append(entry)

    return entries


def upload_manifest(
    s3_client, bucket: str, entries: list[dict[str, Any]], dry_run: bool = False
) -> None:
    """Generate and upload manifest.json."""
    manifest = {
        "version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entries": [
            {
                "path": e["path"],
                "hash": e["hash"],
                "size": e["size"],
                "cache_ttl": e["cache_ttl"],
            }
            for e in entries
        ],
    }

    content = json.dumps(manifest, indent=2).encode("utf-8")
    content_hash = get_content_hash(content)

    if not dry_run:
        s3_client.put_object(
            Bucket=bucket,
            Key="manifest.json",
            Body=content,
            ContentType="application/json",
            CacheControl="public, max-age=60, stale-while-revalidate=30",
            Metadata={"content-sha256": content_hash},
        )
        print("Uploaded: manifest.json")
    else:
        print("Would upload: manifest.json")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Sync agent definitions to R2")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be uploaded without uploading",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Root directory of agent-definitions repo",
    )
    args = parser.parse_args()

    # Get R2 credentials from environment
    endpoint = os.environ.get("R2_ENDPOINT")
    access_key = os.environ.get("R2_ACCESS_KEY")
    secret_key = os.environ.get("R2_SECRET_KEY")
    bucket = os.environ.get("R2_BUCKET", "botburrow-agents")

    if not all([endpoint, access_key, secret_key]):
        print("ERROR: Missing R2 credentials. Set R2_ENDPOINT, R2_ACCESS_KEY, R2_SECRET_KEY")
        sys.exit(1)

    s3_client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )

    root = args.root
    if not (root / "agents").exists():
        print(f"ERROR: {root} does not appear to be agent-definitions root")
        sys.exit(1)

    all_entries = []

    # Sync agents with per-agent cache_ttl
    print("Syncing agents...")
    all_entries.extend(sync_agents(s3_client, bucket, root, args.dry_run))

    # Sync skills
    print("Syncing skills...")
    all_entries.extend(sync_skills(s3_client, bucket, root, args.dry_run))

    # Sync schemas
    print("Syncing schemas...")
    all_entries.extend(
        sync_directory(s3_client, bucket, root / "schemas", "schemas", 3600, args.dry_run)
    )

    # Upload manifest
    print("Uploading manifest...")
    upload_manifest(s3_client, bucket, all_entries, args.dry_run)

    uploaded_count = sum(1 for e in all_entries if e["uploaded"])
    print(f"\nSync complete: {uploaded_count} files uploaded, {len(all_entries)} total files")


if __name__ == "__main__":
    main()
