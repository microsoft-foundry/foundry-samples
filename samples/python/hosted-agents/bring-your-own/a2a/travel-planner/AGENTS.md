# Coding Agent Instructions - Native A2A Toolbox Travel

Follow the Python hosted-agent README and dependency templates.
One azure.yaml defines three independent native A2A packages:
src/travel-agent, src/flight-agent and src/hotel-agent. Each has its own
main.py, pyproject.toml and uv.lock; do not reintroduce an AGENT_ROLE switch.
Only the planner uses an LLM. All remote specialist discovery and invocation
must use the managed Foundry Toolbox MCP endpoint, never direct A2A HTTP.

Keep the Flight and Hotel catalogs synthetic and independent. Require both
remote completed Tasks even for a no-match answer. Verify the requested query,
response contracts, constraints, prices and remote Task/execution IDs before accepting a model selection.
The planner must not contain or import either specialist's inventory/search code.
Calculate money in integer USD cents. Never create bookings or payments.
Missing inputs need clarification; tool failures must not become model-only success.

Preserve trusted platform headers for delegated UserEntraToken connections.
Never copy incoming Authorization, persist tokens or weaken shared RBAC.
Use explicit Toolbox type `a2a` with `a2a_version: "1.0"`, not `a2a_preview`.
Runtime discovers the operation names and validates the advertised message schema;
the model selects bound-query tools without rewriting normalized constraints.

Keep the committed project and lock; the two alpha sources remain subject to
repository policy. Do not commit credentials, environments or deployment state.
Do not add a sample tests folder. Keep the shared harness and cloud behavior
contracts wired to the independent packages. Report live verification separately.
