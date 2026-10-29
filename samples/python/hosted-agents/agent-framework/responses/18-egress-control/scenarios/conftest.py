"""Shared fixtures and helpers for egress control E2E tests.

Required environment variables:
    FOUNDRY_ENDPOINT      - e.g. https://myaccount.services.ai.azure.com/api/projects/myproject
    AGENT_NAME            - deployed agent name (e.g. egress-test-af)
    COGSVC_ACCOUNT_ID     - full ARM resource ID of the CogSvc account
    AGENT_IMAGE           - ACR image ref (digest or tag) for the hosted agent
    MODEL_DEPLOYMENT      - model deployment name (e.g. gpt-4.1)

Optional:
    RAI_BASE_POLICY       - base RAI policy name (default: Microsoft.DefaultV2)
    INVOKE_DELAY          - seconds between invocations to avoid rate limits (default: 15)

For ManagedIdentityRef tests (scenario_managed_identity.py):
    AGENT_STORAGE_ACCOUNT - storage account name (e.g. myteststorage)
    AGENT_STORAGE_CONTAINER - blob container name (default: egress-test)
"""

import json
import os
import subprocess
import time
import uuid

import pytest


# ── Config from environment ──────────────────────────────────────────────────

FOUNDRY_ENDPOINT = os.environ.get("FOUNDRY_ENDPOINT", "")
AGENT_NAME = os.environ.get("AGENT_NAME", "")
COGSVC_ACCOUNT_ID = os.environ.get("COGSVC_ACCOUNT_ID", "")
AGENT_IMAGE = os.environ.get("AGENT_IMAGE", "")
MODEL_DEPLOYMENT = os.environ.get("MODEL_DEPLOYMENT", "gpt-4.1")
RAI_BASE_POLICY = os.environ.get("RAI_BASE_POLICY", "Microsoft.DefaultV2")
INVOKE_DELAY = int(os.environ.get("INVOKE_DELAY", "15"))
AGENT_STORAGE_ACCOUNT = os.environ.get("AGENT_STORAGE_ACCOUNT", "")
AGENT_STORAGE_CONTAINER = os.environ.get("AGENT_STORAGE_CONTAINER", "egress-test")
API_VERSION = "2025-05-15-preview"
POLICY_API_VERSION = "2026-05-15-preview"

# Base RAI config needed for policy creation (content filters from the base policy)
_rai_base_cache = None


def _check_env():
    missing = []
    for var in ["FOUNDRY_ENDPOINT", "AGENT_NAME", "COGSVC_ACCOUNT_ID", "AGENT_IMAGE"]:
        if not os.environ.get(var):
            missing.append(var)
    if missing:
        pytest.skip(f"Missing required env vars: {', '.join(missing)}")


def get_token(resource: str) -> str:
    """Get an Azure access token using az CLI."""
    return subprocess.check_output(
        ["az", "account", "get-access-token", "--resource", resource,
         "--query", "accessToken", "-o", "tsv"],
        stderr=subprocess.DEVNULL,
    ).decode().strip()


def curl_json(method: str, url: str, token: str, data: dict | None = None) -> dict:
    """Make an HTTP request using curl and return parsed JSON."""
    cmd = [
        "curl", "-s", "-X", method, url,
        "-H", f"Authorization: Bearer {token}",
        "-H", "Content-Type: application/json",
    ]
    if data:
        cmd += ["-d", json.dumps(data)]
    result = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode()
    return json.loads(result) if result.strip() else {}


def get_rai_base_config() -> dict:
    """Fetch the base RAI policy config (content filters) from an existing policy."""
    global _rai_base_cache
    if _rai_base_cache is not None:
        return _rai_base_cache

    token = get_token("https://management.azure.com")
    url = (f"https://management.azure.com{COGSVC_ACCOUNT_ID}"
           f"/raiPolicies/{RAI_BASE_POLICY}?api-version={POLICY_API_VERSION}")
    r = curl_json("GET", url, token)
    props = r.get("properties", {})
    _rai_base_cache = {
        "basePolicyName": props.get("basePolicyName", RAI_BASE_POLICY),
        "contentFilters": props.get("contentFilters", []),
    }
    return _rai_base_cache


# ── Policy and agent version management ──────────────────────────────────────

def create_egress_policy(name: str, egress_policy: dict) -> bool:
    """Create or update a RAI egress policy on the CogSvc account."""
    token = get_token("https://management.azure.com")
    base_config = get_rai_base_config()
    body = {"properties": {**base_config, "egressPolicy": egress_policy}}
    url = (f"https://management.azure.com{COGSVC_ACCOUNT_ID}"
           f"/raiPolicies/{name}?api-version={POLICY_API_VERSION}")
    r = curl_json("PUT", url, token, body)
    if "error" in r:
        pytest.fail(f"Policy creation failed: {r['error'].get('message', '?')[:300]}")
    ep = r.get("properties", {}).get("egressPolicy", {})
    print(f"  Policy '{name}': mode={ep.get('mode')}, "
          f"default={ep.get('defaultAction')}, rules={len(ep.get('rules', []))}")
    return True


def delete_egress_policy(name: str):
    """Delete a RAI egress policy (best-effort cleanup)."""
    try:
        token = get_token("https://management.azure.com")
        url = (f"https://management.azure.com{COGSVC_ACCOUNT_ID}"
               f"/raiPolicies/{name}?api-version={POLICY_API_VERSION}")
        curl_json("DELETE", url, token)
    except Exception:
        pass


