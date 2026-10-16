# CSV and chart findings

Date tested: 2026-10-09

Environment:

- Region: Canada Central
- Model: `gpt-5.4-mini`
- Agent extension: `azure.ai.agents` 1.0.0-beta.19
- Agent: `csv-chart-analyst`
- Agent version: 1 in a fresh isolated project
- Deployment: clean `azd up --no-prompt`, without manually setting project-context variables

## Result

The GitHub Copilot harness completes the CSV-to-PNG workflow without Code Interpreter or per-file
Agent versions.

| Test | Result |
| --- | --- |
| Project Files API upload | Passed |
| Responses `input_file` automatic staging | Passed |
| Native shell CSV analysis | Passed |
| Missing `matplotlib` installation with pip | Passed |
| PNG generation in the workspace | Passed |
| Output upload to Foundry Files | Passed |
| Agent identity **Foundry User** assignment | Passed |
| Client download through project Files API | Passed |

## Evidence

The successful fresh-conversation test uploaded the 24-row CSV, staged it in the harness workspace,
calculated West as the highest-total region at `378,300`, generated
`regional_monthly_revenue_by_region.png`, uploaded it as a project file, and downloaded a valid
1744×1025 RGBA PNG through the client.

## Current response compatibility

The tested Canada Central response returned the generated filename and exact Foundry file ID as
`File` and `Download ID` text rather than as a `file_citation` annotation. The client supports that
deployed format and the first-class annotation shape expected from newer builds. Both paths download
from `/openai/v1/files/{file_id}/content`.

## Remaining caveats

- Input staging is best effort. The response should demonstrate that it used the attached data.
- The plotting package is installed at runtime when missing, so a cold workspace takes longer.
- Role assignment can take several minutes to propagate after first deployment.
- Input and output files remain in Foundry Files until explicitly deleted.
- Portal upload filtering and generated-file rendering were not part of this client validation.
