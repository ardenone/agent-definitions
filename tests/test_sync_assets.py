"""Tests for sync_assets.py script.

Per ADR-028, this script syncs ONLY binary assets to R2.
Agent configs are read directly from git by runners.
"""

import hashlib

# Import from scripts directory
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from sync_assets import (
    SyncStats,
    get_cache_control,
    get_content_hash,
    get_content_type,
    sync_file,
)


class TestGetContentHash:
    def test_computes_sha256_hash(self):
        content = b"Hello, World!"
        result = get_content_hash(content)
        expected = hashlib.sha256(content).hexdigest()
        assert result == expected

    def test_same_content_same_hash(self):
        content = b"Same content"
        assert get_content_hash(content) == get_content_hash(content)

    def test_different_content_different_hash(self):
        assert get_content_hash(b"Content A") != get_content_hash(b"Content B")


class TestGetContentType:
    @pytest.mark.parametrize(
        "filename,expected",
        [
            ("avatar.png", "image/png"),
            ("photo.jpg", "image/jpeg"),
            ("photo.jpeg", "image/jpeg"),
            ("animation.gif", "image/gif"),
            ("image.webp", "image/webp"),
            ("icon.svg", "image/svg+xml"),
            ("favicon.ico", "image/x-icon"),
            ("audio.mp3", "audio/mpeg"),
            ("video.mp4", "video/mp4"),
            ("video.webm", "video/webm"),
            ("audio.wav", "audio/wav"),
            ("document.pdf", "application/pdf"),
            ("archive.zip", "application/zip"),
            ("archive.tar.gz", "application/gzip"),
            ("unknown.xyz", "application/octet-stream"),
        ],
    )
    def test_content_types(self, filename, expected):
        result = get_content_type(Path(filename))
        assert result == expected


class TestGetCacheControl:
    @pytest.mark.parametrize(
        "filename,expected_max_age",
        [
            ("avatar.png", "86400"),  # Images get 24h cache
            ("photo.jpg", "86400"),
            ("image.webp", "86400"),
            ("icon.svg", "86400"),
            ("document.pdf", "3600"),  # Other assets get 1h cache
            ("archive.zip", "3600"),
            ("video.mp4", "3600"),
        ],
    )
    def test_cache_control_by_file_type(self, filename, expected_max_age):
        result = get_cache_control(Path(filename))
        assert f"max-age={expected_max_age}" in result
        assert "stale-while-revalidate" in result

    def test_images_have_long_cache(self):
        for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico"]:
            result = get_cache_control(Path(f"image{ext}"))
            assert "max-age=86400" in result

    def test_other_assets_have_standard_cache(self):
        for ext in [".pdf", ".zip", ".mp3", ".mp4"]:
            result = get_cache_control(Path(f"file{ext}"))
            assert "max-age=3600" in result


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


class TestSyncFile:
    def test_skips_unchanged_files(self, tmp_path):
        test_file = tmp_path / "avatar.png"
        test_file.write_bytes(b"fake image content")

        mock_s3 = MagicMock()
        mock_s3.head_object.return_value = {
            "Metadata": {"content-sha256": get_content_hash(b"fake image content")}
        }

        result = sync_file(mock_s3, "test-bucket", test_file, "agents/test/avatar.png")

        assert result["uploaded"] is False
        mock_s3.put_object.assert_not_called()

    def test_uploads_changed_files(self, tmp_path):
        test_file = tmp_path / "avatar.png"
        test_file.write_bytes(b"new content")

        mock_s3 = MagicMock()
        mock_s3.head_object.return_value = {
            "Metadata": {"content-sha256": "old-hash"}
        }

        result = sync_file(mock_s3, "test-bucket", test_file, "agents/test/avatar.png")

        assert result["uploaded"] is True
        mock_s3.put_object.assert_called_once()

    def test_uploads_new_files(self, tmp_path):
        test_file = tmp_path / "avatar.png"
        test_file.write_bytes(b"content")

        mock_s3 = MagicMock()
        error = MagicMock()
        error.response = {"Error": {"Code": "404"}}
        mock_s3.head_object.side_effect = mock_s3.exceptions.ClientError(error, "HeadObject")

        result = sync_file(mock_s3, "test-bucket", test_file, "agents/test/avatar.png")

        assert result["uploaded"] is True
        mock_s3.put_object.assert_called_once()

    def test_sets_correct_metadata(self, tmp_path):
        test_file = tmp_path / "avatar.png"
        test_file.write_bytes(b"content")

        mock_s3 = MagicMock()
        error = MagicMock()
        error.response = {"Error": {"Code": "404"}}
        mock_s3.head_object.side_effect = mock_s3.exceptions.ClientError(error, "HeadObject")

        sync_file(mock_s3, "test-bucket", test_file, "agents/test/avatar.png")

        call_args = mock_s3.put_object.call_args
        assert call_args[1]["ContentType"] == "image/png"
        assert "max-age=86400" in call_args[1]["CacheControl"]
        assert call_args[1]["Metadata"]["content-sha256"] == get_content_hash(b"content")

    def test_respects_dry_run(self, tmp_path):
        test_file = tmp_path / "avatar.png"
        test_file.write_bytes(b"content")

        mock_s3 = MagicMock()
        error = MagicMock()
        error.response = {"Error": {"Code": "404"}}
        mock_s3.head_object.side_effect = mock_s3.exceptions.ClientError(error, "HeadObject")

        sync_file(mock_s3, "test-bucket", test_file, "agents/test/avatar.png", dry_run=True)

        mock_s3.put_object.assert_not_called()