def deploy_agent_version(policy_name: str) -> str | None:
    """Create a new agent version with the given policy and pin traffic to it."""
    token = get_token("https://ai.azure.com")
    policy_id = f"{COGSVC_ACCOUNT_ID}/raiPolicies/{policy_name}"

    r = curl_json("POST", f"{FOUNDRY_ENDPOINT}/agents/{AGENT_NAME}/versions?api-version={API_VERSION}", token, {
        "definition": {
            "kind": "hosted",
            "image": AGENT_IMAGE,
            "container_protocol_versions": [{"protocol": "responses", "version": "2.0.0"}],
            "cpu": "1", "memory": "2Gi",
            "environment_variables": {
                "PYTHONNOUSERSITE": "1",
                "AZURE_AI_MODEL_DEPLOYMENT_NAME": MODEL_DEPLOYMENT,
                # Propagate the TLS-verification knob to the deployed agent so
                # Full-inspection scenarios can exercise a TLS-intercepting proxy.
                "EGRESS_TEST_VERIFY_TLS": os.environ.get("EGRESS_TEST_VERIFY_TLS", "true"),
            },
            "rai_config": {"rai_policy_name": policy_id},
        }
    })
    ver = r.get("version")
    if ver is None:
        pytest.fail(f"Version creation failed: {json.dumps(r.get('error', r))[:300]}")

    # Pin 100% of traffic to this version. If pinning fails, the new version may
    # never receive traffic (invocations keep hitting the previous version),
    # which would make scenario results misleading — so surface the failure.
    pin = curl_json("PATCH", f"{FOUNDRY_ENDPOINT}/agents/{AGENT_NAME}?api-version={API_VERSION}", token, {
        "agent_endpoint": {"version_selector": {"version_selection_rules": [
            {"type": "FixedRatio", "agent_version": str(ver), "traffic_percentage": 100}
        ]}}
    })
    if "error" in pin:
        pytest.fail(
            f"Traffic pinning to version {ver} failed: "
            f"{json.dumps(pin['error'])[:300]}"
        )

    # Wait for version to become active
    for _ in range(20):
        s = curl_json("GET",
                      f"{FOUNDRY_ENDPOINT}/agents/{AGENT_NAME}/versions/{ver}?api-version={API_VERSION}",
                      token)
        if s.get("status") == "active":
            print(f"  Version {ver} active")
            return str(ver)
        time.sleep(5)

    status = s.get("status", "?")
    pytest.fail(f"Version {ver} not active after 100s (status={status})")


def invoke_agent(command: str, delay: int | None = None) -> str:
    """Send a command to the deployed agent and return the text response."""
    if delay is None:
        delay = INVOKE_DELAY
    token = get_token("https://ai.azure.com")
    url = (f"{FOUNDRY_ENDPOINT}/agents/{AGENT_NAME}"
           f"/endpoint/protocols/openai/responses?api-version={API_VERSION}")
    request_body = {
        "agent_session_id": f"egress-e2e-{uuid.uuid4().hex}",
        "input": command,
        "store": False,
    }
    r = curl_json("POST", url, token, request_body)

    for retry in range(3):
        if "error" not in r:
            break
        msg = r["error"].get("message", "")
        normalized = msg.lower()
        if "429" not in msg and "rate_limit" not in normalized and "rate limit" not in normalized:
            return f"ERROR: {msg[:300]}"
        print(f"  Rate limited, retrying in 30s ({retry + 1}/3)...")
        time.sleep(30)
        token = get_token("https://ai.azure.com")
        request_body["agent_session_id"] = f"egress-e2e-{uuid.uuid4().hex}"
        r = curl_json("POST", url, token, request_body)
    if "error" in r:
        return f"ERROR: {r['error'].get('message', '?')[:300]}"

    text = ""
    for item in r.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    text += c["text"]
    time.sleep(delay)
    return text


# ── Storage helpers (for ManagedIdentityRef tests) ───────────────────────────

def storage_blob_url(path: str = "") -> str:
    """Build an Azure Blob Storage REST API URL."""
    base = f"https://{AGENT_STORAGE_ACCOUNT}.blob.core.windows.net"
    if path:
        return f"{base}/{AGENT_STORAGE_CONTAINER}/{path}"
    return f"{base}/{AGENT_STORAGE_CONTAINER}?restype=container&comp=list"


def curl_storage(method: str, url: str, token: str, data: bytes | None = None) -> tuple[int, str]:
    """Make a storage REST call and return (status_code, body).

    Uses curl with -w to capture HTTP status code separately.
    """
    cmd = [
        "curl", "-s", "-o", "/dev/stdout", "-w", "\n%{http_code}",
        "-X", method, url,
        "-H", f"Authorization: ******",
        "-H", "x-ms-version: 2023-11-03",
    ]
    if data is not None:
        cmd += ["-H", "x-ms-blob-type: BlockBlob",
                "-H", "Content-Type: application/octet-stream",
                "-d", data.decode() if isinstance(data, bytes) else data]
    result = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode()
    lines = result.rsplit("\n", 1)
    body = lines[0] if len(lines) > 1 else result
    status = int(lines[-1]) if len(lines) > 1 and lines[-1].isdigit() else 0
    return status, body


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True, scope="session")
def check_environment():
    """Skip all tests if required environment variables are missing."""
    _check_env()
