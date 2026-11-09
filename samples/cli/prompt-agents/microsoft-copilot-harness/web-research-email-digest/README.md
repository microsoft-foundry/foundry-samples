# Web Research Email Digest

An interactive Microsoft Copilot harness agent that researches current public information with
Microsoft Foundry Web Search and emails a concise, cited summary through Work IQ Mail.

The sample deploys:

- a Microsoft Foundry project and `gpt-5.4-mini` model deployment;
- Microsoft Foundry Web Search, backed by Grounding with Bing Search;
- a user-identity project connection for Work IQ User;
- a user-identity project connection for Work IQ Mail;
- a Prompt Agent that uses the Copilot harness;
- an approval-free Mail send tool suitable for unattended execution; and
- an enabled creator-identity Routine that emails its creator a daily Microsoft Foundry news digest
  at 8:00 AM Vancouver time.

The agent explicitly disables the Copilot harness's native toolset. Its web results therefore
come from the declared Foundry `web_search` tool rather than the harness-native web capability.

## Prerequisites

- Azure Developer CLI (`azd`) 1.36.0 or later.
- The Microsoft Foundry `azd` extension pack. The sample pins `azure.ai.agents` 1.0.0-beta.21
  and `azure.ai.projects` 1.0.0-beta.14.
- An Azure subscription where you can create Microsoft Foundry resources.
- The commercial requirements for the Work IQ connections. Connector-backed Microsoft 365 tools
  can require a Microsoft 365 Copilot license for each calling user.
- **Foundry Project Manager** on the project for creating the Work IQ connections, and **Foundry
  User** for the developer, Agent runtime identity, and user identities involved in OAuth.
- Microsoft 365 Mail and Work IQ access for each calling user.
- Tenant consent for the Work IQ User and Mail permissions required by your organization.
- The Microsoft Foundry `azd` extension pack. The sample pins `azure.ai.routines` 1.0.0-beta.10,
  which includes creator dispatch identity.

Work IQ calls run with the signed-in user's identity. Application-only authentication is not
supported for this scenario.

Work IQ and Foundry have distinct service and data-processing boundaries. Work IQ requests can be
processed outside the Azure compliance boundary, and Foundry can process or store returned content
according to the project configuration. Review the complete request path, service terms, regional
configuration, and data-handling requirements before using organizational data.

Web Search uses Grounding with Bing Search, incurs additional usage charges, and sends search data
outside Azure compliance and geographic boundaries. Review the linked terms before production use.

## Deploy

From this folder:

```bash
azd auth login
azd env new web-research-email-digest-dev --location canadacentral
azd up
```

Canada Central is the sample default. Replace `canadacentral` with another supported Foundry region
when needed. `azd up` prompts for the target subscription when it isn't already configured. It
provisions the Foundry resources and user-identity connections before deploying the Agent and
enabled Routine. Enabling does not immediately dispatch it; the first automatic dispatch occurs at
the next scheduled 8:00 AM in `America/Vancouver`. Review the schedule before running `azd up`.

The post-provision hook copies the generated Foundry endpoint to `AZURE_AI_PROJECT_ENDPOINT`, the
canonical variable used by the Routines extension. If you add the Routine to an existing environment
without rerunning provisioning, set it manually before deployment:

```bash
azd env set AZURE_AI_PROJECT_ENDPOINT \
  "$(azd env get-value FOUNDRY_PROJECT_ENDPOINT)"
azd deploy daily-foundry-news-digest
```

## Try it

Open **Web Research Email Digest** in the Microsoft Foundry agent playground and try:

```text
Look at the top stories about Microsoft Foundry from the past day and email a concise summary to
<recipient-email>.
```

The agent researches first, then sends the formatted HTML digest without an interactive tool
approval. Digests use linked headlines, source and publication metadata, short summaries, and a
clear "Why it matters" line instead of exposed raw URLs. The first Work IQ call can return consent
error `-32006` with a URL. Open the URL, complete the consent flow, and retry in a new conversation.

An exact address in the user prompt takes precedence. Otherwise, the agent calls Work IQ User's
`GetMyDetails` tool once and sends to the signed-in user's primary email address. It stops without
sending when the profile result does not contain one unambiguous address.

The pinned `azure.ai.agents` version includes the Copilot harness Conversation fix used by
`azd ai agent invoke` and the camelCase harness-toolset authoring contract.

The model deployment uses capacity 50 because a Work IQ turn can require several model/tool
continuations. The agent and Routine instructions request at most five Web Search calls per
digest, but this is not an enforced execution budget. Monitor actual tool usage and consider
increasing capacity if bounded requests still report `rate_limit_exceeded`.

