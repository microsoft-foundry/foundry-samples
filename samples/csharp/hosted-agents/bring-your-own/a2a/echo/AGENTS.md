# .NET A2A Echo development sample

This project was built with the microsoft-foundry skill. Before working on or answering questions about foundry agents, read the microsoft-foundry skill first.

This is a source-built reference sample for the unpublished .NET A2A hosting
library. Keep the SDK dependency as a project reference; do not introduce a
published or alpha package dependency without the author's request.

Preserve deterministic Echo, native A2A Task/artifact shapes, and normal requests
without artificial delay. Paced streaming is opt-in through message metadata.
Use the dedicated .NET client to prove incremental delivery, exact output, and
GetTask consistency. HTTP success alone does not establish streaming success.

Do not silently fix hosting-library defects inside the sample. Keep the explicit
native in-memory store, and document that persistence and SDK contract gaps are
not covered by this sample. Do not edit the Python reference or shared CI
exclusions to make this sample pass.

Keep deployment copies outside the template, use a distinct agent name, and do
not commit SDK binaries, cloud state, sessions, tokens, or runtime evidence.
