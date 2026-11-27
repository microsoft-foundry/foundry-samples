---
ai-usage: ai-assisted
---

# AIProjectClient examples for 13 foundry memory

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
| `memory-store-examples.py` | `aip-python-040` | `FOUNDRY_PROJECT_ENDPOINT` |
| `memory-store-examples.py` | `aip-python-056` | `FOUNDRY_MEMORY_STORE_CHAT_MODEL_DEPLOYMENT_NAME`, `FOUNDRY_MEMORY_STORE_EMBEDDING_MODEL_DEPLOYMENT_NAME`, `FOUNDRY_PROJECT_ENDPOINT` |
| `memory-store-examples.py` | `aip-python-134` | `AZURE_AI_EMBEDDING_MODEL_DEPLOYMENT_NAME`, `FOUNDRY_MEMORY_STORE_NAME`, `FOUNDRY_MODEL_NAME`, `FOUNDRY_PROJECT_ENDPOINT` |
| `memory-store-examples.py` | `aip-python-144` | `FOUNDRY_PROJECT_ENDPOINT` |
| `deploy-from-code.py` | `aip-python-135` | `FOUNDRY_MEMORY_STORE_NAME`, `FOUNDRY_MODEL_NAME`, `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_SAMPLE_PATH` |
| `delete-memory-store.py` | `aip-python-136` | `FOUNDRY_PROJECT_ENDPOINT` |
| `delete-memory-store.py` | `aip-python-137` | `FOUNDRY_MEMORY_STORE_NAME`, `FOUNDRY_PROJECT_ENDPOINT` |

`FOUNDRY_SAMPLE_PATH` must point to the existing sample's executable `src` project, not its parent sample directory. The packager includes only `main.py`, `pyproject.toml`, and `uv.lock`; these reviewed runtimes don't require other local modules. It never packages `.env`, local credentials, or virtual environments. The temporary ZIP is removed even if deployment fails. Existing configured agent endpoints are restored; a newly created sample agent is removed.

## Run

Run from this directory. The explicit `--run` flag acknowledges that an example can create, update, or delete Azure resources and incur charges. Use an unused sample name for creation examples. Management examples require existing resources you own, not a production or shared agent. Read the selected function before running it.

```powershell
python memory-store-examples.py --run --example aip-python-040
```

Use `--help` to list the supported example IDs. Examples that accept original command-line arguments receive them after `--`.

## Clean up

Run the cleanup operations shown in the selected example. Creation examples print identifiers needed for subsequent steps; retain them and delete only the resources you created. If execution stops before cleanup, use those identifiers to remove the created versions, conversations, files, vector stores, toolboxes, or memory stores. Don't delete caller-owned connections, model deployments, or external services. Use the shared [cleanup script](../../../../../../sdk/cleanup/cleanup.py) with the same active environment and `FOUNDRY_PROJECT_ENDPOINT`; run its `--help` and pass only your created identifiers with `--confirm`. The script doesn't run without explicit confirmation.

## Check locally

```powershell
python -m unittest discover -p 'test_*.py'
```

These checks compile the programs and verify imports without running examples or making Azure requests. They don't prove authentication, service availability, permissions, or end-to-end execution. No automated live-service command is declared.