## Daily routine

The enabled `daily-foundry-news-digest` Routine runs at 8:00 AM in `America/Vancouver`. It researches
up to five substantive Microsoft Foundry stories from the previous 24 hours, resolves the Routine
creator's primary email address through Work IQ User, and emails the final HTML digest to that
address.

The Routine uses `authorization.identity: creator`, so its unattended dispatches run as the
Microsoft Entra identity that first creates it. Creator identity is create-only: later deployments
preserve it, and changing the identity requires deleting and recreating the Routine.

The service also rejects changes to an existing trigger definition, including its cron
expression or time zone. To change those values, disable and delete the Routine, edit its
`triggers` in `azure.yaml`, and redeploy it while signed in as the intended creator.

If an existing Routine was created with released beta.9 or an earlier extension, enabling or
redeploying it doesn't add creator identity. Delete the existing Routine, then run
`azd deploy daily-foundry-news-digest` with this sample's beta.10 extension to recreate it from the
manifest.

To run it immediately and inspect recent runs:

```bash
azd ai routine dispatch daily-foundry-news-digest
azd ai routine run list daily-foundry-news-digest
```

The Portal **Test run** button performs the same asynchronous dispatch. A Routine run marked
**Completed** means the Routine handed the request to Agent Service; it does not prove that the
background agent response completed or that Mail was sent.

## Optional tracing and rate-limit diagnosis

Application Insights remains opt-in for this sample. Connect or create an Application Insights
resource from the Foundry project before a test run when you need detailed diagnostics. Traces can
contain prompts, search queries, tool arguments, email recipients, subjects, and bodies. Apply your
organization's data, access, retention, compliance, and geographic-boundary requirements before
enabling it. See the [tracing overview](https://aka.ms/tracing-overview) and
[disable-tracing guidance](https://aka.ms/disable-tracing).

After enabling tracing, allow several minutes for ingestion. In the connected Application Insights
resource, run this query from **Logs**:

```kusto
union requests, dependencies
| where timestamp > ago(1h)
| extend ErrorType = tostring(customDimensions["error.type"])
| where name == "invoke_agent"
    or name startswith "invoke_agent github-copilot-preview-"
    or name startswith "tools/call"
| project timestamp, itemType, name, success, resultCode, ErrorType, operation_Id
| order by timestamp asc
```

Interpret the result as follows:

- `ErrorType == "rate_limit_exceeded"` on an `invoke_agent github-copilot-preview-...` dependency
  means a model continuation was throttled. Check the number of prior search/tool calls before
  increasing deployment capacity.
- A successful `tools/call WorkIQMail___SendEmailWithAttachments` request proves that Mail accepted
  the send, even if a later model continuation makes the overall agent response fail.
- A successful root `invoke_agent` request proves only that Agent Service accepted the background
  response. The background tool calls can use different operation IDs, so search by name as above
  rather than inspecting only the root operation ID.
- The Portal trace lookup and Application Insights ingestion can lag by several minutes.

Disable the Routine whenever unattended delivery isn't intended:

```bash
azd ai routine disable daily-foundry-news-digest
```

## Limitations

The User MCP allowlists only `GetMyDetails`, and the Mail MCP allowlists only
`SendEmailWithAttachments`, both with tool approval disabled for unattended delivery. Mailbox reads,
drafts, replies, forwarding, moves, and deletes are not exposed. The Routine depends on its creator's
identity and existing Work IQ User and Mail consent.

The Bicep connection layer pins preview Work IQ catalog metadata. Verify those identifiers against a
released provisioning contract before publishing this sample outside an approved preview audience.

Routines beta.10 can return `value: null` from `run list` even when execution and email delivery
succeed. Inspect the completed Agent response and verify delivery rather than treating empty CLI
history as proof that no run occurred.

## Tear down

Disable and delete the data-plane Routine before removing the Azure resources:

```bash
azd ai routine disable daily-foundry-news-digest --no-prompt
azd ai routine delete daily-foundry-news-digest --force --no-prompt
azd down --purge --force --no-prompt
```

Teardown doesn't retract sent email or revoke tenant consent granted to Work IQ or Mail.

## References

- [Connect agents to Microsoft 365 with Work IQ](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/work-iq)
- [Web Search tool](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/web-search)
- [Mail MCP reference](https://learn.microsoft.com/microsoft-copilot-studio/mcp-mail-tools)
