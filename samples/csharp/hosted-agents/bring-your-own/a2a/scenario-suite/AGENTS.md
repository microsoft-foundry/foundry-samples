# A2A scenario suite

This project was built with the microsoft-foundry skill. Before working on or answering questions about foundry agents, read the microsoft-foundry skill first.

Keep all twelve scenarios available as distinct agent names with fixed deployment
configuration. Test-only runs must never deploy, change source, or switch an
existing agent to another scenario. Preserve existing agents and sessions.

Generate shared sample code from the SDK's compiled snippet regions rather than
maintaining copies of their handlers. Keep deployment/version state and wire
evidence under ignored directories. Do not record tokens or connection secrets.

Each scenario needs deterministic assertions for its defining behavior. A Task
snapshot must be retrieved from a second hosted session to pass cloud persistence.
Do not silently substitute in-memory storage after an authorization/storage failure.
