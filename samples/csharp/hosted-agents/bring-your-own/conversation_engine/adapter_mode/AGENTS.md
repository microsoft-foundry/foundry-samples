# Coding instructions — CE Adapter Mode

This standalone sample exposes only the Hosted `voice_conversation_engine:1.0.0`
protocol. Bridge message version remains `1.0`. Do not modify sibling samples.

- Keep Python and .NET adapter-mode behavior, tests and docs aligned.
- Customers edit the plain streaming Echo handler and its small mapping, not the
  sample-maintained `Adapter` protocol runtime.
- Call the HTTP-shaped handler in process. Do not register HTTP invocations,
  add another service/Agent, or use a loopback/network HTTP client.
- Preserve interruption, cancellation, deadlines, ID correlation, bounded capacity,
  heard-text bookkeeping and lifecycle cleanup. Never block the receive loop.
- Drain the handler and finalization before sending success; errors after its
  SSE done event must remain failures. Do not buffer the complete response.
- Keep Echo stateless/model-free and preserve whitespace/Unicode exactly.
- No sibling-path imports, local packages, private feeds or generated VS Code files.
- Use structured logging without prompts, responses or credentials.
- Keep explicit package pins and nuget.org-only sources; publication is a deployment prerequisite.
- The shared cloud runner lacks CE support. Retain its central deployment skiplist
  entry, public owner/behavior spec, local schema/plan validation and dedicated socket tests;
  never describe these as cloud E2E.
