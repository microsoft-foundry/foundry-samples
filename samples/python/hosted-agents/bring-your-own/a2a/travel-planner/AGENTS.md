# A2A Copilot travel sample

Keep three independent agent packages under one azure.yaml.
Use Copilot SDK ProviderConfig and its custom-tool loop, following the
Copilot Activity sample. Toolbox tools use the standard MCP client.
No direct model HTTP calls or custom orchestration loop.
Flight/Hotel catalogs are raw dummy data only. The LLMs own filtering, prices,
rooms, eligibility and budget decisions. Do not add Python arithmetic checks,
model correction retries, forced eligible IDs or code-selected itineraries.
Keep transport errors explicit and A2A Task failure reporting intact.
Only managed Toolbox MCP tools are enabled for the planner; no built-in coding
tools. Specialists have no tools. Preserve trusted platform headers.
Do not add tests, test clients or dedicated test workflows to this sample.
Keep independent dependency locks; do not bypass package-source policy.
