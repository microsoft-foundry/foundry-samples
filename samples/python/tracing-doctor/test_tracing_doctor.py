# Copyright (c) Microsoft Corporation. All rights reserved.
"""Offline tracing-doctor regression tests. No Azure access required."""

from copy import deepcopy
from io import BytesIO
import json
import subprocess
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest

import tracing_doctor as doctor


SUBSCRIPTION = "11111111-1111-1111-1111-111111111111"
ACCOUNT = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/test/providers/Microsoft.CognitiveServices/accounts/test"
PROJECT = ACCOUNT + "/projects/test"
CONNECTION = PROJECT + "/connections/monitor"
COMPONENT = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/test/providers/Microsoft.Insights/components/test"
WORKSPACE = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/test/providers/Microsoft.OperationalInsights/workspaces/test"
AMPLS = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/test/providers/Microsoft.Insights/privateLinkScopes/test"
PRINCIPAL = "22222222-2222-2222-2222-222222222222"
KEY = "33333333-3333-3333-3333-333333333333"
OTHER_KEY = "44444444-4444-4444-4444-444444444444"
CONNECTION_STRING = (
    f"InstrumentationKey={KEY};IngestionEndpoint=https://ingestion.example.test/"
)
ROLE_PATH = COMPONENT + "/providers/Microsoft.Authorization/roleAssignments"
SECRET = "PRIVATE_CREDENTIAL_MUST_NOT_LEAK"


class FakeAzure:
    def __init__(self):
        self.resources = {
            PROJECT: {"identity": {"principalId": PRINCIPAL}},
            ACCOUNT: {"properties": {}},
            COMPONENT: {
                "properties": {
                    "provisioningState": "Succeeded",
                    "InstrumentationKey": KEY,
                    "ConnectionString": CONNECTION_STRING,
                    "WorkspaceResourceId": WORKSPACE,
                    "IngestionMode": "LogAnalytics",
                    "DisableLocalAuth": True,
                    "publicNetworkAccessForIngestion": "Enabled",
                    "publicNetworkAccessForQuery": "Enabled",
                }
            },
            WORKSPACE: {"properties": {"provisioningState": "Succeeded"}},
        }
        self.connection = {
            "id": CONNECTION,
            "properties": {
                "category": "AppInsights",
                "authType": "ProjectManagedIdentity",
                "target": COMPONENT,
                "metadata": {
                    "ResourceId": COMPONENT,
                    "ApplicationInsightsConnectionString": CONNECTION_STRING,
                },
            },
        }
        self.collections = {
            PROJECT + "/connections": [self.connection],
            ACCOUNT + "/connections": [],
            PROJECT + "/capabilityHosts": [],
            ACCOUNT + "/capabilityHosts": [],
            ROLE_PATH: [
                {
                    "properties": {
                        "principalId": PRINCIPAL,
                        "roleDefinitionId": "/providers/Microsoft.Authorization/roleDefinitions/"
                        + doctor.PUBLISHER_ROLE,
                    }
                }
            ],
        }
        self.requests = []

    def get(self, resource_id, api_version):
        self.requests.append(("get", resource_id, api_version))
        value = self.resources[resource_id]
        if isinstance(value, doctor.ReadError):
            raise value
        return deepcopy(value)

    def list(self, path, api_version, query=None):
        self.requests.append(("list", path, query))
        value = self.collections[path]
        if isinstance(value, doctor.ReadError):
            raise value
        return deepcopy(value)


@pytest.fixture
def azure():
    return FakeAzure()


@pytest.fixture
def cli_available(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda _: "/tools/az")


@pytest.fixture
def make_client(cli_available):
    def create(*pages):
        runner = Mock(
            side_effect=[
                subprocess.CompletedProcess(
                    [], 0, json.dumps("https://management.example.test/"), ""
                ),
                subprocess.CompletedProcess([], 0, json.dumps(SECRET), ""),
            ]
        )
        opener = Mock()
        opener.open.side_effect = [BytesIO(json.dumps(page).encode()) for page in pages]
        return doctor.AzureArm(runner=runner, opener=opener), opener

    return create


def diagnose(azure):
    return doctor.TracingDoctor(azure, PROJECT).run()


def statuses(findings, code):
    return [finding.status for finding in findings if finding.code == code]


