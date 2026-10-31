# Coding Agent Instructions - Native A2A Toolbox Travel

Follow the Python hosted-agent README and dependency templates.
Three native A2A services share one runtime: flights, hotels and planner.
Only the planner uses an LLM. All remote specialist discovery and invocation
must use the managed Foundry Toolbox MCP endpoint, never direct A2A HTTP.

Keep the Flight and Hotel catalogs synthetic and independent. Require both
remote completed Tasks even for a no-match answer. Verify the requested query,
catalog data and remote Task/execution IDs before accepting a model selection.
Calculate money in integer USD cents. Never create bookings or payments.
Missing inputs need clarification; tool failures must not become model-only success.

Preserve trusted platform headers for delegated UserEntraToken connections.
Never copy incoming Authorization, persist tokens or weaken shared RBAC.
Use explicit Toolbox type `a2a` with `a2a_version: "1.0"`, not `a2a_preview`.
Runtime discovers the operation names and validates the advertised message schema;
the model selects bound-query tools without rewriting normalized constraints.

Keep the committed project and lock; the two alpha sources remain subject to
repository policy. Do not commit credentials, environments or deployment state.
Fixture tests are not real model/Azure evidence; report cloud results separately.
