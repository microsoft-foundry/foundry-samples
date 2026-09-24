#!/usr/bin/env python3
"""Snapshot and remove Foundry resources created by one live-validation command.

Cleanup is scoped entirely by the agent name used for the run (which the
harness generates fresh per run, so it can't collide with pre-existing or
concurrently-running resources). For that name, this removes:
  - agent versions created during the run (via before/after snapshot diff)
  - the agent itself, if it did not exist before the run
  - conversations created during the run (via before/after snapshot diff of
    the Foundry conversations API's agent_name filter) -- an agent that
    already existed before the run may have had pre-existing conversations,
    so only the post-snapshot delta is removed.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen


SCHEMA_VERSION = 1
TOKEN_RESOURCE = "https://ai.azure.com"
API_VERSION = "v1"


class CleanupError(RuntimeError):
    pass


class FoundryApiError(CleanupError):
    def __init__(self, method: str, url: str, status: int, detail: str) -> None:
        super().__init__(
            f"Foundry API {method} {url} failed with HTTP {status}: {detail}"
        )
        self.status = status


def foundry_endpoint() -> str:
    endpoint = (
        os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
        or os.environ.get("AZURE_AI_PROJECT_ENDPOINT")
        or ""
    ).rstrip("/")
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.netloc:
        raise CleanupError(
            "FOUNDRY_PROJECT_ENDPOINT or AZURE_AI_PROJECT_ENDPOINT must be a valid HTTPS URL"
        )
    return endpoint


def access_token() -> str:
    try:
        completed = subprocess.run(
            [
                "az",
                "account",
                "get-access-token",
                "--resource",
                TOKEN_RESOURCE,
                "--query",
                "accessToken",
                "-o",
                "tsv",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise CleanupError("Azure CLI is required for live-resource cleanup") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or "token request failed"
        raise CleanupError(f"failed to acquire Foundry access token: {detail}") from exc
    token = completed.stdout.strip()
    if not token:
        raise CleanupError("Azure CLI returned an empty Foundry access token")
    return token


def request_json(method: str, url: str, token: str) -> dict[str, Any]:
    request = Request(
        url,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=60) as response:
            body = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise FoundryApiError(method, url, exc.code, detail) from exc
    except URLError as exc:
        raise CleanupError(f"Foundry API {method} {url} failed: {exc.reason}") from exc
    if not body:
        return {}
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise CleanupError(f"Foundry API returned invalid JSON for {method} {url}") from exc
    if not isinstance(payload, dict):
        raise CleanupError(f"Foundry API returned a non-object for {method} {url}")
    return payload


def list_agent_versions(
    endpoint: str, token: str, agent_name: str, *, missing_ok: bool = True
) -> set[str]:
    versions: set[str] = set()
    after = ""
    while True:
        query = {"api-version": API_VERSION, "limit": "100", "order": "asc"}
        if after:
            query["after"] = after
        url = (
            f"{endpoint}/agents/{quote(agent_name, safe='')}/versions?"
            f"{urlencode(query)}"
        )
        try:
            payload = request_json("GET", url, token)
        except FoundryApiError as exc:
            if exc.status == 404 and missing_ok:
                return set()
            raise
        data = payload.get("data")
        if not isinstance(data, list):
            raise CleanupError(
                f"Foundry API version list for agent {agent_name!r} has no data array"
            )
        for item in data:
            version = item.get("version") if isinstance(item, dict) else None
            if not isinstance(version, str) or not version:
                raise CleanupError(
                    f"Foundry API returned an invalid version for agent {agent_name!r}"
                )
            versions.add(version)
        if not payload.get("has_more"):
            return versions
        last_id = payload.get("last_id")
        if not isinstance(last_id, str) or not last_id or last_id == after:
            raise CleanupError(
                f"Foundry API pagination stalled for agent {agent_name!r}"
            )
        after = last_id


def agent_exists(endpoint: str, token: str, agent_name: str) -> bool:
    url = (
        f"{endpoint}/agents/{quote(agent_name, safe='')}?"
        f"{urlencode({'api-version': API_VERSION})}"
    )
    try:
        request_json("GET", url, token)
    except FoundryApiError as exc:
        if exc.status == 404:
            return False
        raise
    return True


def list_agent_conversations(endpoint: str, token: str, agent_name: str) -> set[str]:
    """List conversation IDs associated with an agent name.

    Conversations have no ARM identity and are scoped entirely by the
    (guaranteed-fresh) agent name used to create them, so anything returned
    here was necessarily created by this validation run.
    """
    conversation_ids: set[str] = set()
    after = ""
    while True:
        query = {
            "limit": "100",
            "order": "asc",
            "agent_name": agent_name,
        }
        if after:
            query["after"] = after
        url = f"{endpoint}/openai/v1/conversations?{urlencode(query)}"
        payload = request_json("GET", url, token)
        data = payload.get("data")
        if not isinstance(data, list):
            raise CleanupError(
                f"Foundry API conversation list for agent {agent_name!r} has no data array"
            )
        for item in data:
            conversation_id = item.get("id") if isinstance(item, dict) else None
            if not isinstance(conversation_id, str) or not conversation_id:
                raise CleanupError(
                    f"Foundry API returned an invalid conversation id for agent {agent_name!r}"
                )
            conversation_ids.add(conversation_id)
        if not payload.get("has_more"):
            return conversation_ids
        last_id = payload.get("last_id")
        if not isinstance(last_id, str) or not last_id or last_id == after:
            raise CleanupError(
                f"Foundry API conversation pagination stalled for agent {agent_name!r}"
            )
        after = last_id


def delete_conversation(endpoint: str, token: str, conversation_id: str) -> None:
    # /openai/v1/... paths encode their own API version; an explicit
    # api-version query parameter is rejected here (unlike the /agents/...
    # endpoints below, which are not under /v1 and do require it).
    url = f"{endpoint}/openai/v1/conversations/{quote(conversation_id, safe='')}"
    try:
        request_json("DELETE", url, token)
    except FoundryApiError as exc:
        if exc.status == 404:
            return
        raise


def take_snapshot(agent_names: list[str]) -> dict[str, Any]:
    endpoint = foundry_endpoint()
    token = access_token()
    resources: dict[str, dict[str, Any]] = {}
    for name in sorted(set(agent_names)):
        exists = agent_exists(endpoint, token, name)
        resources[name] = {
            "exists": exists,
            "versions": sorted(list_agent_versions(endpoint, token, name, missing_ok=False))
            if exists
            else [],
            "conversations": sorted(list_agent_conversations(endpoint, token, name)),
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "foundry_agent_versions": resources,
    }


def load_snapshot(path: Path) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CleanupError(f"cleanup snapshot is unreadable: {path}") from exc
    if not isinstance(payload, dict):
        raise CleanupError(f"cleanup snapshot has an unsupported schema: {path}")
    resources = payload.get("foundry_agent_versions")
    if payload.get("schema_version") != SCHEMA_VERSION or not isinstance(resources, dict):
        raise CleanupError(f"cleanup snapshot has an unsupported schema: {path}")
    normalized: dict[str, dict[str, Any]] = {}
    for name, state in resources.items():
        exists = state.get("exists") if isinstance(state, dict) else None
        versions = state.get("versions") if isinstance(state, dict) else None
        conversations = state.get("conversations") if isinstance(state, dict) else None
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(exists, bool)
            or not isinstance(versions, list)
            or any(not isinstance(version, str) or not version for version in versions)
            or (not exists and versions)
            or not isinstance(conversations, list)
            or any(
                not isinstance(conversation_id, str) or not conversation_id
                for conversation_id in conversations
            )
        ):
            raise CleanupError(f"cleanup snapshot contains an invalid agent entry: {path}")
        normalized[name] = {"exists": exists, "versions": versions, "conversations": conversations}
    return normalized


def version_sort_key(version: str) -> tuple[int, int | str]:
    return (0, int(version)) if version.isdigit() else (1, version)


def cleanup(snapshot_path: Path) -> int:
    before = load_snapshot(snapshot_path)
    endpoint = foundry_endpoint()
    token = access_token()
    deleted = 0
    for agent_name, previous_state in before.items():
        # Conversations are scoped by agent name, but an agent that already
        # existed before this run may have had pre-existing conversations
        # attached to it, so only delete the post-snapshot delta. Delete
        # these first: some Foundry deployments reject deleting an agent
        # that still has conversations.
        current_conversations = list_agent_conversations(endpoint, token, agent_name)
        created_conversations = current_conversations - set(previous_state["conversations"])
        for conversation_id in created_conversations:
            delete_conversation(endpoint, token, conversation_id)
            print(f"Deleted live-created conversation: {conversation_id} (agent {agent_name})")
            deleted += 1

        exists_now = agent_exists(endpoint, token, agent_name)
        if not previous_state["exists"]:
            if exists_now:
                url = (
                    f"{endpoint}/agents/{quote(agent_name, safe='')}?"
                    f"{urlencode({'api-version': API_VERSION})}"
                )
                request_json("DELETE", url, token)
                print(f"Deleted live-created agent: {agent_name}")
                deleted += 1
            continue
        if not exists_now:
            continue
        current_versions = list_agent_versions(endpoint, token, agent_name, missing_ok=False)
        created_versions = current_versions - set(previous_state["versions"])
        for version in sorted(created_versions, key=version_sort_key, reverse=True):
            url = (
                f"{endpoint}/agents/{quote(agent_name, safe='')}/versions/"
                f"{quote(version, safe='')}?{urlencode({'api-version': API_VERSION})}"
            )
            request_json("DELETE", url, token)
            print(f"Deleted live-created agent version: {agent_name} version {version}")
            deleted += 1
    print(f"Live-resource cleanup removed {deleted} resource(s).")
    return deleted


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    snapshot_parser = subparsers.add_parser("snapshot")
    snapshot_parser.add_argument("--output", type=Path, required=True)
    snapshot_parser.add_argument("--foundry-agent", action="append", required=True)
    cleanup_parser = subparsers.add_parser("cleanup")
    cleanup_parser.add_argument("--snapshot", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "snapshot":
            payload = take_snapshot(args.foundry_agent)
            args.output.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            print(f"Captured cleanup snapshot for {len(args.foundry_agent)} resource scope(s).")
        else:
            cleanup(args.snapshot)
    except CleanupError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
