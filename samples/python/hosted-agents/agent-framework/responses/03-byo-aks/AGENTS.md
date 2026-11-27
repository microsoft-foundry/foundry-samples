# Coding Agent Instructions - Agent Framework BYO AKS

This Microsoft Foundry hosted agent uses Microsoft Agent Framework and the
Responses protocol on a customer-managed AKS cluster.

## Deployment mode

`azure.yaml` provisions a Foundry project connected to an existing AKS cluster
and deploys the agent as a container with an ACR remote build. The optional
`provision_aks.sh` and `provision_aks.ps1` scripts prepare only the cluster and
sandbox node pool; they don't complete Foundry onboarding.

## Key files

- `azure.yaml` - project, model, cluster and hosted-agent configuration
- `src/agent-framework-agent-basic-responses-byoaks/main.py` - agent and GPT-OSS chat-completions compatibility path
- `src/agent-framework-agent-basic-responses-byoaks/pyproject.toml` and `uv.lock` - locked Python dependencies
- `src/agent-framework-agent-basic-responses-byoaks/Dockerfile` - container definition
- `README.md` - prerequisites, provisioning, invocation and limitations
- `tests/` - offline tests for the agent and provisioning-script safeguards

Do not commit generated `.vscode` files, local environment files, Azure
credentials, resource IDs, or deployment outputs.

## Dependency workflow

Follow `samples/python/hosted-agents/DEPENDENCY_POLICY.md`. Keep
`pyproject.toml` and `uv.lock` synchronized and run the dependency-policy
checker with `--resolve` when network access is available.

## Development workflow

Read `README.md` before provisioning. Verify the supported preview prerequisites
and subscription permissions, and preview the AKS script before applying it.
The deployment uses `azd provision`, `azd deploy`, and `azd ai agent invoke`.
Local tests do not require Azure resources.

Use Python's `logging` module for runtime diagnostics. Do not rely on mutable
framework log messages as end-to-end test evidence.

## References

- [Hosted agents overview](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents)
- [Microsoft Foundry Skill](https://learn.microsoft.com/azure/foundry/how-to/develop/use-microsoft-foundry-skill)
