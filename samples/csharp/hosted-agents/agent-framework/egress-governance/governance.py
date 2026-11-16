# Copyright (c) Microsoft. All rights reserved.

"""Opt-in Azure Policy walkthrough. Uses Azure CLI authentication, not API keys."""

import argparse
import copy
import json
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

DEFINITIONS = {
    "baseline": "0cfd954d-079f-447f-91bf-89889e9d1de0",
    "rewrite": "64a15c51-9797-4d6b-93a5-16b19e7de23b",
    "headers": "29be091c-88f9-419b-8ad9-82ce5dc452d3",
    "agent": "d279dbb1-e60e-4ca0-8c2f-cc7a0f46166b",
}
PREFIX = "/providers/Microsoft.Authorization/policyDefinitions/"
ACCOUNT = re.compile(
    r"^/subscriptions/([0-9a-fA-F-]{36})/resourceGroups/([^/]+)/"
    r"providers/Microsoft\.CognitiveServices/accounts/([a-zA-Z0-9-]+)$",
    re.IGNORECASE,
)


def request(method, url, body=None):
    endpoint = urllib.parse.urlsplit(url)
    if endpoint.scheme != "https":
        raise ValueError("Only HTTPS is supported.")
    audience = (
        "https://management.azure.com"
        if endpoint.netloc == "management.azure.com"
        else "https://ai.azure.com"
    )
    az = shutil.which("az")
    if not az:
        raise RuntimeError("Azure CLI is required. Install it and run az login.")
    token = subprocess.check_output(
        [
            az,
            "account",
            "get-access-token",
            "--resource",
            audience,
            "--query",
            "accessToken",
            "--output",
            "tsv",
            "--only-show-errors",
        ],
        text=True,
    ).strip()
    headers = {
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
        "x-ms-client-request-id": str(uuid.uuid4()),
    }
    if audience == "https://ai.azure.com":
        headers["Foundry-Features"] = "HostedAgents=V1Preview"
    req = urllib.request.Request(
        url,
        data=None if body is None else json.dumps(body).encode(),
        headers=headers,
        method=method,
    )
    try:
        response = urllib.request.urlopen(req, timeout=180)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        raw = response.read()
        result = json.loads(raw) if raw else {}
        return response.code, result


def require(status, body, allowed=(200, 201)):
    if status not in allowed:
        raise RuntimeError(f"HTTP {status}: {json.dumps(body)}")
    return body


def save(path, state):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load(path):
    state = json.loads(path.read_text(encoding="utf-8"))
    if not ACCOUNT.fullmatch(state["account"]) or not re.fullmatch(
        r"egov-[0-9a-f]{12}", state["run"]
    ):
        raise ValueError("Invalid sample state.")
    validate_target(state["account"], state["endpoint"])
    return state


def validate_target(account, endpoint):
    match = ACCOUNT.fullmatch(account)
    url = urllib.parse.urlsplit(endpoint)
    if not match or (
        url.scheme != "https"
        or url.netloc != f"{match[3].lower()}.services.ai.azure.com"
        or not re.fullmatch(r"/api/projects/[a-zA-Z0-9._-]+", url.path)
        or url.query
        or url.fragment
    ):
        raise ValueError(
            "Use a public Azure account ID and its matching project endpoint."
        )


def initialize(args):
    if args.state.exists():
        raise ValueError(
            "State already exists. Use it for cleanup; do not overwrite it."
        )
    account = args.account_id.rstrip("/")
    endpoint = args.project_endpoint.rstrip("/")
    validate_target(account, endpoint)
    require(
        *request(
            "GET", "https://management.azure.com" + account + "?api-version=2026-09-01"
        )
    )
    require(
        *request("GET", endpoint + "/agents?api-version=v1&limit=1"), allowed=(200,)
    )
    for member, definition in DEFINITIONS.items():
        require(
            *request(
                "GET",
                "https://management.azure.com"
                + PREFIX
                + definition
                + "?api-version=2023-04-01",
            ),
            allowed=(200,),
        )
        print(f"Found published {member} definition: {definition}")
    parameters = json.loads(Path(__file__).with_name("parameters.json").read_text())
    state = {
        "run": "egov-" + uuid.uuid4().hex[:12],
        "account": account,
        "endpoint": endpoint,
        "parameters": parameters,
        "owned": [],
    }
    save(args.state, state)
    print(f"State saved to {args.state.resolve()}. No Azure writes performed.")


def own(args, state, kind, url):
    if not any(item["url"] == url for item in state["owned"]):
        require(*request("GET", url), allowed=(404,))
        state["owned"].append({"kind": kind, "url": url})
        save(args.state, state)


