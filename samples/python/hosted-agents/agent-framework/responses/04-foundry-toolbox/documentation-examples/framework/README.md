---
ai-usage: ai-assisted
---

# AIProjectClient examples for 04 foundry toolbox

Use the **framework** dependency set in its own virtual environment. These examples preserve their documented API generation; don't combine their dependencies with another generation.

## Set up

Use Python 3.13. Authenticate with `az login` and use a nonproduction project. Your identity needs permission for each demonstrated operation. Connections, deployed models, and external services are caller-owned prerequisites.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Set the required environment variables before running an example. `FOUNDRY_PROJECT_ENDPOINT` is your project's endpoint, including `/api/projects/<project>`. `FOUNDRY_MODEL_NAME`, when required, is the name of an existing compatible model deployment. Never commit credentials or populated environment files.

| Script | Example | Required configuration |
|---|---|---|
| `bing-grounding-client.py` | `aip-python-075` | `FOUNDRY_MODEL_NAME`, `FOUNDRY_PROJECT_ENDPOINT` |
| `code-interpreter-client.py` | `aip-python-080` | `FOUNDRY_MODEL_NAME`, `FOUNDRY_PROJECT_ENDPOINT` |
| `managed-connectors-client.py` | `aip-python-084` | `FOUNDRY_CONNECTOR_CONNECTION_NAME`, `FOUNDRY_CONNECTOR_MCP_URL`, `FOUNDRY_MODEL_NAME`, `FOUNDRY_PROJECT_ENDPOINT` |
| `mcp-client.py` | `aip-python-097` | `FOUNDRY_MODEL_NAME`, `FOUNDRY_PROJECT_ENDPOINT` |
| `openapi-client.py` | `aip-python-100` | `FOUNDRY_MODEL_NAME`, `FOUNDRY_OPENAPI_CONNECTION_ID`, `FOUNDRY_PROJECT_ENDPOINT` |
| `sharepoint-client.py` | `aip-python-103` | `FOUNDRY_MODEL_NAME`, `FOUNDRY_PROJECT_ENDPOINT` |
| `web-search-client.py` | `aip-python-116` | `FOUNDRY_MODEL_NAME`, `FOUNDRY_PROJECT_ENDPOINT` |

## Run

Run from this directory. The explicit `--run` flag acknowledges that an example can create, update, or delete Azure resources and incur charges. Use an unused sample name for creation examples. Management examples require existing resources you own, not a production or shared agent. Read the selected function before running it.

```powershell
python bing-grounding-client.py --run --example aip-python-075
```

Use `--help` to list the supported example IDs. Examples that accept original command-line arguments receive them after `--`.

## Clean up

Run the cleanup operations shown in the selected example. Creation examples print identifiers needed for subsequent steps; retain them and delete only the resources you created. If execution stops before cleanup, use those identifiers to remove the created versions, conversations, files, vector stores, toolboxes, or memory stores. Don't delete caller-owned connections, model deployments, or external services. Use the shared [cleanup script](../../../../../../sdk/cleanup/cleanup.py) with the same active environment and `FOUNDRY_PROJECT_ENDPOINT`; run its `--help` and pass only your created identifiers with `--confirm`. The script doesn't run without explicit confirmation.

## Check locally

```powershell
python -m unittest discover -p 'test_*.py'
```

These checks compile the programs and verify imports without running examples or making Azure requests. They don't prove authentication, service availability, permissions, or end-to-end execution. No automated live-service command is declared.
