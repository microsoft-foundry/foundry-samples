# .NET native A2A travel web-search sample

Read the microsoft-foundry skill before Foundry work.
Use published AgentServer A2A alpha `1.0.0-alpha.20261109.2`; no SDK source references.
The shared application runs as three separately deployed agents, selected by AGENT_ROLE.
Keep card-discovered native A2A delegation; never replace it with Toolbox A2A or direct model HTTP.
Copilot owns the model/tool loop. Only bounded Toolbox web_search is exposed to specialists.
Search is public research, not verified inventory, booking or payment.
Require actual cited search receipts and completed specialist Task IDs.
Preserve plan version/ETag checks, per-user keys, research revision binding, and explicit failures.
Use offline tests for policy/storage/protocol behavior; do not claim they prove hosted deployment.
Never commit runtime binaries, deployment state, cloud evidence, tokens or private travel data.