def assign(args, state):
    if args.confirm_account != state["account"]:
        raise ValueError(
            "--confirm-account must exactly match the disposable account ID."
        )
    selected = ["baseline", "agent"]
    if args.profile == "full":
        selected += ["rewrite", "headers"]
    for member in DEFINITIONS:
        url = (
            "https://management.azure.com"
            + state["account"]
            + "/providers/Microsoft.Authorization/policyAssignments/"
            + state["run"]
            + "-"
            + member
            + "?api-version=2024-04-01"
        )
        exists = any(item["url"] == url for item in state["owned"])
        if member not in selected and not exists:
            continue
        own(args, state, "assignment", url)
        params = {
            "effect": {"value": args.effect if member in selected else "Disabled"}
        }
        if member != "headers":
            params.update(copy.deepcopy(state["parameters"]))
            if member == "rewrite":
                params.pop("allowedActionTypes")
        properties = {
            "displayName": f"Egress governance sample: {member}",
            "description": "Disposable sample assignment; all applicable resources on this account.",
            "policyDefinitionId": PREFIX + DEFINITIONS[member],
            "enforcementMode": "Default",
            "parameters": params,
        }
        require(*request("PUT", url, {"properties": properties}))
        actual = require(*request("GET", url), allowed=(200,))["properties"]
        for field in ("policyDefinitionId", "enforcementMode", "parameters"):
            if actual[field] != properties[field]:
                raise RuntimeError("Assignment readback mismatch: " + field)
        print(f"{member}: {params['effect']['value']} ({url.split('?')[0]})")
    print(
        "Allow propagation before probing. Data-plane changes can take 30-60 minutes."
    )
    print("An assignment GET or elapsed wait alone does not prove enforcement.")


def fixture(name):
    egress = {
        "mode": "Enforced",
        "defaultAction": "Deny",
        "rules": [
            {
                "name": "sample-rule",
                "ruleType": "Fqdn",
                "match": {"host": "httpbin.org", "path": "/get"},
                "action": {"actionType": "Allow"},
            }
        ],
    }
    rule = egress["rules"][0]
    if name == "bad-source":
        rule["match"]["host"] = "unapproved.example.com"
    elif name == "bad-rewrite":
        rule["action"] = {
            "actionType": "Rewrite",
            "rewrite": {
                "scheme": "https",
                "host": "unapproved.example.com",
                "path": "/get",
            },
        }
    elif name == "bad-headers":
        rule["action"] = {
            "actionType": "Rewrite",
            "rewrite": {"scheme": "http", "host": "httpbin.org", "path": "/get"},
            "headers": [
                {
                    "name": "Authorization",
                    "operation": "Set",
                    "valueRef": {
                        "managedIdentityRef": {
                            "resource": "https://management.azure.com/"
                        }
                    },
                }
            ],
        }
    properties = {
        "basePolicyName": "Microsoft.Default",
        "mode": "Blocking",
        "contentFilters": [],
    }
    if name != "no-egress":
        properties["egressPolicy"] = egress
    return {"properties": properties}


def assert_result(status, body, expected, state, member, error_code):
    if expected == "allowed":
        require(status, body)
        return
    assignment = (
        state["account"]
        + "/providers/Microsoft.Authorization/policyAssignments/"
        + state["run"]
        + "-"
        + member
    )
    definition = PREFIX + DEFINITIONS[member]

    def attributed(value):
        if isinstance(value, dict):
            fields = {key.replace("_", "").lower(): val for key, val in value.items()}
            if (
                str(fields.get("policyassignmentid", "")).lower() == assignment.lower()
                and str(fields.get("policydefinitionid", "")).lower()
                == definition.lower()
            ):
                return True
            return any(attributed(child) for child in value.values())
        return isinstance(value, list) and any(attributed(child) for child in value)

    if (
        status != 403
        or body.get("error", {}).get("code") != error_code
        or not attributed(body)
    ):
        raise RuntimeError(
            f"Expected an attributed {member} policy denial, got HTTP {status}: "
            f"{json.dumps(body)}. Stop and inspect propagation/scope; this is not a pass."
        )


def guardrail(args, state):
    name = state["run"] + "-" + args.fixture
    resource = state["account"] + "/raiPolicies/" + name
    url = "https://management.azure.com" + resource + "?api-version=2026-09-01"
    own(args, state, "guardrail", url)
    expected_body = fixture(args.fixture)
    before_status, before = request("GET", url)
    require(before_status, before, allowed=(200, 404))
    status, body = request("PUT", url, expected_body)
    assert_result(
        status, body, args.expect, state, args.member, "RequestDisallowedByPolicy"
    )
    after_status, after = request("GET", url)
    if args.expect == "allowed":
        require(after_status, after, allowed=(200,))
        if after["properties"].get("egressPolicy") != expected_body["properties"].get(
            "egressPolicy"
        ):
            raise RuntimeError(
                "Stored egress settings differ from the requested fixture."
            )
    elif after_status != before_status or (
        before_status == 200 and after["properties"] != before["properties"]
    ):
        raise RuntimeError("Denied write changed the stored guardrail.")
    print(f"PASS: guardrail {args.fixture} {args.expect}. {resource}")


