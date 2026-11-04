# Coding Agent Instructions — Foreground/background CE migration

This Python-only sample migrates the Responses foreground/background sample to
`voice_conversation_engine:1.0.0` in one Hosted Agent process. Bridge messages use `1.0`.

## Scope and key files

- Preserve `router_agent.py`, `worker_agent.py`, and `task_store.py` verbatim from
  `bring-your-own/voicelive/foreground-background-agents-responses-voicelive`.
- `agent_logic.py` preserves that sample's model access and handler; only transport
  registration and the framework-provided context are adapted.
- `voice_runtime.py` supplies CE context, response streaming, history and cleanup.
- `protocol.py`, `state.py`, `response_coordinator.py`, and `response_telemetry.py`
  retain the existing CE sample's protocol and lifecycle handling.
- Do not add a separate Agent, HTTP hop, second registered Hosted protocol, new
  model endpoint/key configuration, proactive business notification, or backend rewrite.
- Keep barge-in distinct from cancelling a worker. Cancel session-owned workers
  on session termination, but not when an individual response is interrupted.
- Never block the CE receive loop on a model call or tool operation.

## Deployment and validation

Direct code deployment uses Python 3.13 and `main.py`. Keep `PYTHONNOUSERSITE=1`.
Use the committed `pyproject.toml`, `uv.lock`, and `uv.toml`; follow the parent
dependency policy. Run `sample.yaml` build, validation and tests, plus schema
validation and raw-evidence planning for the fixture in `.azure-pipelines`.
The shared HTTP runner cannot invoke CE; use a CE-aware client and Voice wrapper.
Do not use `azd ai agent invoke` or Agent Inspector as a CE protocol test.

The model configuration remains `FOUNDRY_PROJECT_ENDPOINT` and
`AZURE_AI_MODEL_DEPLOYMENT_NAME` through `DefaultAzureCredential` and
`AIProjectClient.get_openai_client()`, as in the original sample. Router uses Chat
Completions; Worker uses Responses. Preserve the manifest's default model.
Keep the original logging diagnostics; never add credential or bearer-token logging.