def test_valid_pmi_configuration_has_no_confirmed_failure(azure):
    findings = diagnose(azure)

    assert not any(finding.status == "FAIL" for finding in findings)
    assert statuses(findings, "PMI_CONNECTION_STRING") == ["PASS"]


def test_pmi_missing_metadata_fails_without_reading_secrets(azure):
    del azure.connection["properties"]["metadata"][
        "ApplicationInsightsConnectionString"
    ]

    findings = diagnose(azure)

    assert statuses(findings, "PMI_CONNECTION_STRING_MISSING") == ["FAIL"]
    assert not any("listsecrets" in request[1].casefold() for request in azure.requests)


def test_wrong_connection_string_destination_fails(azure):
    azure.connection["properties"]["metadata"][
        "ApplicationInsightsConnectionString"
    ] = f"InstrumentationKey={OTHER_KEY}"

    findings = diagnose(azure)

    assert statuses(findings, "CONNECTION_STRING_DESTINATION") == ["FAIL"]


def test_stale_ingestion_endpoint_is_a_warning_not_a_network_diagnosis(azure):
    azure.connection["properties"]["metadata"][
        "ApplicationInsightsConnectionString"
    ] = f"InstrumentationKey={KEY};IngestionEndpoint=https://other.example.test/"

    findings = diagnose(azure)

    assert statuses(findings, "INGESTION_ENDPOINT_MISMATCH") == ["WARN"]


def test_api_key_redaction_is_unknown_not_missing_credentials(azure):
    azure.connection["properties"]["authType"] = "ApiKey"
    azure.resources[COMPONENT]["properties"]["DisableLocalAuth"] = False

    findings = diagnose(azure)

    assert statuses(findings, "API_KEY_CONTENT") == ["UNKNOWN"]
    assert not any(finding.status == "FAIL" for finding in findings)


def test_api_key_with_local_auth_disabled_is_confirmed_failure(azure):
    azure.connection["properties"]["authType"] = "ApiKey"

    findings = diagnose(azure)

    assert statuses(findings, "LOCAL_AUTH_DISABLED") == ["FAIL"]


def test_missing_connections_is_a_failure_only_after_complete_inventory(azure):
    azure.collections[PROJECT + "/connections"] = []

    findings = diagnose(azure)

    assert statuses(findings, "CONNECTION_MISSING") == ["FAIL"]


@pytest.mark.parametrize("output_format", ["text", "json"])
def test_raw_connection_values_never_appear_in_output(azure, output_format):
    azure.connection["properties"]["target"] = CONNECTION_STRING + SECRET
    azure.connection["properties"]["metadata"][
        "ApplicationInsightsConnectionString"
    ] = SECRET

    findings = diagnose(azure)
    report = doctor.render_report(PROJECT, findings, output_format)

    assert SECRET not in report
    assert KEY not in report
    assert statuses(findings, "CONNECTION_TARGET") == ["FAIL"]


def test_shared_account_connection_is_not_reported_missing(azure):
    azure.collections[PROJECT + "/connections"] = []
    azure.connection["properties"]["isSharedToAll"] = True
    azure.connection["id"] = ACCOUNT + "/connections/shared"
    azure.collections[ACCOUNT + "/connections"] = [azure.connection]

    findings = diagnose(azure)

    assert statuses(findings, "CONNECTION_MISSING") == []
    assert statuses(findings, "PMI_CONNECTION_STRING") == ["PASS"]


def test_same_shared_connection_returned_twice_is_not_ambiguous(azure):
    azure.connection["properties"]["isSharedToAll"] = True
    azure.collections[ACCOUNT + "/connections"] = [azure.connection]

    findings = diagnose(azure)

    assert statuses(findings, "CONNECTION_AMBIGUOUS") == []


def test_access_denied_inventory_is_not_an_empty_inventory(azure):
    azure.collections[PROJECT + "/connections"] = doctor.ReadError("access_denied")

    findings = diagnose(azure)

    assert statuses(findings, "CONNECTION_MISSING") == []
    assert "UNKNOWN" in statuses(findings, "RESOURCE_READ")


def test_connection_without_id_is_unknown_not_missing(azure):
    del azure.connection["id"]

    findings = diagnose(azure)

    assert statuses(findings, "CONNECTION_ID") == ["UNKNOWN"]
    assert statuses(findings, "CONNECTION_MISSING") == []


