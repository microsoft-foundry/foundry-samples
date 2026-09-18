# Python Autopilot agents

These samples deploy Python agents directly to Microsoft Foundry Agent Service
and publish their hosted-agent identity blueprints as Microsoft 365 Autopilots.
Autopilots work as persistent, named members of an organization and can
participate in Microsoft Teams conversations.

## Choose a sample

| Sample | What you will build |
| --- | --- |
| [Hello World](hello-world/README.md) | A minimal agent that responds to Teams direct messages, group chats, and channel messages that mention it. Interactively create or reuse its Foundry project and model deployment. |

Start with the [Hello World walkthrough](hello-world/README.md#step-1-install-the-prerequisites).
It contains the complete sequence: prerequisites, permissions, sign-in,
interactive provisioning, deployment, Microsoft 365 publication, administrator approval,
and your first Teams conversation.

## Shared utilities

The [session-stop script](scripts/stop-agent-sessions.ps1) is shared by the
samples. Each sample documents the exact command to run after updating its code.

## References

- [What is an Autopilot in Microsoft Foundry?](https://learn.microsoft.com/azure/foundry/agents/concepts/autopilot-overview)
- [Deploy a hosted agent](https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent)
- [Publish an Autopilot in Microsoft Agent 365](https://learn.microsoft.com/azure/foundry/agents/how-to/agent-365)
- [Hosted agent permissions](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-permissions)
