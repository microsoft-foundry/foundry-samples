# Microsoft Copilot harness samples for Microsoft Foundry

Runnable examples of Prompt Agents that use the Microsoft Copilot harness in Microsoft Foundry. Each
sample is an independent Azure Developer CLI (`azd`) project with its own infrastructure,
instructions, client or test flow, and cleanup guidance.

## Samples

| Sample | Demonstrates | Additional resources |
| --- | --- | --- |
| [Quickstart: Web Research](quickstart-web-research/) | The completed web-research quickstart: declared Web Search, a reusable official-source Skill, and an automated smoke test | Foundry account, project, and model deployment |
| [Web Research Email Digest](web-research-email-digest/) | Foundry Web Search, Work IQ User recipient lookup, Work IQ Mail delivery, and a creator-identity daily Routine | Work IQ User and Mail project connections |
| [Browser Automation Blog Research](browser-automation-blog-research/) | Managed browser sessions through a Browser Automation Toolbox | Playwright workspace, project connections, Toolbox, and RBAC |
| [AdventureWorks SQL Analyst](adventureworks-sql-analyst/) | Read-only relational analysis through managed connector MCP tools and a progressive-disclosure Skill | AdventureWorksLT Azure SQL database and Connector Namespace |
| [CSV Chart Analyst](csv-chart-analyst/) | Request-scoped CSV staging, native shell analysis, PNG generation, and Foundry Files upload/download without Code Interpreter | Agent-identity **Foundry User** assignment at project scope |

## Before you begin

Common requirements:

- Azure Developer CLI (`azd`) 1.36.0 or later and Azure CLI.
- The Microsoft Foundry `azd` extension pack.
- An Azure subscription with access to the Copilot harness and quota for the sample's model.
- Permission to create the resources and role assignments listed by the selected sample.

Read the sample README before deployment. Some samples also require Microsoft 365 consent,
additional command-line tools, or service availability in a specific region.

## Run a sample

From the selected sample folder:

```bash
azd auth login
azd env new <environment-name> --location canadacentral
azd up
```

The samples default to Canada Central for Microsoft Foundry. Replace `canadacentral` when your
subscription's harness entitlement, model quota, or data-location requirements use another supported
region. Regional dependencies that aren't available in Canada Central have separate defaults in the
sample and can also be overridden. Use a separate environment for each sample. Follow its README to
exercise the deployed agent and verify the expected tool calls or generated output.

When you no longer need an isolated sample environment, follow that sample's **Tear down** or
**Clean up** section. Some samples have data-plane resources or side effects that require additional
steps before Azure resource deletion. In particular, the Web Research Email Digest requires you to
disable and delete its Routine before running `azd down`.

For samples whose README doesn't specify additional steps, remove the Azure resources from that
sample folder:

```bash
azd down --purge --force
```

These examples use preview services and APIs. Review generated resources, permissions, data flow,
retention, tool behavior, and costs before adapting them for production use.
