# Quickstart: Web Research

A complete, runnable version of the Microsoft Foundry quickstart for creating a Prompt Agent that
uses the Microsoft Copilot harness, declared Web Search, and a reusable Skill. Use this sample to inspect
the finished project, follow the scenario without assembling files by hand, or run the same workflow
as an automated smoke test.

One `azd up` creates:

- a Microsoft Foundry account, project, and `gpt-5.4-mini` model deployment;
- the immutable `official-source-research` Skill; and
- the `web-research-agent` Prompt Agent with `harness.type: microsoft_copilot_preview`, declared Web
  Search, and the Skill attached.

The sample leaves the harness-native tools enabled, matching the quickstart. The declared
`web_search` tool is also persisted on the Agent definition.

## Prerequisites

- Azure Developer CLI (`azd`) 1.36.0 or later.
- The Microsoft Foundry `azd` extension pack. The sample pins `azure.ai.agents` 1.0.0-beta.21
  and `azure.ai.projects` 1.0.0-beta.14.
- Python 3.10 or later for the automated smoke test.
- An Azure subscription with Copilot harness access and Global Standard quota for
  `gpt-5.4-mini` in the selected Foundry region. The sample requests 100 capacity units
  (100,000 tokens per minute).
- Contributor plus `Microsoft.Authorization/roleAssignments/write` permission, such as **User Access
  Administrator** or **Owner**, to create the isolated resources and initial project access.
- The **Foundry User** role on the deployed project for Agent inspection and invocation.

Web Search incurs additional usage charges and can send search data outside Azure compliance and
geographic boundaries. Review the applicable pricing, administrator controls, service terms, and
data-handling requirements before using it with sensitive prompts.

## Deploy

From this folder:

```bash
azd auth login
azd env new quickstart-web-research-dev \
  --subscription <subscription-id> \
  --location canadacentral
azd up --no-prompt
```

Canada Central is the sample default. Replace `canadacentral` when your subscription's harness
entitlement, model quota, or data-location requirements use another supported region.

Like the quickstart article's new-project path, this sample provisions an isolated project and
model so `azd up` and `azd down` cover the complete lifecycle.

## Try the quickstart scenario

Inspect the deployed definition:

```bash
azd ai agent show --output json
```

Start a new conversation with the same question used by the quickstart:

```bash
azd ai agent invoke --new-conversation --no-prompt \
  "What is the latest stable Python release? Use official Python sources. Return its version and release date, summarize two changes, and cite the release page and What's New page."
```

Verify that the answer uses current information, cites official `python.org` release and What's New
pages, includes a version and release date, summarizes two sourced changes, and reports uncertainty
instead of inventing missing facts.

## Run the automated smoke test

The dependency-free test runner verifies both configuration and behavior:

```bash
python3 scripts/smoke-test.py
```

It checks that the deployed Agent is active and persists the Microsoft Copilot harness, immutable Skill
version, and declared Web Search tool. It then starts a fresh conversation and requires a successful
current-information answer with labeled version/date/change fields, a Python version, and citations
to official release and What's New pages. It independently reads Python.org's current release list,
requires the Agent's version and release date to match, and rejects empty or duplicate change
summaries. These checks keep the scenario useful in CI without pinning a release that will become
stale.

The current Prompt Agent CLI returns final answer text rather than tool-call items, including with
`--output raw`. The automated test therefore verifies the persisted Web Search tool and observable
research result. For a manual release check, open the response trace in Foundry and confirm that it
contains a Web Search call.

The test uses the active `azd` environment, makes a direct read-only request to Python.org, and incurs
model and Web Search usage charges.

## Tear down

Remove the complete isolated environment after testing:

```bash
azd down --purge --force --no-prompt
```

## References

- [Web Search tool](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/web-search)
- [Agent Skills](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/skills)