def test_multiple_connections_are_all_checked_not_silently_selected(azure):
    broken = deepcopy(azure.connection)
    broken["id"] = PROJECT + "/connections/broken"
    broken["properties"]["metadata"] = {"ResourceId": COMPONENT}
    azure.collections[PROJECT + "/connections"].append(broken)

    findings = diagnose(azure)

    assert statuses(findings, "CONNECTION_AMBIGUOUS") == ["WARN"]
    assert statuses(findings, "PMI_CONNECTION_STRING_MISSING") == ["FAIL"]


def test_private_injection_requires_both_capability_hosts(azure):
    azure.resources[ACCOUNT]["properties"]["networkInjections"] = [
        {"scenario": "agent", "subnetArmId": "/configured/subnet"}
    ]
    azure.collections[ACCOUNT + "/capabilityHosts"] = [
        {
            "id": ACCOUNT + "/capabilityHosts/agents",
            "properties": {"provisioningState": "Succeeded"},
        }
    ]

    findings = diagnose(azure)

    assert statuses(findings, "CAPABILITY_HOST_MISSING") == ["FAIL"]


def test_basic_setup_without_capability_hosts_is_not_a_confirmed_failure(azure):
    findings = diagnose(azure)

    assert statuses(findings, "CAPABILITY_HOST_MISSING") == ["WARN", "WARN"]


@pytest.mark.parametrize(
    ("category", "status"),
    [
        ("not_found", "FAIL"),
        ("access_denied", "UNKNOWN"),
        ("unsupported_api", "UNKNOWN"),
    ],
)
def test_workspace_read_failures_are_classified_without_guessing(
    azure, category, status
):
    azure.resources[WORKSPACE] = doctor.ReadError(category)

    findings = diagnose(azure)

    assert statuses(findings, "RESOURCE_READ") == [status]


def test_missing_known_role_does_not_assert_missing_effective_permission(azure):
    azure.collections[ROLE_PATH] = []

    findings = diagnose(azure)

    assert statuses(findings, "INGESTION_ROLE_ASSIGNMENT") == ["UNKNOWN"]
    assert not any(finding.status == "FAIL" for finding in findings)


def test_conditional_publisher_assignment_does_not_pass_effective_access(azure):
    azure.collections[ROLE_PATH][0]["properties"]["condition"] = "condition"

    findings = diagnose(azure)

    assert statuses(findings, "INGESTION_ROLE_ASSIGNMENT") == ["UNKNOWN"]


def test_private_endpoint_approval_does_not_pass_service_reachability(azure):
    azure.resources[COMPONENT]["properties"].update(
        {
            "publicNetworkAccessForIngestion": "Disabled",
            "PrivateLinkScopedResources": [{"ResourceId": AMPLS}],
        }
    )
    azure.resources[AMPLS] = {
        "properties": {
            "privateEndpointConnections": [
                {
                    "properties": {
                        "privateLinkServiceConnectionState": {"status": "Approved"}
                    }
                }
            ]
        }
    }

    findings = diagnose(azure)

    assert statuses(findings, "AMPLS_PRIVATE_ENDPOINTS") == ["PASS"]
    assert statuses(findings, "PRIVATE_INGESTION") == ["WARN"]


def test_uses_configured_cloud_and_only_get_requests(make_client):
    client, opener = make_client({"properties": {}})

    client.get(PROJECT, doctor.FOUNDRY_API)

    request = opener.open.call_args.args[0]
    assert request.method == "GET"
    assert request.full_url.startswith("https://management.example.test/")
    assert request.get_header("Authorization") == "Bearer " + SECRET


def test_follows_all_pages_before_returning_inventory(make_client):
    continuation = f"https://management.example.test{PROJECT}/connections?api-version=2025-06-01&skip=1"
    client, _ = make_client(
        {"value": [{"id": "first"}], "nextLink": continuation},
        {"value": [{"id": "second"}]},
    )

    resources = client.list(PROJECT + "/connections", doctor.FOUNDRY_API)

    assert resources == [{"id": "first"}, {"id": "second"}]


