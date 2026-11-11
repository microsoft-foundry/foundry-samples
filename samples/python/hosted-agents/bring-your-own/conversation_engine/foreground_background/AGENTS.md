# Coding Agent Instructions — Foreground + Background Conversation Engine

This is the model-backed CE counterpart to the retained Responses sample. It uses Hosted protocol
`voice_conversation_engine:1.0.0` and Bridge message version `1.0`.

## Scope and implementation

- Preserve the Router, Worker, four mock domain tools, and model deployment. This is not a
  model-free story/Echo sample. Do not copy the neighboring samples' business handler here.
- Keep the sample self-contained. The native CE response coordinator, state, and telemetry were
  copied from Basic; do not introduce sibling imports, local wheels, or private feeds.
- `conversation_runtime.py` adapts business output to the existing native CE lifecycle.
- History and task stores are per physical connection. Record history after successful sends
  and reconcile `heard_text`; do not commit generated-but-unsent text.
- Track delivered task IDs explicitly, including paraphrases, and commit only after
  `response.done` sends successfully. Do not infer delivery from text substrings.
- Validate Router delivery claims against complete result bodies in its request snapshot,
  never task-store state after model I/O. Index-only results require explicit retrieval;
  concurrent Worker completion must still use an actual result-output path.
- Response interruption leaves business Workers running within the connection. End/disconnect
  requests cooperative cancellation; shutdown retains and drains in-flight Workers before
  closing clients. Do not cancel only an executor wrapper and call that drained cleanup.
- Keep receive callbacks nonblocking. Signal cancellation before awaiting terminal I/O.
- Preserve `user.barge_in`, timeouts, IDs, response limits, and terminal ownership.
- Do not forward raw upstream exceptions, prompts, model output, or credentials into logs/errors.
- The mock tools intentionally simulate latency. Tests replace that latency, not deployment code.

## Development and dependencies

Follow the parent Hosted Agent dependency policy. Regenerate `uv.lock` with dependency changes.
Use `uv sync --frozen`, pytest, Ruff, and compile/import checks declared in `sample.yaml`.
Do not configure cloud resources or run model/audio deployment tests without authorization.
The shared HTTP runner cannot exercise CE; use the documented dedicated WebSocket smoke client.
Do not claim fake-model tests validate live model permissions or deployed audio.

## Deployment

`azure.yaml` uses direct code deployment on Python 3.13 and also declares a managed Voice wrapper.
Keep the runtime directory and model deployment; initialize azd from a fresh directory.
Use distinct CE Hosted Agent and Voice wrapper names so the original Responses Agent is not
replaced when both samples are deployed in the same project. Leave the original sample unchanged.
Neither deprecated Bridge metadata key is needed. The SDK's independent legacy WS route remains
available, but only CE is declared. Agent Inspector and `azd ai agent invoke` are not CE clients.
Keep the model/identity and service-side CE rollout prerequisites explicit in the README.
Do not add generated `.vscode` files.
