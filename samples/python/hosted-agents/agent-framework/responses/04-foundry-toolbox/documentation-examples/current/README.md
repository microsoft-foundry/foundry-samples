---
ai-usage: ai-assisted
---

# AIProjectClient examples for 04 foundry toolbox

Use the **current** dependency set in its own virtual environment. These examples preserve their documented API generation; don't combine their dependencies with another generation.

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
| `tool-search.py` | `aip-python-112` | `FOUNDRY_PROJECT_ENDPOINT` |
| `provision-toolbox.py` | `aip-python-113` | `FOUNDRY_MCP_SERVER_URL`, `FOUNDRY_PROJECT_ENDPOINT` |
| `provision-toolbox.py` | `aip-python-114` | `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_RAI_POLICY_ID` |
| `provision-toolbox.py` | `aip-python-139` | `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_TOOLBOX_NAME` |
| `provision-toolbox.py` | `aip-python-141` | `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_TOOLBOX_NAME` |
| `work-iq-client.py` | `aip-python-120` | `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_WORK_IQ_PROJECT_CONNECTION_ID` |
| `deploy-from-code.py` | `aip-python-140` | `FOUNDRY_MODEL_NAME`, `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_SAMPLE_PATH`, `FOUNDRY_TOOLBOX_NAME` |

`FOUNDRY_SAMPLE_PATH` must point to the existing sample's executable `src` project, not its parent sample directory. The packager includes only `main.py`, `pyproject.toml`, and `uv.lock`; these reviewed runtimes don't require other local modules. It never packages `.env`, local credentials, or virtual environments. The temporary ZIP is removed even if deployment fails. Existing configured agent endpoints are restored; a newly created sample agent is removed.

## Run

Run from this directory. The explicit `--run` flag acknowledges that an example can create, update, or delete Azure resources and incur charges. Use an unused sample name for creation examples. Management examples require existing resources you own, not a production or shared agent. Read the selected function before running it.

```powershell
python tool-search.py --run --example aip-python-112
```

Use `--help` to list the supported example IDs. Examples that accept original command-line arguments receive them after `--`.

## Clean up

Run the cleanup operations shown in the selected example. Creation examples print identifiers needed for subsequent steps; retain them and delete only the resources you created. If execution stops before cleanup, use those identifiers to remove the created versions, conversations, files, vector stores, toolboxes, or memory stores. Don't delete caller-owned connections, model deployments, or external services. Use the shared [cleanup script](../../../../../../sdk/cleanup/cleanup.py) with the same active environment and `FOUNDRY_PROJECT_ENDPOINT`; run its `--help` and pass only your created identifiers with `--confirm`. The script doesn't run without explicit confirmation.

## Check locally

```powershell
python -m unittest discover -p 'test_*.py'
```

These checks compile the programs and verify imports without running examples or making Azure requests. They don't prove authentication, service availability, permissions, or end-to-end execution. No automated live-service command is declared.
