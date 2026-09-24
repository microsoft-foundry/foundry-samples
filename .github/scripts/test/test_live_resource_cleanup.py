#!/usr/bin/env python3
"""Tests for ownership-aware live-resource cleanup."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "live-resource-cleanup.py"
SPEC = importlib.util.spec_from_file_location("live_resource_cleanup", SCRIPT)
assert SPEC and SPEC.loader
cleanup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cleanup)


class LiveResourceCleanupTests(unittest.TestCase):
    def test_cleanup_deletes_only_versions_absent_from_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "snapshot.json"
            snapshot.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "foundry_agent_versions": {
                            "existing-agent": {
                                "exists": True,
                                "versions": ["1", "2"],
                                "conversations": [],
                            },
                            "new-agent": {
                                "exists": False,
                                "versions": [],
                                "conversations": [],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            current = {
                "existing-agent": {"1", "2", "3"},
                "new-agent": {"1"},
            }
            deleted_urls: list[str] = []

            def record_delete(method: str, url: str, token: str) -> dict:
                self.assertEqual(method, "DELETE")
                self.assertEqual(token, "token")
                deleted_urls.append(url)
                return {}

            with (
                mock.patch.object(cleanup, "foundry_endpoint", return_value="https://example.test/project"),
                mock.patch.object(cleanup, "access_token", return_value="token"),
                mock.patch.object(cleanup, "agent_exists", return_value=True),
                mock.patch.object(cleanup, "list_agent_conversations", return_value=set()),
                mock.patch.object(
                    cleanup,
                    "list_agent_versions",
                    side_effect=lambda endpoint, token, name, **kwargs: current[name],
                ),
                mock.patch.object(cleanup, "request_json", side_effect=record_delete),
            ):
                deleted = cleanup.cleanup(snapshot)

            self.assertEqual(deleted, 2)
            self.assertEqual(
                deleted_urls,
                [
                    "https://example.test/project/agents/existing-agent/versions/3?api-version=v1",
                    "https://example.test/project/agents/new-agent?api-version=v1",
                ],
            )
            self.assertFalse(any("/versions/1?" in url and "existing-agent" in url for url in deleted_urls))
            self.assertFalse(any("/versions/2?" in url for url in deleted_urls))

    def test_list_agent_versions_follows_cursor_pagination(self) -> None:
        pages = [
            {
                "data": [{"version": "1"}],
                "has_more": True,
                "last_id": "cursor-1",
            },
            {
                "data": [{"version": "2"}],
                "has_more": False,
                "last_id": "cursor-2",
            },
        ]
        with mock.patch.object(cleanup, "request_json", side_effect=pages) as request:
            versions = cleanup.list_agent_versions(
                "https://example.test/project", "token", "agent/name"
            )

        self.assertEqual(versions, {"1", "2"})
        self.assertEqual(request.call_count, 2)
        self.assertIn("/agents/agent%2Fname/versions?", request.call_args_list[0].args[1])
        self.assertIn("after=cursor-1", request.call_args_list[1].args[1])

    def test_cleanup_preserves_pre_existing_conversations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "snapshot.json"
            snapshot.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "foundry_agent_versions": {
                            "existing-agent": {
                                "exists": True,
                                "versions": [],
                                "conversations": ["conv_pre"],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            deleted_urls: list[str] = []

            def record_delete(method: str, url: str, token: str) -> dict:
                deleted_urls.append(url)
                return {}

            with (
                mock.patch.object(cleanup, "foundry_endpoint", return_value="https://example.test/project"),
                mock.patch.object(cleanup, "access_token", return_value="token"),
                mock.patch.object(cleanup, "agent_exists", return_value=True),
                mock.patch.object(cleanup, "list_agent_versions", return_value=set()),
                mock.patch.object(
                    cleanup,
                    "list_agent_conversations",
                    return_value={"conv_pre", "conv_new"},
                ),
                mock.patch.object(cleanup, "request_json", side_effect=record_delete),
            ):
                deleted = cleanup.cleanup(snapshot)

            self.assertEqual(deleted, 1)
            self.assertEqual(
                deleted_urls,
                ["https://example.test/project/openai/v1/conversations/conv_new"],
            )
            self.assertFalse(any("conv_pre" in url for url in deleted_urls))

    def test_missing_agent_is_an_empty_snapshot(self) -> None:
        missing = cleanup.FoundryApiError("GET", "https://example.test", 404, "not found")
        with mock.patch.object(cleanup, "request_json", side_effect=missing):
            versions = cleanup.list_agent_versions(
                "https://example.test/project", "token", "new-agent"
            )
        self.assertEqual(versions, set())

    def test_existing_agent_versions_404_fails_snapshot(self) -> None:
        missing = cleanup.FoundryApiError("GET", "https://example.test", 404, "not found")
        with (
            mock.patch.object(
                cleanup, "foundry_endpoint", return_value="https://example.test/project"
            ),
            mock.patch.object(cleanup, "access_token", return_value="token"),
            mock.patch.object(cleanup, "agent_exists", return_value=True),
            mock.patch.object(cleanup, "request_json", side_effect=missing),
        ):
            with self.assertRaises(cleanup.FoundryApiError):
                cleanup.take_snapshot(["existing-agent"])

    def test_list_agent_conversations_filters_by_agent_name_with_pagination(self) -> None:
        pages = [
            {
                "data": [{"id": "conv_1"}],
                "has_more": True,
                "last_id": "cursor-1",
            },
            {
                "data": [{"id": "conv_2"}],
                "has_more": False,
                "last_id": "cursor-2",
            },
        ]
        with mock.patch.object(cleanup, "request_json", side_effect=pages) as request:
            conversation_ids = cleanup.list_agent_conversations(
                "https://example.test/project", "token", "my-agent"
            )

        self.assertEqual(conversation_ids, {"conv_1", "conv_2"})
        self.assertEqual(request.call_count, 2)
        first_url = request.call_args_list[0].args[1]
        self.assertIn("/openai/v1/conversations?", first_url)
        self.assertIn("agent_name=my-agent", first_url)
        self.assertNotIn("api-version", first_url)
        self.assertIn("after=cursor-1", request.call_args_list[1].args[1])
        self.assertNotIn("api-version", request.call_args_list[1].args[1])

    def test_delete_conversation_treats_missing_conversation_as_success(self) -> None:
        missing = cleanup.FoundryApiError("DELETE", "https://example.test", 404, "not found")
        with mock.patch.object(cleanup, "request_json", side_effect=missing) as request:
            cleanup.delete_conversation("https://example.test/project", "token", "conv_1")
        request.assert_called_once()
        self.assertNotIn("api-version", request.call_args.args[1])

    def test_conversation_urls_omit_api_version_while_agent_urls_keep_it(self) -> None:
        """/openai/v1/... paths encode their own version; /agents/... does not."""
        with mock.patch.object(cleanup, "request_json", return_value={"data": [], "has_more": False}) as request:
            cleanup.list_agent_conversations("https://example.test/project", "token", "my-agent")
        self.assertNotIn("api-version", request.call_args.args[1])

        with mock.patch.object(cleanup, "request_json", return_value={"data": [], "has_more": False}) as request:
            cleanup.list_agent_versions("https://example.test/project", "token", "my-agent")
        self.assertIn("api-version=v1", request.call_args.args[1])

        with mock.patch.object(cleanup, "request_json", return_value={}) as request:
            cleanup.agent_exists("https://example.test/project", "token", "my-agent")
        self.assertIn("api-version=v1", request.call_args.args[1])

    def test_cleanup_deletes_conversations_before_agent_and_versions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "snapshot.json"
            snapshot.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "foundry_agent_versions": {
                            "new-agent": {"exists": False, "versions": [], "conversations": []},
                        },
                    }
                ),
                encoding="utf-8",
            )
            order: list[str] = []

            def record_delete(method: str, url: str, token: str) -> dict:
                self.assertEqual(method, "DELETE")
                order.append(url)
                return {}

            with (
                mock.patch.object(cleanup, "foundry_endpoint", return_value="https://example.test/project"),
                mock.patch.object(cleanup, "access_token", return_value="token"),
                mock.patch.object(cleanup, "agent_exists", return_value=True),
                mock.patch.object(cleanup, "list_agent_versions", return_value=set()),
                mock.patch.object(
                    cleanup,
                    "list_agent_conversations",
                    return_value={"conv_1"},
                ),
                mock.patch.object(cleanup, "request_json", side_effect=record_delete),
            ):
                deleted = cleanup.cleanup(snapshot)

            self.assertEqual(deleted, 2)
            self.assertEqual(
                order,
                [
                    "https://example.test/project/openai/v1/conversations/conv_1",
                    "https://example.test/project/agents/new-agent?api-version=v1",
                ],
            )


if __name__ == "__main__":
    unittest.main()
