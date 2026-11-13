# Foundry tracing doctor

Check Azure resource configuration for common causes of missing Foundry agent
traces in Application Insights. The diagnostic reports findings and suggested
actions without changing resources, granting permissions, or invoking agents.

## Prerequisites

- Python 3.10 or later and Azure CLI. No additional Python packages are needed
  to run the diagnostic.
- An Azure CLI login for the cloud and tenant containing the project.
- Read access to the Foundry account and project, connections, connected
  Application Insights component, backing Log Analytics workspace, and relevant
  Azure Monitor Private Link Scopes (AMPLS).
- `Microsoft.Authorization/roleAssignments/read` for the ingestion role check.

The supported project resource type is
`Microsoft.CognitiveServices/accounts/projects`. Classic hub-based projects
are not supported.

## Run

From this directory:

```bash
az login
python tracing_doctor.py --project-id "<Foundry project ARM resource ID>"
```

Use the full ARM ID, not the project endpoint:

```text
/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>
```

For JSON output:

```bash
python tracing_doctor.py --project-id "<project ARM ID>" --format json
```

Use `--timeout 60` to change the per-request timeout from its default of 30 seconds.
The diagnostic uses your existing Azure CLI cloud and authentication without
changing your active subscription, cloud, or tenant.

## Checks

- Missing, conflicting, or malformed App Insights connection destinations.
- Missing or inconsistent Project Managed Identity connection-string metadata.
- API-key connections targeting App Insights with local authentication disabled.
- Visible Monitoring Metrics Publisher assignments for the project identity.
- App Insights workspace linkage and resource provisioning states.
- Private ingestion/query settings, AMPLS associations, and endpoint approvals.
- Missing account/project capability hosts when private-agent setup requires them.

## Results

| Status | Meaning |
| --- | --- |
| `PASS` | The named configuration check passed. |
| `FAIL` | A configuration problem was identified. |
| `WARN` | A condition needs review but is not independently proof of failure. |
| `UNKNOWN` | A result could not be established, including because of permissions or unsupported APIs. |

Exit codes are `1` when any `FAIL` exists, `2` when no `FAIL` exists but at least
one check is `UNKNOWN`, and `0` otherwise. Invalid arguments also exit `2`.

These are configuration checks, not an end-to-end tracing test. They do not
validate API-key secrets, query trace tables, inspect hosted-agent instrumentation,
or test DNS, firewall rules, routes, or ingestion reachability. Visible role grants
do not prove effective authorization or managed-identity token acquisition.
Microsoft-managed proxy versions and regional token-routing failures require
service-side investigation.

The diagnostic only makes ARM GET requests. Reports exclude raw responses,
tokens, connection strings, and conversation content. They retain resource IDs;
review them before sharing outside your organization.

## Development

From this directory, in an activated Python environment:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q test_tracing_doctor.py
```

From the repository root, run the standard sample validator with Python, Bash,
and `yq` v4 available:

```bash
bash .github/scripts/validate-sample.sh \
  --language python \
  --sample-dir samples/python/tracing-doctor
```

Validation compiles the Python files and runs offline pytest tests.
No live-service validation is configured.
