#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
"""Read-only Foundry tracing doctor (draft, Python 3.10+ and Azure CLI).

Run from this directory after `az login` to the project's cloud and tenant:
  python3 tracing_doctor.py --project-id "<project ARM ID>"
  python3 tracing_doctor.py --project-id "<project ARM ID>" --format json

Requires read access to the project, account, connections and Monitor resources.
Role checks additionally need Microsoft.Authorization/roleAssignments/read.
No listSecrets calls, resource changes, agent invocations or telemetry writes.
Only ARM GET requests are made; the Azure CLI supplies authentication.

Output includes resource IDs, but never raw responses, credentials or CLI errors.
Exit codes: 0 = no FAIL/UNKNOWN, 1 = confirmed configuration issue, 2 = incomplete.
PASS means only that the named configuration check passed, not end-to-end health.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
from http.client import HTTPException
import json
import re
import shutil
import subprocess
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID


FOUNDRY_API = "2025-06-01"
APP_INSIGHTS_API = "2020-02-02"
WORKSPACE_API = "2023-09-01"
AMPLS_API = "2021-07-01-preview"
AUTHORIZATION_API = "2022-04-01"
PUBLISHER_ROLE = "3913510d-42f4-4e42-8a64-420c390055eb"
PROJECT_TYPE = "microsoft.cognitiveservices/accounts/projects"
APP_INSIGHTS_TYPE = "microsoft.insights/components"
WORKSPACE_TYPE = "microsoft.operationalinsights/workspaces"
AMPLS_TYPE = "microsoft.insights/privatelinkscopes"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_PAGES = 20
LIMITATIONS = (
    "Configuration only: no trace queries, ingestion writes, or DNS/TCP probes.",
    "API-key secrets are not retrieved; credential validation remains UNKNOWN.",
    "Visible role grants do not prove effective access or project-MI token acquisition.",
    "Hosted-agent exporter identity, code, and instrumentation are not inspected.",
    "Service routing, proxy versions, and regional failures need Microsoft telemetry.",
    "AMPLS endpoint approval does not prove DNS, routing, or service reachability.",
    "Unsupported APIs and inaccessible resources are UNKNOWN, not absent.",
    "Reports retain resource IDs; review them before sharing outside your organization.",
)


def field(document, name, default=None):
    if not isinstance(document, dict):
        return default
    return next(
        (value for key, value in document.items() if key.casefold() == name.casefold()),
        default,
    )


def text(document, name):
    value = field(document, name)
    return value if isinstance(value, str) else ""


def properties(document):
    value = field(document, "properties")
    return value if isinstance(value, dict) else {}


def is_guid(value):
    try:
        return isinstance(value, str) and str(UUID(value)) == value.casefold()
    except ValueError:
        return False


def resource_type(resource_id):
    if not isinstance(resource_id, str) or not resource_id.startswith("/"):
        return ""
    parts = resource_id[1:].split("/")
    if len(parts) < 8 or len(parts) % 2:
        return ""
    if [parts[index].casefold() for index in (0, 2, 4)] != [
        "subscriptions",
        "resourcegroups",
        "providers",
    ] or not is_guid(parts[1]):
        return ""
    if any(
        not re.fullmatch(r"[A-Za-z0-9_.() -]+", part) or part in (".", "..")
        for part in parts
    ):
        return ""
    return "/".join([parts[5], *parts[6::2]]).casefold()


def parse_connection_string(value):
    parts = {}
    for segment in value.split(";"):
        if not segment.strip():
            continue
        key, separator, content = segment.partition("=")
        key = key.strip().casefold()
        if not separator or not key or key in parts:
            raise ValueError("invalid_connection_string")
        parts[key] = content.strip()
    if not is_guid(parts.get("instrumentationkey")):
        raise ValueError("invalid_connection_string")
    endpoint = parts.get("ingestionendpoint")
    if endpoint and not is_https_origin(endpoint):
        raise ValueError("invalid_connection_string")
    return parts


def is_https_origin(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.port in (None, 443)
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
            and parsed.path in ("", "/")
        )
    except ValueError:
        return False


class ReadError(Exception):
    """Carries a fixed error category, never an upstream error message."""


def classify_cli_error(stderr):
    lowered = stderr.casefold()
    if any(marker in lowered for marker in ("authorizationfailed", "forbidden")):
        return "access_denied"
    if any(
        marker in lowered
        for marker in ("az login", "aadsts", "expiredauthenticationtoken")
    ):
        return "login_required"
    return "cli_failed"


def classify_http_error(error):
    try:
        body = json.loads(error.read(MAX_RESPONSE_BYTES))
        code = text(field(body, "error"), "code").casefold()
    except (ValueError, OSError, HTTPException):
        code = ""
    finally:
        error.close()
    if code in (
        "invalidapiversionparameter",
        "noregisteredproviderfound",
        "invalidresourcetype",
        "missingsubscriptionregistration",
    ):
        return "unsupported_api"
    if error.code == 404 and code in (
        "resourcenotfound",
        "resourcegroupnotfound",
        "parentresourcenotfound",
        "projectnotfound",
        "accountnotfound",
        "workspacenotfound",
    ):
        return "not_found"
    return {
        401: "authentication_failed",
        403: "access_denied",
        429: "throttled",
    }.get(error.code, "http_error")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        # Never forward an ARM bearer token to a redirected destination.
        return None


class AzureArm:
    def __init__(self, timeout=30, runner=None, opener=None):
        self.timeout = timeout
        self.runner = runner or subprocess.run
        self.opener = opener or build_opener(NoRedirect())
        self.executable = shutil.which("az")
        if not self.executable:
            raise ReadError("cli_missing")
        endpoint = self._cli_json(
            ["cloud", "show", "--query", "endpoints.resourceManager"]
        )
        if not is_https_origin(endpoint):
            raise ReadError("invalid_cloud_endpoint")
        self.endpoint = endpoint.rstrip("/")
        self.token = self._cli_json(
            [
                "account",
                "get-access-token",
                "--resource-type",
                "arm",
                "--query",
                "accessToken",
            ]
        )
        if (
            not isinstance(self.token, str)
            or not self.token
            or re.search(r"\s", self.token)
        ):
            raise ReadError("invalid_token_response")

    def _cli_json(self, arguments):
        try:
            completed = self.runner(
                [self.executable, *arguments, "--only-show-errors", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise ReadError("cli_timeout") from None
        except OSError:
            raise ReadError("cli_unavailable") from None
        if completed.returncode:
            raise ReadError(classify_cli_error(completed.stderr)) from None
        try:
            return json.loads(completed.stdout)
        except (ValueError, TypeError):
            raise ReadError("invalid_cli_response") from None

    def _url(self, path, api_version, query=None):
        if not path.casefold().startswith("/subscriptions/"):
            raise ReadError("invalid_arm_path")
        return (
            self.endpoint
            + quote(path, safe="/")
            + "?"
            + urlencode(
                {
                    "api-version": api_version,
                    **(query or {}),
                }
            )
        )

    def _get_url(self, url, expected_path):
        try:
            parsed = urlsplit(url)
        except ValueError:
            raise ReadError("unsafe_continuation") from None
        endpoint = urlsplit(self.endpoint)
        if (parsed.scheme, parsed.netloc, parsed.path) != (
            endpoint.scheme,
            endpoint.netloc,
            expected_path,
        ) or parsed.fragment:
            raise ReadError("unsafe_continuation")
        request = Request(
            url, headers={"Authorization": "Bearer " + self.token}, method="GET"
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as error:
            raise ReadError(classify_http_error(error)) from None
        except (URLError, OSError, ValueError, HTTPException):
            raise ReadError("transport_failed") from None
        if len(body) > MAX_RESPONSE_BYTES:
            raise ReadError("response_too_large")
        try:
            document = json.loads(body)
        except (ValueError, UnicodeError):
            raise ReadError("invalid_response") from None
        if not isinstance(document, dict):
            raise ReadError("invalid_response")
        return document

    def get(self, resource_id, api_version):
        url = self._url(resource_id, api_version)
        return self._get_url(url, urlsplit(url).path)

    def list(self, path, api_version, query=None):
        url = self._url(path, api_version, query)
        expected_path = urlsplit(url).path
        resources = []
        seen = set()
        while url:
            if url in seen or len(seen) >= MAX_PAGES:
                raise ReadError("pagination_limit")
            seen.add(url)
            page = self._get_url(url, expected_path)
            entries = page.get("value")
            if not isinstance(entries, list) or any(
                not isinstance(item, dict) for item in entries
            ):
                raise ReadError("invalid_response")
            resources.extend(entries)
            url = page.get("nextLink")
            if url is not None and not isinstance(url, str):
                raise ReadError("invalid_response")
        return resources


@dataclass(frozen=True)
class Finding:
    status: str
    code: str
    resource_id: str
    message: str
    recommendation: str = ""


class TracingDoctor:
    def __init__(self, azure, project_id):
        self.azure = azure
        self.project_id = project_id
        self.account_id = project_id.rsplit("/", 2)[0]
        self.findings = []

    def add(self, status, code, resource_id, message, recommendation=""):
        if not resource_type(resource_id) and isinstance(resource_id, str):
            resource_id = resource_id.rsplit("/", 1)[0]
        safe_id = resource_id if resource_type(resource_id) else self.project_id
        self.findings.append(Finding(status, code, safe_id, message, recommendation))

    def read(
        self, resource_id, api_version, *, collection=False, required=False, query=None
    ):
        try:
            if collection:
                return self.azure.list(resource_id, api_version, query)
            return self.azure.get(resource_id, api_version)
        except ReadError as error:
            status = "FAIL" if required and str(error) == "not_found" else "UNKNOWN"
            self.add(
                status,
                "RESOURCE_READ",
                resource_id,
                f"Read could not be completed ({error}).",
                "Check read permissions, resource ID, tenant/subscription access, and API support.",
            )
            return None

    def run(self):
        project = self.read(self.project_id, FOUNDRY_API, required=True)
        account = self.read(self.account_id, FOUNDRY_API)
        self.check_connections(project)
        self.check_capability_hosts(account)
        return self.findings

    def check_connections(self, project):
        project_connections = self.read(
            self.project_id + "/connections", FOUNDRY_API, collection=True
        )
        account_connections = self.read(
            self.account_id + "/connections", FOUNDRY_API, collection=True
        )
        visible = list(project_connections or [])
        visible.extend(
            connection
            for connection in account_connections or []
            if field(properties(connection), "isSharedToAll") is True
        )
        connections = {}
        found_appinsights = False
        for connection in visible:
            if text(properties(connection), "category").casefold() != "appinsights":
                continue
            found_appinsights = True
            identity = text(connection, "id")
            if not resource_type(identity):
                self.add(
                    "UNKNOWN",
                    "CONNECTION_ID",
                    self.project_id,
                    "An App Insights connection was returned without a usable resource ID.",
                )
                continue
            connections.setdefault(identity.casefold(), connection)
        if (
            not found_appinsights
            and project_connections is not None
            and account_connections is not None
        ):
            self.add(
                "FAIL",
                "CONNECTION_MISSING",
                self.project_id,
                "No project or shared account App Insights connection was returned.",
                "Connect the intended App Insights resource, then run a new agent request.",
            )
        if len(connections) > 1:
            self.add(
                "WARN",
                "CONNECTION_AMBIGUOUS",
                self.project_id,
                "Multiple App Insights connections are visible; runtime selection is not inferred.",
                "Confirm the intended destination and deliberately repair obsolete connections.",
            )
        for connection in connections.values():
            self.check_connection(connection, project)

    def check_connection(self, connection, project):
        connection_id = text(connection, "id")
        settings = properties(connection)
        target = field(settings, "target")
        metadata_id = field(field(settings, "metadata"), "ResourceId")
        target_valid = resource_type(target) == APP_INSIGHTS_TYPE
        metadata_valid = resource_type(metadata_id) == APP_INSIGHTS_TYPE
        if not target_valid:
            self.add(
                "FAIL",
                "CONNECTION_TARGET",
                connection_id,
                "Connection target is not an App Insights ARM resource ID.",
                "For AppInsights connections, target is the component ARM ID, not its connection string.",
            )
        if not metadata_valid:
            self.add(
                "WARN",
                "CONNECTION_RESOURCE_ID",
                connection_id,
                "metadata.ResourceId is missing or is not an App Insights ARM resource ID.",
                "Verify connection metadata using the supported Foundry connection setup.",
            )
        if (
            target_valid
            and metadata_valid
            and target.casefold() != metadata_id.casefold()
        ):
            self.add(
                "FAIL",
                "CONNECTION_DESTINATION_MISMATCH",
                connection_id,
                "Connection target and metadata.ResourceId identify different components.",
                "Make the connection's destination fields consistent.",
            )
        destination = (
            target if target_valid else metadata_id if metadata_valid else None
        )
        component = (
            self.read(destination, APP_INSIGHTS_API, required=True)
            if destination
            else None
        )
        self.check_authentication(connection, destination, component, project)
        if component is not None:
            self.check_component(destination, component)

    def check_authentication(self, connection, destination, component, project):
        connection_id = text(connection, "id")
        auth_type = text(properties(connection), "authType").casefold()
        if auth_type == "projectmanagedidentity":
            self.check_pmi_metadata(connection, component)
            if destination:
                self.check_publisher_role(destination, project)
        elif auth_type == "apikey":
            self.add(
                "UNKNOWN",
                "API_KEY_CONTENT",
                connection_id,
                "API-key credential content was not retrieved; ARM GET can redact it.",
                "Verify that the credential is the current full App Insights connection string; do not share it.",
            )
            if field(properties(component), "DisableLocalAuth") is True:
                self.add(
                    "FAIL",
                    "LOCAL_AUTH_DISABLED",
                    connection_id,
                    "An API-key connection targets a component with local authentication disabled.",
                    "Use the documented Entra ingestion setup; do not relax authentication automatically.",
                )
        else:
            self.add(
                "UNKNOWN",
                "CONNECTION_AUTH_TYPE",
                connection_id,
                "This draft only understands ApiKey and ProjectManagedIdentity authentication.",
            )

    def check_pmi_metadata(self, connection, component):
        connection_id = text(connection, "id")
        value = field(
            field(properties(connection), "metadata"),
            "ApplicationInsightsConnectionString",
        )
        if not isinstance(value, str) or not value.strip():
            self.add(
                "FAIL",
                "PMI_CONNECTION_STRING_MISSING",
                connection_id,
                "PMI connection has no ApplicationInsightsConnectionString metadata.",
                "Repair the connection using the documented Project Managed Identity setup.",
            )
            return
        try:
            parts = parse_connection_string(value)
        except ValueError:
            self.add(
                "FAIL",
                "CONNECTION_STRING_INVALID",
                connection_id,
                "PMI metadata is not a usable connection string (key/endpoint or duplicate fields).",
            )
            return
        expected_key = field(properties(component), "InstrumentationKey")
        if not is_guid(expected_key):
            self.add(
                "UNKNOWN",
                "PMI_CONNECTION_STRING",
                connection_id,
                "Metadata parses, but the target's instrumentation key could not be compared.",
            )
        elif parts["instrumentationkey"].casefold() != expected_key.casefold():
            self.add(
                "FAIL",
                "CONNECTION_STRING_DESTINATION",
                connection_id,
                "The metadata instrumentation key does not match the target component.",
                "Replace stale or incorrect metadata with the intended component's current connection string.",
            )
        else:
            self.add(
                "PASS",
                "PMI_CONNECTION_STRING",
                connection_id,
                "PMI metadata parses and its instrumentation key matches the target.",
            )
        self.check_ingestion_endpoint(connection_id, parts, component)

    def check_ingestion_endpoint(self, connection_id, parts, component):
        canonical = text(properties(component), "ConnectionString")
        if not canonical or not parts.get("ingestionendpoint"):
            return
        try:
            expected = parse_connection_string(canonical).get("ingestionendpoint")
        except ValueError:
            return
        if (
            expected
            and expected.rstrip("/").casefold()
            != parts["ingestionendpoint"].rstrip("/").casefold()
        ):
            self.add(
                "WARN",
                "INGESTION_ENDPOINT_MISMATCH",
                connection_id,
                "The metadata ingestion endpoint differs from the component's current connection string.",
                "Verify whether the connection is stale; this comparison does not establish reachability.",
            )

    def check_publisher_role(self, resource_id, project):
        principal_id = field(field(project, "identity"), "principalId")
        if not is_guid(principal_id):
            self.add(
                "UNKNOWN",
                "PROJECT_IDENTITY",
                self.project_id,
                "A project system-assigned principal ID could not be read.",
            )
            return
        assignments = self.read(
            resource_id + "/providers/Microsoft.Authorization/roleAssignments",
            AUTHORIZATION_API,
            collection=True,
            query={"$filter": "atScope()"},
        )
        if assignments is None:
            return
        grants = [
            properties(assignment)
            for assignment in assignments
            if text(properties(assignment), "principalId").casefold()
            == principal_id.casefold()
            and text(properties(assignment), "roleDefinitionId")
            .casefold()
            .endswith("/" + PUBLISHER_ROLE)
        ]
        if any(not field(grant, "condition") for grant in grants):
            self.add(
                "PASS",
                "INGESTION_ROLE_ASSIGNMENT",
                resource_id,
                "A Monitoring Metrics Publisher assignment is visible for the project identity.",
                "This does not test deny assignments, propagation, or token acquisition.",
            )
        else:
            self.add(
                "UNKNOWN",
                "INGESTION_ROLE_ASSIGNMENT",
                resource_id,
                "No unconditional Monitoring Metrics Publisher assignment was identified.",
                "Verify effective ingestion access, including custom/group grants and conditions.",
            )

    def check_provisioning(self, resource_id, document):
        state = text(properties(document), "provisioningState").casefold()
        if state == "succeeded":
            status, message = "PASS", "ARM reports successful resource provisioning."
        elif state in ("failed", "canceled", "deleted"):
            status, message = "FAIL", "ARM reports unsuccessful resource provisioning."
        else:
            status = "WARN" if state else "UNKNOWN"
            message = "Provisioning state was not returned or is not Succeeded."
        self.add(status, "PROVISIONING_STATE", resource_id, message)

    def check_component(self, resource_id, component):
        self.check_provisioning(resource_id, component)
        settings = properties(component)
        for setting, code in (
            ("publicNetworkAccessForIngestion", "PRIVATE_INGESTION"),
            ("publicNetworkAccessForQuery", "PRIVATE_QUERY"),
        ):
            value = text(settings, setting).casefold()
            if value == "disabled":
                self.add(
                    "WARN",
                    code,
                    resource_id,
                    "Public access is disabled; this operation needs a permitted private path.",
                    "Verify the exporter/query path. Local connectivity does not prove service reachability.",
                )
            elif value != "enabled":
                self.add(
                    "UNKNOWN",
                    code,
                    resource_id,
                    "The public-network access setting was not returned/recognized.",
                )
        workspace = self.check_workspace(resource_id, settings)
        self.check_ampls(resource_id, (settings, properties(workspace)))

    def check_workspace(self, resource_id, settings):
        workspace_id = field(settings, "WorkspaceResourceId")
        if resource_type(workspace_id) != WORKSPACE_TYPE:
            status = (
                "FAIL"
                if text(settings, "IngestionMode").casefold() == "loganalytics"
                else "UNKNOWN"
            )
            self.add(
                status,
                "WORKSPACE_LINK",
                resource_id,
                "A usable backing Log Analytics workspace ID was not returned.",
                "Verify workspace linkage; ARM cannot diagnose all backend mapping failures.",
            )
            return None
        workspace = self.read(workspace_id, WORKSPACE_API, required=True)
        if workspace is not None:
            self.check_provisioning(workspace_id, workspace)
        return workspace

    def check_ampls(self, resource_id, settings_documents):
        scope_ids = set()
        for settings in settings_documents:
            references = field(settings, "PrivateLinkScopedResources", [])
            if isinstance(references, list):
                scope_ids.update(
                    text(reference, "ResourceId")
                    for reference in references
                    if resource_type(field(reference, "ResourceId")) == AMPLS_TYPE
                )
        if not scope_ids:
            self.add(
                "WARN",
                "AMPLS_ASSOCIATIONS",
                resource_id,
                "No AMPLS references were returned on the inspected component/workspace.",
                "AMPLS is not universally required. This is not proof of missing private connectivity.",
            )
        for scope_id in sorted(scope_ids):
            scope = self.read(scope_id, AMPLS_API)
            if scope is not None:
                self.check_private_endpoints(scope_id, scope)

    def check_private_endpoints(self, resource_id, scope):
        connections = field(properties(scope), "privateEndpointConnections")
        if not isinstance(connections, list):
            self.add(
                "UNKNOWN",
                "AMPLS_PRIVATE_ENDPOINTS",
                resource_id,
                "Private endpoint connection information was not returned.",
            )
            return
        approved = bool(connections) and all(
            text(
                field(properties(connection), "privateLinkServiceConnectionState"),
                "status",
            ).casefold()
            == "approved"
            for connection in connections
        )
        self.add(
            "PASS" if approved else "WARN",
            "AMPLS_PRIVATE_ENDPOINTS",
            resource_id,
            "All returned private endpoint connections are approved; DNS/routing are not verified."
            if approved
            else "No private endpoints were returned, or some are not approved.",
        )

    def check_capability_hosts(self, account):
        inventories = {
            scope: self.read(scope + "/capabilityHosts", FOUNDRY_API, collection=True)
            for scope in (self.account_id, self.project_id)
        }
        injections = field(properties(account), "networkInjections", [])
        requires_private = isinstance(injections, list) and any(
            text(injection, "scenario").casefold() == "agent"
            and field(injection, "subnetArmId")
            for injection in injections
        )
        requires_private = requires_private or any(
            field(properties(host), "customerSubnet")
            for host in inventories[self.account_id] or []
        )
        for scope, hosts in inventories.items():
            if hosts is None:
                continue
            if not hosts:
                self.add(
                    "FAIL" if requires_private else "WARN",
                    "CAPABILITY_HOST_MISSING",
                    scope,
                    "No capability host returned for a configured private-agent setup."
                    if requires_private
                    else "No capability host returned; this can be valid for basic setup.",
                    "Verify account AND project setup for private agents; do not recreate resources automatically.",
                )
            for host in hosts:
                self.check_provisioning(text(host, "id") or scope, host)


def exit_code(findings):
    if any(finding.status == "FAIL" for finding in findings):
        return 1
    return 2 if any(finding.status == "UNKNOWN" for finding in findings) else 0


def render_report(project_id, findings, output_format):
    counts = dict(Counter(finding.status for finding in findings))
    if output_format == "json":
        return json.dumps(
            {
                "schema_version": 1,
                "project_id": project_id,
                "summary": counts,
                "limitations": LIMITATIONS,
                "findings": [asdict(item) for item in findings],
            },
            indent=2,
        )
    lines = [
        "Foundry tracing doctor - configuration-only draft",
        f"Project: {project_id}",
        "",
    ]
    for finding in findings:
        lines.extend(
            (
                f"{finding.status:7} {finding.code}",
                f"        Resource: {finding.resource_id}",
                f"        {finding.message}",
            )
        )
        if finding.recommendation:
            lines.append(f"        Action: {finding.recommendation}")
    lines.extend(
        (
            "",
            "Summary: " + ", ".join(f"{key}={value}" for key, value in counts.items()),
            "",
            "Limitations:",
            *(f"- {limitation}" for limitation in LIMITATIONS),
        )
    )
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--project-id", required=True, help="Foundry account/project ARM resource ID."
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Per CLI/HTTP request timeout in seconds (1-300).",
    )
    arguments = parser.parse_args(argv)
    project_id = arguments.project_id.rstrip("/")
    if resource_type(project_id) != PROJECT_TYPE:
        parser.error(
            "--project-id must be a full Microsoft.CognitiveServices/accounts/projects ARM ID."
        )
    if not 1 <= arguments.timeout <= 300:
        parser.error("--timeout must be between 1 and 300 seconds.")
    try:
        findings = TracingDoctor(AzureArm(arguments.timeout), project_id).run()
    except ReadError as error:
        findings = [
            Finding(
                "UNKNOWN",
                "AZURE_AUTHENTICATION",
                project_id,
                f"Azure CLI authentication could not initialize ({error}).",
                "Install Azure CLI and sign in to the intended cloud/tenant before rerunning.",
            )
        ]
    print(render_report(project_id, findings, arguments.format))
    return exit_code(findings)


if __name__ == "__main__":
    raise SystemExit(main())
