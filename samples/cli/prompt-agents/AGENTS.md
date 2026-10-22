# Coding Agent Instructions — CLI prompt-agent samples

Conventions for AI agents creating or editing declarative prompt and managed-harness
agent samples under `samples/cli/prompt-agents/`. Agents read the nearest
`AGENTS.md` up the tree, so this applies to all samples in this directory.

## Choosing the right E2E test contract (prompt/managed vs. hosted)

Samples under `samples/cli/prompt-agents/` are validated by the CLI prompt-agent
pipeline (`.azure-pipelines/prompt-agents-samples-ci.yml`), **not** the
hosted-agent pipeline (`.azure-pipelines/hosted-agents-samples-ci.yml`):

| Sample location | Fixture path | Execution profile | Supported turn inputs | Supported assertions |
|---|---|---|---|---|
| `samples/<python\|csharp>/hosted-agents/<path>` | `.azure-pipelines/hosted-agent-tests/<python\|csharp>/<path>/test-spec.yml` | `hosted` | string, JSON mapping, or sequence | `assistant_text`, `raw`, `session_files`, `console_log`, `trace`, plus `approvals.mcp` |
| `samples/cli/prompt-agents/<path>` (no `harness`) | `.azure-pipelines/prompt-agent-tests/cli/<path>/test-spec.yml` | `prompt` | string only | `assistant_text` only (`contains`, `equals`, `regex`) |
| `samples/cli/prompt-agents/<path>` (`harness.type` set) | `.azure-pipelines/prompt-agent-tests/cli/<path>/test-spec.yml` | `managed` | string only | `assistant_text` only (`contains`, `equals`, `regex`) |

Every non-excluded sample under `samples/cli/prompt-agents/` must either:

1. Provide `.azure-pipelines/prompt-agent-tests/cli/<complete-sample-path>/test-spec.yml`
   with a responsible Microsoft alias in `sample.owner`, supported `experiences`,
   deterministic string-input turns, and at least one `assistant_text` assertion.
   Do **not** use `raw`, `session_files`, `console_log`, `trace`, `approvals.mcp`,
   or structured message-array inputs in prompt/managed contracts; `azd ai agent invoke`
   exposes only terminal assistant text, and contract validation rejects
   unsupported sources even on filtered-out tests.
2. Or, if the sample requires capabilities outside the prompt CI adapter (such as
   client-executed function tools, file-based skills, connections, extra Azure
   resources like Azure AI Search, or lifecycle hooks), add an entry with a
   non-empty reason in
   [`.azure-pipelines/scripts/prompt-agents/blacklist.json`](../../../.azure-pipelines/scripts/prompt-agents/blacklist.json).

## References and local validation

Read both references before adding or updating a sample or contract:

- [Prompt-agent E2E runner and manifest/contract limits](../../../.azure-pipelines/scripts/prompt-agents/README.md)
- [Shared `test-spec.yml` schema reference](../../../.azure-pipelines/hosted-agent-tests/README.md)

Run these credential-free checks from the repository root before submitting changes:

```bash
python -m pip install -r .github/scripts/requirements.txt

python .github/scripts/hosted_agent_test_spec.py validate \
  --spec .azure-pipelines/prompt-agent-tests/cli/<complete-sample-path>/test-spec.yml

python .github/scripts/hosted_agent_test_spec.py plan \
  --spec .azure-pipelines/prompt-agent-tests/cli/<complete-sample-path>/test-spec.yml \
  --protocol responses \
  --profile <prompt|managed> \
  --output /tmp/prompt-agent-test-plan.json

python .azure-pipelines/scripts/prompt-agents/discover_samples.py discover --validate-contracts
```
