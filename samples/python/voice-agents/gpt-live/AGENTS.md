# Coding Agent Instructions — GPT Live Response Delegation

This is a declarative Microsoft Foundry Voice Agent using `subProtocol: live`.
The agent is deployed from `azure.yaml`; `client.py` is a Native Live client, not
a hosted-agent server.

- Keep the service `kind: voice`, `subProtocol: live`, and `modelType: self_deployed`.
- Do not add Realtime/Voice Live-only fields such as avatar, telephony, VAD, STT,
  `conversationEngine`, root tools, handoff, or output modalities.
- Keep lifecycle ownership in azd. The client must only reuse `AGENT_NAME`; it
  must not create, update, or delete agents.
- Wait for service-owned `session.started`; never send `session.start`.
- Preserve delegation correlation and clean `session.closed` checks.
- Never log tokens or raw audio payloads. Test evidence must omit audio bodies.
- Keep dependencies pinned and run `sample.yaml` commands before submitting.
