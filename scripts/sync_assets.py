#!/usr/bin/env python3
"""
Sync binary assets to Cloudflare R2.

Per ADR-028, this script syncs ONLY binary assets to R2.
Agent configs (YAML/Markdown) are read directly from git by runners.

Binary assets include:
- Agent avatars (PNG, JPG, WebP)
- Images and media files
- Large binary skill packages

NOT synced to R2:
- config.yaml files (read from git)
- system-prompt.md files (read from git)
- SKILL.md files (read from git)
- JSON schemas (read from git)
"""

import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3


@dataclass
class SyncStats:
    """Statistics for a sync operation."""

    uploaded: int = 0
    skipped: int = 0
    deleted: int = 0
    errors: list[str] = field(default_factory=list)


def get_content_hash(content: bytes) -> str:
    """Generate SHA256 hash of content."""
    return hashlib.sha256(content).hexdigest()


def get_content_type(file_path: Path) -> str:
    """Get the content type for a file based on its extension."""
    suffix = file_path.suffix.lower()
    content_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
        ".mp3": "audio/mpeg",
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".wav": "audio/wav",
        ".pdf": "application/pdf",
        ".zip": "application/zip",
        ".tar": "application/x-tar",
        ".gz": "application/gzip",
    }
    return content_types.get(suffix, "application/octet-stream")


def get_cache_control(file_path: Path) -> str:
    """Get Cache-Control header for a file."""
    # Images get longer cache (24 hours)
    if file_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico"}:
        return "public, max-age=86400, stale-while-revalidate=3600"
    # Other assets get standard cache
    return "public, max-age=3600, stale-while-revalidate=600"


def should_upload(s3_client, bucket: str, key: str, content_hash: str) -> bool:
    """Check if file needs to be uploaded by comparing ETags."""
    try:
        response = s3_client.head_object(Bucket=bucket, Key=key)
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
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Sync a single binary asset file to R2.

    Returns manifest entry for this file.
    """
    content = local_path.read_bytes()
    content_hash = get_content_hash(content)
    size = len(content)

    # Determine content type
    content_type = get_content_type(local_path)
    cache_control = get_cache_control(local_path)

    # Check if upload needed
    needs_upload = should_upload(s3_client, bucket, key, content_hash)

    if needs_upload and not dry_run:
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
            CacheControl=cache_control,
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
        "uploaded": needs_upload,
    }


def sync_assets_directory(
    s3_client,
    bucket: str,
    local_dir: Path,
    prefix: str,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Sync all binary assets in a directory to R2.

    Only syncs binary files (images, media), skipping text files.
    """
    entries = []

    if not local_dir.exists():
        return entries

    # Binary file extensions to sync
    binary_extensions = {
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico",
        ".mp3", ".mp4", ".webm", ".wav", ".ogg",
        ".pdf", ".zip", ".tar", ".gz", ".bz2",
    }

    for file_path in local_dir.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in binary_extensions:
            rel_path = file_path.relative_to(local_dir)
            key = f"{prefix}/{rel_path}"
            entry = sync_file(s3_client, bucket, file_path, key, dry_run)
            entries.append(entry)

    return entries


def sync_agent_avatars(
    s3_client, bucket: str, root: Path, dry_run: bool = False
) -> list[dict[str, Any]]:
    """Sync agent avatar images."""
    entries = []
    agents_dir = root / "agents"

    if not agents_dir.exists():
        return entries

    for agent_dir in agents_dir.iterdir():
        if not agent_dir.is_dir():
            continue

        # Look for avatar files
        avatar_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
        for file_path in agent_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in avatar_extensions:
                key = f"agents/{agent_dir.name}/avatar{file_path.suffix}"
                entry = sync_file(s3_client, bucket, file_path, key, dry_run)
                entries.append(entry)

    return entries


def upload_manifest(
    s3_client, bucket: str, entries: list[dict[str, Any]], dry_run: bool = False
) -> None:
    """Generate and upload assets manifest.json."""
    manifest = {
        "version": "2.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "type": "assets-only",
        "description": "Binary assets manifest per ADR-028",
        "entries": [
            {
                "path": e["path"],
                "hash": e["hash"],
                "size": e["size"],
            }
            for e in entries
        ],
    }

    content = json.dumps(manifest, indent=2).encode("utf-8")
    content_hash = get_content_hash(content)

    if not dry_run:
        s3_client.put_object(
            Bucket=bucket,
            Key="assets-manifest.json",
            Body=content,
            ContentType="application/json",
            CacheControl="public, max-age=300, stale-while-revalidate=60",
            Metadata={"content-sha256": content_hash},
        )
        print("Uploaded: assets-manifest.json")
    else:
        print("Would upload: assets-manifest.json")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Sync binary assets to R2 (per ADR-028, configs are read from git)"
    )
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
    bucket = os.environ.get("R2_BUCKET", "botburrow-assets")

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

    # Sync agent avatars
    print("Syncing agent avatars...")
    all_entries.extend(sync_agent_avatars(s3_client, bucket, root, args.dry_run))

    # Sync skill assets (if any)
    print("Syncing skill assets...")
    all_entries.extend(
        sync_assets_directory(s3_client, bucket, root / "skills", "skills", args.dry_run)
    )

    # Sync template assets (if any)
    print("Syncing template assets...")
    all_entries.extend(
        sync_assets_directory(s3_client, bucket, root / "templates", "templates", args.dry_run)
    )

    # Upload manifest
    print("Uploading manifest...")
    upload_manifest(s3_client, bucket, all_entries, args.dry_run)

    uploaded_count = sum(1 for e in all_entries if e["uploaded"])
    print(f"\nSync complete: {uploaded_count} files uploaded, {len(all_entries)} total assets")


if __name__ == "__main__":
    main()
