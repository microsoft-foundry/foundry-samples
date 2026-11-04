# Direct A2A travel sample

Keep three independently packaged Copilot SDK agents and one deployment manifest.
No Toolbox, MCP or direct model HTTP implementation.
Fetch the configured Cards before building the planner's Copilot tools. Tool
descriptions come from Card descriptions and skills; the model selects the
specialist and message. Do not invoke specialists before model tool selection.
Require actual completed specialist Tasks and nonempty answers. No model-only
fallback on failed discovery/invocation. Validate destinations before credentials.
Hosted A2A selects the planner instance identity explicitly; preserve trusted
platform context and propagate W3C tracing. Do not copy incoming Authorization.
Preserve request context across runtime callbacks without custom discovery/tool
spans. Log lifecycle, Task IDs, durations and trace IDs, not credentials, raw
headers, user messages, answers, response bodies or arbitrary exception text.
LLMs own all travel decisions and arithmetic. No Python price checks or retries.
The planner's LLM uses user-isolated FoundryStateStore tools for saved trip IDs,
requirements, metadata, recommendations and history. Bind trusted caller context
before callbacks; never expose identity controls to the model. Version/ETag
conditions must protect writes. Requirement changes mark recommendations stale
until both specialists return fresh Tasks and a version-matched recommendation
is saved. Metadata-only changes preserve the requirement revision and pricing.
Do not add sample tests, test clients or dedicated workflows. Keep locks genuine.
