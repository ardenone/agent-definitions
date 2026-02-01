"""Tests for sync_to_r2.py script."""

import hashlib
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

# Import from scripts directory
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from sync_to_r2 import (
    ManifestEntry,
    SyncStats,
    compute_file_hash,
    get_cache_control,
    get_content_type,
    load_agent_config,
)


class TestComputeFileHash:
    def test_computes_sha256_hash(self, tmp_path):
        test_file = tmp_path / "test.txt"
        content = b"Hello, World!"
        test_file.write_bytes(content)

        result = compute_file_hash(test_file)
        expected = hashlib.sha256(content).hexdigest()

        assert result == expected

    def test_same_content_same_hash(self, tmp_path):
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        content = b"Same content"
        file1.write_bytes(content)
        file2.write_bytes(content)

        assert compute_file_hash(file1) == compute_file_hash(file2)

    def test_different_content_different_hash(self, tmp_path):
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_bytes(b"Content A")
        file2.write_bytes(b"Content B")

        assert compute_file_hash(file1) != compute_file_hash(file2)


class TestGetContentType:
    @pytest.mark.parametrize(
        "filename,expected",
        [
            ("config.yaml", "application/x-yaml"),
            ("config.yml", "application/x-yaml"),
            ("schema.json", "application/json"),
            ("README.md", "text/markdown"),
            ("notes.txt", "text/plain"),
            ("unknown.xyz", "application/octet-stream"),
        ],
    )
    def test_content_types(self, filename, expected):
        result = get_content_type(Path(filename))
        assert result == expected


class TestGetCacheControl:
    def test_default_ttl(self, tmp_path):
        test_file = tmp_path / "test.yaml"
        result = get_cache_control(test_file)
        assert "max-age=300" in result
        assert "stale-while-revalidate=60" in result

    def test_custom_ttl_from_config(self, tmp_path):
        test_file = tmp_path / "test.yaml"
        config = {"cache_ttl": 60}
        result = get_cache_control(test_file, config)
        assert "max-age=60" in result

    def test_manifest_has_shorter_ttl(self, tmp_path):
        manifest_file = tmp_path / "manifest.json"
        result = get_cache_control(manifest_file)
        assert "max-age=60" in result


class TestLoadAgentConfig:
    def test_loads_config(self, tmp_path):
        agent_dir = tmp_path / "test-agent"
        agent_dir.mkdir()
        config = {"name": "test-agent", "cache_ttl": 180}
        (agent_dir / "config.yaml").write_text(yaml.dump(config))

        result = load_agent_config(agent_dir)

        assert result == config

    def test_returns_none_if_no_config(self, tmp_path):
        agent_dir = tmp_path / "no-config"
        agent_dir.mkdir()

        result = load_agent_config(agent_dir)

        assert result is None


class TestSyncStats:
    def test_initial_values(self):
        stats = SyncStats()
        assert stats.uploaded == 0
        assert stats.skipped == 0
        assert stats.deleted == 0
        assert stats.errors == []

    def test_tracks_values(self):
        stats = SyncStats()
        stats.uploaded = 5
        stats.skipped = 3
        stats.errors.append("Error 1")

        assert stats.uploaded == 5
        assert stats.skipped == 3
        assert len(stats.errors) == 1


class TestManifestEntry:
    def test_creates_entry(self):
        entry = ManifestEntry(
            path="agents/test/config.yaml",
            hash="abc123",
            size=1024,
            last_modified="2026-02-01T00:00:00Z",
            cache_ttl=300,
        )

        assert entry.path == "agents/test/config.yaml"
        assert entry.hash == "abc123"
        assert entry.size == 1024
        assert entry.cache_ttl == 300