@pytest.mark.parametrize(
    "continuation",
    [
        "https://untrusted.example.test/collect",
        "https://management.example.test/unrelated",
        "https://[" + SECRET,
    ],
)
def test_unsafe_continuation_is_rejected_before_authenticated_request(
    make_client, continuation
):
    client, opener = make_client({"value": [], "nextLink": continuation})

    with pytest.raises(doctor.ReadError, match="^unsafe_continuation$"):
        client.list(PROJECT + "/connections", doctor.FOUNDRY_API)

    assert opener.open.call_count == 1


def test_partial_pagination_failure_does_not_return_partial_inventory(make_client):
    continuation = f"https://management.example.test{PROJECT}/connections?skip=1"
    client, opener = make_client()
    opener.open.side_effect = [
        BytesIO(
            json.dumps({"value": [{"id": "first"}], "nextLink": continuation}).encode()
        ),
        URLError(SECRET),
    ]

    with pytest.raises(doctor.ReadError, match="^transport_failed$"):
        client.list(PROJECT + "/connections", doctor.FOUNDRY_API)


def test_http_error_body_is_not_exposed(make_client):
    client, opener = make_client()
    opener.open.side_effect = HTTPError(
        "https://management.example.test", 403, SECRET, {}, BytesIO()
    )

    with pytest.raises(doctor.ReadError, match="^access_denied$"):
        client.get(PROJECT, doctor.FOUNDRY_API)


@pytest.mark.parametrize(
    ("code", "category"),
    [
        ("NoRegisteredProviderFound", "unsupported_api"),
        ("ResourceNotFound", "not_found"),
        (None, "http_error"),
    ],
)
def test_http_404_requires_explicit_evidence_of_missing_resource(
    make_client, code, category
):
    client, opener = make_client()
    opener.open.side_effect = HTTPError(
        "https://management.example.test",
        404,
        SECRET,
        {},
        BytesIO(json.dumps({"error": {"code": code, "message": SECRET}}).encode()),
    )

    with pytest.raises(doctor.ReadError, match=f"^{category}$"):
        client.get(PROJECT, doctor.FOUNDRY_API)


def test_bearer_token_is_not_forwarded_on_http_redirects():
    handler = doctor.NoRedirect()
    handler.parent = Mock()

    result = handler.http_error_302(
        doctor.Request(
            "https://management.example.test", headers={"Authorization": SECRET}
        ),
        BytesIO(),
        302,
        "redirect",
        {"location": "https://untrusted.example.test"},
    )

    assert result is None
    handler.parent.open.assert_not_called()


@pytest.mark.parametrize(
    ("runner_options", "category"),
    [
        (
            {
                "return_value": subprocess.CompletedProcess(
                    [], 1, "", "ERROR (AuthorizationFailed) " + SECRET
                )
            },
            "access_denied",
        ),
        (
            {"side_effect": subprocess.TimeoutExpired([], 30, output=SECRET)},
            "cli_timeout",
        ),
    ],
)
def test_cli_failures_do_not_expose_raw_output(cli_available, runner_options, category):
    with pytest.raises(doctor.ReadError, match=f"^{category}$"):
        doctor.AzureArm(runner=Mock(**runner_options))


def test_unknown_results_are_not_a_success_exit_code():
    findings = [doctor.Finding("UNKNOWN", "RESOURCE_READ", PROJECT, "Not inspected.")]

    assert doctor.exit_code(findings) == 2


def test_cli_initialization_failure_still_produces_json_report(monkeypatch, capsys):
    monkeypatch.setattr(
        doctor, "AzureArm", Mock(side_effect=doctor.ReadError("cli_missing"))
    )

    status = doctor.main(["--project-id", PROJECT, "--format", "json"])
    report = json.loads(capsys.readouterr().out)

    assert status == 2
    assert report["findings"][0]["code"] == "AZURE_AUTHENTICATION"


def test_invalid_project_id_is_rejected_before_authentication(monkeypatch, capsys):
    azure = Mock()
    monkeypatch.setattr(doctor, "AzureArm", azure)

    with pytest.raises(SystemExit) as failure:
        doctor.main(["--project-id", "https://untrusted.example.test/" + SECRET])

    assert failure.value.code == 2
    azure.assert_not_called()
    assert SECRET not in capsys.readouterr().err


def test_duplicate_connection_string_fields_are_rejected():
    with pytest.raises(ValueError, match="^invalid_connection_string$"):
        doctor.parse_connection_string(
            CONNECTION_STRING + ";instrumentationkey=" + OTHER_KEY
        )