def agent(args, state):
    if not args.image or "@sha256:" not in args.image:
        raise ValueError("Supply the sample's hosted-agent image pinned with @sha256:.")
    name = state["run"] + "-agent-" + uuid.uuid4().hex[:8]
    definition = {
        "kind": "hosted",
        "cpu": "0.5",
        "memory": "1Gi",
        "image": args.image,
        "container_protocol_versions": [{"protocol": "responses", "version": "2.0.0"}],
    }
    if args.python_runtime:
        definition["environment_variables"] = {"PYTHONNOUSERSITE": "1"}
    if args.fixture != "none":
        resource = (
            state["account"] + "/raiPolicies/" + state["run"] + "-" + args.fixture
        )
        require(
            *request(
                "GET",
                "https://management.azure.com" + resource + "?api-version=2026-09-01",
            ),
            allowed=(200,),
        )
        definition["rai_config"] = {"rai_policy_name": resource}
    url = state["endpoint"] + "/agents/" + name
    own(args, state, "agent", url + "?api-version=v1")
    versions = url + "/versions?api-version=v1"
    status, body = request(
        "POST",
        versions,
        {
            "description": "Disposable egress governance sample; never invoked.",
            "definition": definition,
        },
    )
    assert_result(status, body, args.expect, state, "agent", "agent_policy_denied")
    if args.expect == "allowed":
        if not body.get("version"):
            raise RuntimeError("Creation returned no agent version.")
        stored = require(
            *request(
                "GET", url + "/versions/" + str(body["version"]) + "?api-version=v1"
            ),
            allowed=(200,),
        )
        if stored.get("definition") != body.get("definition"):
            raise RuntimeError("Agent version readback differs.")
        if stored["definition"].get("rai_config") != definition.get("rai_config"):
            raise RuntimeError(
                "Stored agent guardrail attachment differs from the request."
            )
    else:
        check_status, check = request("GET", versions)
        require(check_status, check, allowed=(200, 404))
        if check_status == 200 and (check.get("data") or check.get("has_more")):
            raise RuntimeError("A denied fresh agent has stored versions.")
    print(f"PASS: fresh hosted-agent version {args.expect}. {name}")


def cleanup(args, state):
    order = {"assignment": 0, "agent": 1, "guardrail": 2}
    for item in sorted(state["owned"], key=lambda item: order[item["kind"]]):
        if item.get("deleted"):
            continue
        url = item["url"]
        allowed_prefixes = (
            "https://management.azure.com"
            + state["account"]
            + "/providers/Microsoft.Authorization/policyAssignments/"
            + state["run"]
            + "-",
            "https://management.azure.com"
            + state["account"]
            + "/raiPolicies/"
            + state["run"]
            + "-",
            state["endpoint"] + "/agents/" + state["run"] + "-",
        )
        if not url.startswith(allowed_prefixes):
            raise ValueError("Cleanup target is outside this run's ownership prefix.")
        require(*request("DELETE", url), allowed=(200, 204, 404))
        require(*request("GET", url), allowed=(404,))
        item["deleted"] = True
        save(args.state, state)
        print("Deleted and verified absent: " + url.split("?")[0])
    print(
        "Cleanup complete. Built-ins, account, project, and other agents were not deleted."
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=Path(".egress-governance.json"))
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--account-id", required=True)
    init.add_argument("--project-endpoint", required=True)
    assignment = commands.add_parser("assign")
    assignment.add_argument("--confirm-account", required=True)
    assignment.add_argument(
        "--profile", choices=["baseline", "full"], default="baseline"
    )
    assignment.add_argument(
        "--effect", choices=["Audit", "Deny", "Disabled"], default="Audit"
    )
    rai = commands.add_parser("guardrail")
    rai.add_argument(
        "--fixture",
        choices=["good", "bad-source", "bad-rewrite", "bad-headers", "no-egress"],
        required=True,
    )
    rai.add_argument(
        "--member", choices=["baseline", "rewrite", "headers"], default="baseline"
    )
    rai.add_argument("--expect", choices=["allowed", "denied"], required=True)
    hosted = commands.add_parser("agent")
    hosted.add_argument(
        "--fixture",
        choices=["good", "no-egress", "bad-rewrite", "bad-headers", "none"],
        required=True,
    )
    hosted.add_argument("--expect", choices=["allowed", "denied"], required=True)
    hosted.add_argument("--image", required=True)
    hosted.add_argument("--python-runtime", action="store_true")
    commands.add_parser("cleanup")
    args = parser.parse_args(argv)
    if args.command == "init":
        initialize(args)
    else:
        state = load(args.state)
        {"assign": assign, "guardrail": guardrail, "agent": agent, "cleanup": cleanup}[
            args.command
        ](args, state)


if __name__ == "__main__":
    try:
        main()
    except (
        ValueError,
        KeyError,
        OSError,
        RuntimeError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
