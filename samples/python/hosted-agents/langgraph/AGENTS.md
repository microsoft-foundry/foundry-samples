# LangGraph Hosted Agent Samples

Applies to this directory and its descendants. Follow the
[shared Python hosted-agent instructions](../AGENTS.md) and any sample-specific
instructions. Apply new requirements to new samples and changed parts of
existing samples.

## Sample Code

- Read the target README and [shared LangGraph README](README.md) before editing.
- Keep the existing `responses/NN-name/`, `invocations/NN-name/`, and `a2a/`
  layout, with runtime code under `src/<service>`. Update the relevant sample indexes.
- Use the configuration-driven `langchain_azure_ai.agents.hosting.run` entrypoint
  by default. Use a host class when the sample requires request translation,
  options unsupported by the entrypoint, custom readiness, or async resources
  kept alive for the server lifetime.
- Default model calls to the Responses or Decisions API. Do not use Chat
  Completions. The model API is independent of the hosted endpoint protocol.
- For Responses model calls, set `store=False` because LangGraph manages message
  history. This does not disable Hosted Responses storage, `previous_response_id`,
  or checkpoint recovery.

## README

- Use the shared [README template](../README-template.md), retaining the `azd`
  and Foundry Toolkit paths supported by the sample.
- Explain graph state, checkpointing, and any sample-specific history or storage
  limits beside the interaction steps. For approvals, recovery, or downloads,
  provide a runnable client using the real host protocol.

## Startup and Telemetry

- When `main.py` only exports a graph, set `startupCommand` in `azure.yaml` to
  `uv run --no-sync python -m langchain_azure_ai.agents.hosting.run` with the
  sample's protocol and options. Keep `langgraph.json` aligned with the exported graph.
- Follow the shared telemetry rules. Use the stock host's LangChain
  instrumentation where available in the locked SDK; do not also register a
  second LangChain tracer. Document exporter and content-recording defaults for
  local and hosted runs.

## Validation

Follow the shared validation requirements. Exercise stateful client flows when
changing them, including the sample's supported approval, resume, or recovery
behavior. Distinguish local protocol checks from live Foundry and
Toolkit/Inspector validation.
