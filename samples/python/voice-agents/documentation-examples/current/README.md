---
ai-usage: ai-assisted
---

# AIProjectClient examples for voice agents

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
| `voice_agent_hosted_protocol.py` | `aip-python-043` | `FOUNDRY_CONTAINER_IMAGE`, `FOUNDRY_PROJECT_ENDPOINT` |
| `voice_agent_basic.py` | `aip-python-047` | `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_VOICE_AGENT_NAME` |
| `voice_agent_basic.py` | `aip-python-128` | `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_VOICE_AGENT_NAME` |
| `voice_agent_basic.py` | `aip-python-129` | `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_VOICE_AGENT_MODEL`, `FOUNDRY_VOICE_AGENT_NAME` |
| `voice_agent_realtime_text_conversation.py` | `aip-python-057` | `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_VOICE_AGENT_NAME`, `FOUNDRY_VOICE_AGENT_VERSION` |
| `voice_agent_realtime_text_conversation.py` | `aip-python-130` | `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_VOICE_AGENT_NAME` |
| `voice_agent_subagent.py` | `aip-python-123` | `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_SUBAGENT_MODEL` |
| `voice_agent_subagent.py` | `aip-python-124` | `FOUNDRY_PROJECT_ENDPOINT` |
| `voice_agent_subagent_conversation.py` | `aip-python-125` | `FOUNDRY_PROJECT_ENDPOINT` |
| `voice_agent_telephony.py` | `aip-python-126` | `FOUNDRY_PROJECT_ENDPOINT` |
| `voice_agent_generate.py` | `aip-python-127` | `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_VOICE_AGENT_NAME` |
| `voice_agent_read_conversation.py` | `aip-python-131` | `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_VOICE_AGENT_NAME` |
| `voice_agent_cleanup.py` | `aip-python-132` | `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_VOICE_AGENT_NAME` |
| `voice_agent_hosted_target.py` | `aip-python-149` | `FOUNDRY_HOSTED_AGENT_NAME`, `FOUNDRY_HOSTED_AGENT_VERSION`, `FOUNDRY_PROJECT_ENDPOINT` |
| `voice_agent_hosted_target_conversation.py` | `aip-python-150` | `FOUNDRY_PROJECT_ENDPOINT` |

For conversation readback or cleanup, append `-- <conversation-id>` to the selected command. Use the ID from the conversation you created.

Microphone examples also require an audio input/output device and `python -m pip install -r requirements-audio.txt`. PyAudio can require PortAudio development libraries on platforms without a published wheel.

## Run

Run from this directory. The explicit `--run` flag acknowledges that an example can create, update, or delete Azure resources and incur charges. Use an unused sample name for creation examples. Management examples require existing resources you own, not a production or shared agent. Read the selected function before running it.

```powershell
python voice_agent_hosted_protocol.py --run --example aip-python-043
```

Use `--help` to list the supported example IDs. Examples that accept original command-line arguments receive them after `--`.

## Clean up

Run the cleanup operations shown in the selected example. Creation examples print identifiers needed for subsequent steps; retain them and delete only the resources you created. If execution stops before cleanup, use those identifiers to remove the created versions, conversations, files, vector stores, toolboxes, or memory stores. Don't delete caller-owned connections, model deployments, or external services. Use the shared [cleanup script](../../../sdk/cleanup/cleanup.py) with the same active environment and `FOUNDRY_PROJECT_ENDPOINT`; run its `--help` and pass only your created identifiers with `--confirm`. The script doesn't run without explicit confirmation.

## Check locally

```powershell
python -m unittest discover -p 'test_*.py'
```

These checks compile the programs and verify imports without running examples or making Azure requests. They don't prove authentication, service availability, permissions, or end-to-end execution. No automated live-service command is declared.
