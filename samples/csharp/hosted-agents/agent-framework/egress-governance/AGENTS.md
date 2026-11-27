# Coding Agent Instructions - Egress governance

This Microsoft Foundry hosted agent uses an Agent Framework workflow and Responses
protocol 2.0. It is intentionally model-free; the host response is a smoke check,
while `governance.py` demonstrates service-side configuration and admission checks.

`azure.yaml` deploys the container built from `src/egress-governance/Dockerfile`.
Build locally with the .NET 10 SDK. Follow `README.md` for the staged Audit, Deny,
and cleanup commands. Run the helper's unit tests without Azure credentials before
any live run.

The admin helper and parameters are mirrored in the Python `26-egress-governance`
sample. When changing either, keep both copies byte-identical. Use a disposable
account for live assignments and retain ownership state through verified cleanup.

The public cloud test contract covers the fixed host response only. Keep the
separate governance qualification explicit in documentation and test results.
