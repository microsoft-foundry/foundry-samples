# Coding Agent Instructions

This project is a LangGraph agent hosted in Responses protocol. It can run in Microsoft Foundry or on-premises.
This sample demonstrates how to customize all the stateful parts of the agent so users have full control over the stores
in order to be flexible to host on Foundry or on-prem.
Keep documentation focused on the custom-store interfaces and how they are
wired into the host and graph. SQLite is only a simple example implementation rather than required.

## Deployment mode

- **Foundry Hosted Agents:** `azure.yaml` uses direct code deployment with
  `codeConfiguration`, Python 3.13, and `main.py` in `src/custom-store`.
  A Dockerfile is not required.
- **On-premises:** Run the same source on your infrastructure.

## Key files

- `azure.yaml` - Foundry hosted-agent manifest.
- `src/custom-store/main.py` - agent and host lifecycle
- `src/custom-store/model.py` - Foundry
  model authentication using `AZURE_AI_API_KEY` when set, otherwise Azure credentials.
- `src/custom-store/sqlite_conversation_chain_store.py`
  - custom conversation-chain store.
- `src/custom-store/sqlite_response_store.py`
- `src/custom-store/pyproject.toml` - direct dependencies.
- `src/custom-store/uv.lock` - portable, fully resolved runtime dependencies.
- `README.md` - prerequisites, deployment paths, and store behavior checks.

## Dependency workflow

Follow the [Python Hosted Agent dependency policy](../../../DEPENDENCY_POLICY.md).
`pyproject.toml` declares direct dependencies; `uv.lock` is the
consumer artifact with pinned direct and transitive dependencies.
Regenerate and commit `uv.lock` whenever dependency inputs change. Run the policy
checker documented in the shared policy, including `--resolve` when network
access is available, for dependency changes.

## Runtime logging

Use Python's standard `logging` module for runtime diagnostics. Reserve
`print()` for intentional CLI or tool-result output. Test assertions on logs
should target deliberate sample-owned events.

## Development workflow

Run from the sample root:

```bash
azd ai agent run --no-client
azd ai agent invoke --local "Remember that my project is ExampleProject."
azd deploy
azd ai agent invoke "Remember that my project is ExampleProject."
```

Provision declared resources with `azd provision` first when needed. Follow the
README for initialization and authentication. In a Toolkit-scaffolded VS Code
workspace, use **F5** and **Agent Inspector**, or follow the manual run path.

For on-premises runs, use `python main.py` from the source directory with
the required project endpoint and model deployment name in `.env`.
`AZURE_AI_API_KEY` is optional; when it is empty or absent, authenticate an
Azure identity for `DefaultAzureCredential` (for example, with `az login`
for local development). This path uses Foundry models without deploying the
agent to Foundry Hosted Agents.

## Microsoft Foundry Skill

Before working on this Foundry agent, read the microsoft-foundry skill. If you
are in VS Code, read the vscode-microsoft-foundry skill first.

Install the skill with:

```bash
npx skills add https://github.com/microsoft/azure-skills --skill microsoft-foundry
```

## References

- [Hosted agents overview](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
- [Microsoft Foundry Skill](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/use-microsoft-foundry-skill)