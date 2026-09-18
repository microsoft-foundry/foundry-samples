# Microsoft Foundry — Hosted Agent Samples

Samples for building, deploying, and managing hosted agents on [Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents). Each sample is a starter template — fork it, change the system prompt and tools, deploy with `azd up`.

> **Every sample includes Application Insights and OpenTelemetry tracing out of the box.** You get production-ready logging, distributed traces, and metrics from the first sample you run.

### Quickstart

Pick the tool that matches your workflow — both deploy the same sample image to the same Foundry runtime, so you can switch between them at any point.

| Tool | Best for | Get started |
| --- | --- | --- |
| **Azure Developer CLI (`azd`)** | Command-line workflows, scripting, and CI/CD. Auto-provisions a Foundry project + model + ACR from a manifest. | [Deploy with `azd` →](#deploy-with-the-azure-developer-cli-azd) |
| **Foundry Toolkit VS Code Extension** | Integrated editor experience with an **Agent Inspector** for chatting with a running agent and a guided **Deploy Hosted Agent** flow. | [Deploy with the Foundry Toolkit VS Code Extension →](#deploy-with-the-foundry-toolkit-vscode-extension) |

#### Deploy with the Azure Developer CLI (`azd`)

> **Prerequisites:** Install Azure Developer CLI (`azd`) 1.27.1 or later with the Foundry AI extension. Manifests that set service environment variables use the `env:` map and require `azure.ai.agents` 1.0.0-beta.9 or later; their `requiredVersions` blocks enforce these minimums. See [Set up azd for hosted agents](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent?pivots=azd) if you haven't already.

```bash
mkdir my-agent && cd my-agent
azd ai agent init -m ../agent-framework/responses/01-basic/azure.yaml
azd up
```

You'll have a running agent in minutes.

#### Deploy with the Foundry Toolkit VS Code Extension

> **Prerequisites:** Install the Foundry Toolkit VS Code extension and sign in to Azure.

1. Clone this repo and open a sample folder under `samples/python/hosted-agents/` in VS Code.
2. Start the agent locally following the sample's run instructions (e.g. `azd ai agent run` or `python main.py`).
3. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Open Agent Inspector** to chat with the running agent.
4. When you're ready to deploy, run **Foundry Toolkit: Deploy Hosted Agent** to build the container image in ACR, register the agent version, and assign the required RBAC roles automatically.

See the [VS Code quickstart](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent?pivots=vscode) for the full walkthrough.

Read on to pick the right sample for your scenario, or jump to the [learning path](#learning-path) for a guided walkthrough.

---

## Two protocols: Responses and Invocations

Hosted agents support two protocols. Pick the one that matches your scenario.

| Scenario                                                          | Protocol                     | Why                                                                                                                               |
| ----------------------------------------------------------------- | ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Conversational chatbot or assistant                               | **Responses**                | The platform manages conversation history, streaming events, and session lifecycle — use any OpenAI-compatible SDK as the client. |
| Agent published to Teams or M365                                  | **Responses** + **Activity** | The Responses protocol powers the agent logic; the Activity protocol handles the Teams channel integration.                       |
| Multi-turn Q&A with RAG or tools                                  | **Responses**                | Built-in `conversation_id` threading and tool result handling.                                                                    |
| Background / async processing                                     | **Responses**                | `background: true` with platform-managed polling and cancellation — no custom code needed.                                        |
| Webhook receiver (GitHub, Stripe, Jira, etc.)                     | **Invocations**              | The external system sends its own payload format — you can't change it to match `/responses`.                                     |
| Non-conversational processing (classification, extraction, batch) | **Invocations**              | The input is structured data, not a chat message. Arbitrary JSON in, arbitrary JSON out.                                          |
| Custom streaming protocol (AG-UI, etc.)                           | **Invocations**              | AG-UI and other agent-UI protocols aren't OpenAI-compatible — you need raw SSE control.                                           |
| Async job with custom progress, polling, or non-OpenAI callers    | **Invocations**              | Custom progress reporting, intermediate results, and polling semantics beyond what Responses `background: true` provides.         |
| Protocol bridge (GitHub Copilot, proprietary systems)             | **Invocations**              | The caller has its own protocol that doesn't map to `/responses`.                                                                 |
| Inter-service orchestration (Durable Functions, Logic Apps)       | **Invocations**              | The caller sends structured task payloads, not chat messages.                                                                     |

> **Still not sure?** Start with **Responses**. You can always add an Invocations endpoint later — a hosted agent can support both protocols simultaneously by listing both in `azure.yaml`.

> **Other protocols:** Hosted agents can also expose the **Activity** protocol (for Teams and M365 integration) and the **A2A** protocol (for agent-to-agent delegation).

<details>
<summary><strong>Protocol comparison details</strong></summary>

|                               | **Responses**                                                                                                  | **Invocations**                                                                |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| **Best for**                  | Most agents — the platform manages conversation history, streaming lifecycle, and background polling           | Agents that need full HTTP control, custom payloads, or custom async workflows |
| **Payload**                   | OpenAI-compatible `/responses` contract                                                                        | Arbitrary JSON via `/invocations` — you define the schema                      |
| **Client SDK**                | Any OpenAI-compatible SDK (Python, JS, C#) works out of the box                                                | Custom client — you define the contract                                        |
| **Session history**           | Framework-managed via `conversation_id`                                                                        | You manage sessions (in-memory, Cosmos DB, etc.)                               |
| **Streaming**                 | Framework-managed `ResponseEventStream` with lifecycle events (`created`, `in_progress`, `delta`, `completed`) | Raw SSE — you format and write events directly                                 |
| **Background / long-running** | Built-in (`background: true` + platform-managed polling)                                                       | Manual task tracking and custom polling endpoints                              |
| **Server SDK**                | `azure-ai-agentserver-responses`                                                                               | `azure-ai-agentserver-invocations`                                             |
| **azure.yaml**                | `protocol: responses`, `version: v0.1.0`                                                                       | `protocol: invocations`, `version: v0.0.1`                                     |

</details>

---

## Pick your framework

Hosted agents run any code you can put in a container. These samples cover three frameworks — pick the one that matches where you are.

|                         | **Agent Framework**                                                                | **LangGraph**                                                         | **Bring Your Own**                                                                                                          |
| ----------------------- | ---------------------------------------------------------------------------------- | --------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| **Best for**            | Starting fresh on Foundry — also supports AutoGen and Semantic Kernel              | Already using LangChain / LangGraph                                   | Already built with CrewAI or your own stack                                                                                 |
| **SDK**                 | `agent-framework-foundry-hosting` (includes core, openai, foundry, orchestrations) | `langchain-azure-ai[hosting]` (`ResponsesHostServer` / `InvocationsHostServer`) | `azure-ai-agentserver-responses` / `azure-ai-agentserver-invocations`, or `azure-ai-agentserver-core` for fully custom HTTP |
| **Foundry integration** | Native — sessions, tools, memory, streaming all built in                           | Native via `langchain_azure_ai.agents.hosting` — sessions, streaming, and tool-call surfacing built in for LangGraph agents (`create_agent`) and custom `StateGraph`s | Core adapter hosts the web server and exposes `/invocations` and `/responses` endpoints; you supply the agent logic         |
| **Protocols**           | Responses and Invocations                                                          | Responses and Invocations                                             | Responses and Invocations                                                                                                   |
| **Language support**    | Python and C#                                                                      | Python only                                                           | Any language (Python and C# samples provided)                                                                               |
| **Start here**          | [Basic Agent →](agent-framework/responses/01-basic/)                               | [LangGraph Chat →](langgraph/responses/01-langgraph-chat/)            | [Hello World →](bring-your-own/responses/hello-world/)                                                                      |

> **Which should I choose?** If you're building a new agent — or already using AutoGen or Semantic Kernel — start with **Agent Framework**. It has the tightest Foundry integration, supports those orchestrators natively, and has the most samples to learn from. If you already have LangGraph code, use the **LangGraph** hosting integration (`langchain_azure_ai.agents.hosting`) to bring it to Foundry. If you have an existing agent in another framework (e.g., CrewAI), **Bring Your Own** shows how to containerize and deploy it unchanged.

---

## Agent Framework samples

The recommended path for building hosted agents. Agent Framework gives you native session management, built-in tool wiring, streaming, and the full Foundry feature set.

Samples are split by protocol. Start with **Responses** (the common path) — then explore **Invocations** when you need full HTTP control or long-running workflows.

### Responses protocol

The platform manages conversation history, streaming lifecycle, and background execution. This is the default for most agents.

#### Learning path

> **Recommended: reach for a [Foundry Toolbox](./agent-framework/responses/04-foundry-toolbox/) when you add tools.** A toolbox packages web search, code interpreter, MCP servers, OpenAPI tools, and more behind a single managed MCP endpoint, with centralized auth and versioning — so you define tools once and share them across agents instead of wiring each tool into every agent. The local-tools sample below is still fully supported; use it for self-contained logic you own.

**New to hosted agents?** Start here and work through in order:

1. **[Basic agent & Multi-Turn Sessions](./agent-framework/responses/01-basic/)** — Deploy your first agent, have a conversation with it.
2. **[Tools](./agent-framework/responses/02-tools/)** — Add local tools to your agent.
3. **[Foundry Toolbox](./agent-framework/responses/04-foundry-toolbox/)** — Wire your agent to a Foundry Toolbox for managed tool access.
4. **[Workflows](./agent-framework/responses/05-workflows/)** — Compose multiple agents into sequential pipelines.
5. **[Files](./agent-framework/responses/06-files/)** — Agent capable of manipulating files uploaded to the session.
6. **[Skills](./agent-framework/responses/07-skills/)** — Add native file-based skills to your agent and generate a colorful PDF travel guide.
7. **[Observability](./agent-framework/responses/08-observability/)** — Add logging, metrics, and distributed tracing to your agent and visualize them in Foundry.
8. **[Declarative Workflows](./agent-framework/responses/09-declarative-customer-support/)** — A multi-turn customer-support triage workflow defined entirely in YAML and hosted as an agent, demonstrating declarative workflow authoring with `InvokeAzureAgent` calls to specialist Foundry-hosted agents and conversation-aware routing.
9. **[Downstream Azure services](./agent-framework/responses/09-downstream-azure/)** — Call Azure Blob Storage and Service Bus from the agent using its per-agent Microsoft Entra identity (no connection strings).
10. **[A2A Delegation](./agent-framework/a2a/01-delegation/)** — Two-agent walkthrough: a hosted Responses **caller** delegates to a hosted Responses **executor** that is exposed as an A2A endpoint via Foundry's incoming A2A feature, wired together through a Foundry Toolbox `a2a_preview` tool over a `RemoteA2A` connection.
11. **[Content safety guardrail](./agent-framework/responses/16-content-safety-guardrail/)** — Attach a Responsible AI content safety guardrail to a hosted agent so the platform screens prompts and responses against your safety policy.
12. **[Harness Research](./agent-framework/responses/19-harness-research/)** — Build a long-running research assistant with plans, todos, web search, compaction, and autonomous execute-mode loops.
13. **[Harness Data Processing](./agent-framework/responses/20-harness-data-processing/)** — Analyze bundled data with file tools and complete protected writes through structured approvals.
14. **[Harness scaling capabilities](./agent-framework/responses/21-harness-scaling-capabilities/)** — Combine file skills, a confined shell, CodeAct, and concurrent background research in one multi-turn personal-finance harness agent.

### Invocations protocol

Full control over the HTTP request/response cycle. You define the payload schema, manage session state, and implement polling for long-running operations. Use this when you need an arbitrary payload format or async workflows that don't fit the OpenAI `/responses` contract.

> **Every capability works with both protocols.** Tools, RAG, memory, evaluations, Teams publishing, multi-agent — all of these work with Invocations. The Invocations samples below focus on the protocol mechanics (how you handle requests, streaming, sessions, and long-running tasks). To add a capability like knowledge grounding or tools, learn the Invocations pattern from these samples, then adapt the relevant Responses sample — the capability code is the same, only the HTTP handler differs.

| Sample                                                                 | What it shows                                                                           |
| ---------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| **[Basic Invocations Agent](./agent-framework/invocations/01-basic/)** | Minimal invocations agent — shows the invocations handler pattern with Agent Framework. |

---

## LangGraph samples

Bring your existing [LangGraph](https://langchain-ai.github.io/langgraph/) graphs to Foundry. These samples use [`langchain_azure_ai.agents.hosting`](https://github.com/langchain-ai/langchain-azure/tree/main/libs/azure-ai/langchain_azure_ai/agents/hosting) (`ResponsesHostServer` / `InvocationsHostServer`) to expose LangGraph agents (`create_agent`) and custom `StateGraph`s over the hosted agent protocols, with native Foundry session, streaming, and tool wiring.

See [`langgraph/README.md`](langgraph/) for the full list and the local-run guide.

### Responses protocol

| Sample                                                                  | What it shows                                                                                                                          |
| ----------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| **[Chat](langgraph/responses/01-langgraph-chat/)**                      | Minimal LangGraph agent with two local tools (`get_current_time`, `calculator`); multi-turn via `previous_response_id`.                |
| **[LangGraph Toolbox](langgraph/responses/02-langgraph-toolbox/)**      | LangGraph agent wired to a Foundry Toolbox (`web_search` + connection-backed GitHub Copilot MCP) via `AzureAIProjectToolbox`.          |
| **[Workflows](langgraph/responses/05-workflows/)**                      | Custom `StateGraph` chaining three specialized LLM nodes — slogan writer, legal reviewer, formatter — each seeing only the prior agent's output. |
| **[Files](langgraph/responses/06-files/)**                              | LangGraph agent with local filesystem tools and a Foundry-Toolbox `code_interpreter` for session-uploaded files.                       |
| **[Human-in-the-Loop](langgraph/responses/07-human-in-the-loop/)**      | `StateGraph` that drafts a proposal and pauses for approval via `langgraph.types.interrupt`, serialized as `mcp_approval_request` + `function_call`. |
| **[Observability](langgraph/responses/08-observability/)**              | GenAI OpenTelemetry tracing enabled with `enable_auto_tracing()` — spans, metrics, and logs flow to Application Insights.              |

### Invocations protocol

| Sample                                                | What it shows                                                                                                                              |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| **[Chat](langgraph/invocations/01-langgraph-chat/)**  | Minimal LangGraph agent with local tools; session state via `agent_session_id` (URL param / `x-agent-session-id` header) backed by a LangGraph checkpointer. |

### Agent-to-Agent (A2A)

| Sample                              | What it shows                                                                                                                                |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| **[A2A Delegation](langgraph/a2a/)** | Two LangGraph Responses agents — a `concierge` that delegates math questions over A2A to a `math-expert` that publishes an incoming A2A endpoint + agent card, wired through a `RemoteA2A` connection and an `a2a_preview` Toolbox loaded over MCP. |

---

## Bring Your Own Framework samples

Already built an agent with CrewAI or your own code? The protocol SDKs (`azure-ai-agentserver-responses` / `azure-ai-agentserver-invocations`) give you the hosted agent HTTP contract — they host the web server, expose the right endpoint, and handle request parsing — so you just plug in your agent logic. This is the recommended path for BYO to ensure your agent stays aligned with the platform contract as new endpoints are added. For lower-level control, the **Core adapter** (`azure-ai-agentserver-core`) gives you managed hosting, OpenTelemetry tracing, and health endpoints, but you handle the protocol details yourself.

> **Note:** If you're using AutoGen or Semantic Kernel, you don't need BYO — Agent Framework supports them natively. See the [Agent Framework samples](#agent-framework-samples) instead.

### Responses protocol

| Sample                                                             | What it shows                                                                                                                |
| ------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------- |
| **[Hello World](bring-your-own/responses/hello-world/)**           | Minimal agent — calls a Foundry model via the Responses API and returns the reply. The simplest possible BYO starting point. |
| **[uv + pyproject](bring-your-own/responses/uv-pyproject/)**       | Existing-code initialization and remote code deployment with `pyproject.toml`, `uv.lock`, and system TLS certificates.      |
| **[LangGraph Chat](bring-your-own/responses/langgraph-chat/)**     | LangGraph conversational agent hosted on Foundry with multi-turn history via the Responses protocol.                         |
| **[Notetaking Agent](bring-your-own/responses/notetaking-agent/)** | Agent that takes and retrieves notes using a custom tool.                                                                    |
| **[Session Multiplexing](bring-your-own/responses/session-multiplexing/)** | Demonstrates multiple callers sharing one `agent_session_id` while `previous_response_id` history stays scoped by platform user context. |
| **[Toolbox](bring-your-own/responses/toolbox/)**                   | BYO agent wired to a Foundry Toolbox MCP endpoint for tool access.                                                           |
| **[Background Agent](bring-your-own/responses/background-agent/)** | Long-running background processing with async execution.                                                                     |
| **[Env Vars Agent](bring-your-own/responses/env-vars-agent/)**     | Reads env vars injected by Foundry's connection-templated secret resolver. Covers ApiKey + CustomKeys connections and a kind-aware safety policy (whole value for `metadata`/`target`, fingerprint only for `credentials`). |
| **[Browser Automation](bring-your-own/responses/browser-automation/)** | Browser automation agent using Toolbox MCP for session lifecycle and playwright-cli for browser commands. Supports multi-session, form filling, and web scraping. |

### Invocations protocol

| Sample                                                                 | What it shows                                                                                               |
| ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| **[Hello World](bring-your-own/invocations/hello-world/)**             | Minimal agent — arbitrary JSON in, streaming SSE out. The simplest possible BYO invocations starting point. |
| **[LangGraph Chat](bring-your-own/invocations/langgraph-chat/)**       | LangGraph conversational agent over the Invocations protocol with client-managed sessions.                  |
| **[Notetaking Agent](bring-your-own/invocations/notetaking-agent/)**   | Note-taking agent with the Invocations protocol.                                                            |
| **[Toolbox](bring-your-own/invocations/toolbox/)**                     | BYO invocations agent wired to a Foundry Toolbox MCP endpoint.                                              |
| **[AG-UI](bring-your-own/invocations/ag-ui/)**                         | Agent using the AG-UI streaming protocol via the Invocations endpoint.                                      |
| **[GitHub Copilot](bring-your-own/invocations/github-copilot/)**       | Agent that integrates with GitHub Copilot as the AI backbone.                                               |
| **[Human-in-the-Loop](bring-your-own/invocations/human-in-the-loop/)** | Long-running agent that pauses for human approval before continuing.                                        |
| **[Event Grid Trigger](bring-your-own/invocations/event-grid-trigger/)** | Event-driven agent: Azure Storage → Event Grid → hosted agent (direct delivery, authenticated by the system topic's system-assigned managed identity); agent summarizes the new blob and writes the summary to a sibling Storage container. |

## Python dependencies

New Python Hosted Agent runtimes use `pyproject.toml` with `uv.lock` by default. A fully resolved `requirements.txt` remains accepted as a backward-compatible fallback. The selected artifact must capture the complete dependency graph; uv-native validation and deployment use a pinned uv version with `uv sync --frozen`.

See the [Python Hosted Agent dependency policy](DEPENDENCY_POLICY.md) for pinning rules, authoring-tool examples, validation commands, ratchet behavior, and exceptions.

## Deploy any sample

Every sample deploys the same way and supports two equivalent paths. Pick the one that matches your workflow.

| | **Azure Developer CLI (`azd`)** | **Foundry Toolkit VS Code Extension** |
| --- | --- | --- |
| **Install** | [Install `azd`](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd) + `azd ext install microsoft.foundry` | Install the Foundry Toolkit VS Code extension |
| **Open the sample** | `azd ai agent init -m <azure.yaml>` — adopts the sample's `azure.yaml` and sets up env config | Clone the repo and open the sample folder in VS Code |
| **Run locally** | `azd ai agent run` (or `python main.py`) | Same as `azd`/manual, then open **Foundry Toolkit: Open Agent Inspector** to chat with the running agent |
| **Provision Azure resources** | `azd provision` (creates Foundry project, model deployment, ACR, App Insights if needed) | Guided dialog in **Foundry Toolkit: Deploy Hosted Agent** — reuses existing project or provisions a new one |
| **Deploy to Foundry** | `azd deploy` (or `azd up` to provision + deploy) | **Foundry Toolkit: Deploy Hosted Agent** — builds image in ACR, registers the agent version, assigns RBAC |
| **Tear down** | `azd down` | Delete the agent in the Foundry portal or with `az` CLI |

### Using `azd`

```bash
mkdir my-agent && cd my-agent

# Scaffold from the sample manifest — azd generates all the deployment files
azd ai agent init -m ../agent-framework/responses/01-basic/azure.yaml

# Build, push, and deploy
azd up

# Clean up when done
azd down
```

### Using the Foundry Toolkit VS Code Extension

The [Foundry Toolkit VS Code extension](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent?view=foundry&pivots=vscode) has a built-in sample gallery. You can open any sample directly from the extension without cloning this repository, it scaffolds the project into a new workspace, generates `agent.yaml`, `.env`, and `.vscode/tasks.json` + `launch.json` automatically, and configures a one-click **F5** debug experience.

Or, if you've already cloned this repository:

1. Open a sample folder under `samples/python/hosted-agents/` in VS Code.
2. Start the agent locally with `azd ai agent run` or `python main.py` (see the sample README for details). The agent runs on `http://localhost:8088/`.
3. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Open Agent Inspector** to chat with the running agent.
4. When you're ready to deploy, run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a tab-based wizard and reads `agent.yaml` to auto-populate what it can:
   - If prompted, complete **Foundry Project Setup** to pick the subscription and Foundry project (or create a new one) to deploy to.
   - On the **Basics** tab, choose a **Deployment Method** (**Code** ZIP or **Container** image), pick a Code packaging option (**Remote** / **Local**) or a Container registry option (default ACR, your own ACR, or a prebuilt ACR image), and confirm the **Hosted Agent Name**.
   - On the **Review + Deploy** tab, confirm the auto-detected runtime details (language, entry point, or Dockerfile), pick a **CPU and Memory** size, and click **Deploy**.

   The extension builds the container image in ACR (or uploads the ZIP), creates the agent version, and assigns required RBAC roles automatically.

### Other ways to invoke your agent

| Method                                                                                                                                | When to use                               |
| ------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------- |
| `azd ai agent invoke`                                                                                                                 | Quick CLI test after deploy               |
| Foundry Toolkit VS Code extension | One-click invoke from the editor          |
| `curl`                                                                                                                                | Each sample README includes curl examples |

## Voice Live integration

For **Responses** protocol agents, once the agent is deployed to Microsoft Foundry, you can interact with it using real-time voice through the [Azure VoiceLive SDK](https://pypi.org/project/azure-ai-voicelive/). The shared Voice Live client sample, [voicelive_client.py](bring-your-own/voicelive/client/voicelive_client.py), demonstrates how to connect to your deployed agent and have a voice conversation.

```bash
python voicelive_client.py \
  --endpoint "https://<your-foundry-resource>.services.ai.azure.com" \
  --agent-name "<your-agent-name>" \
  --project-name "<your-foundry-project-name>"
```

The client authenticates using `DefaultAzureCredential` — make sure you are logged in (`az login`).

For **Invocations** protocol agents, to make the agent work with Voice Live, the agent needs:

- The agent can process voice live transcription input: `{"type": "input_audio.transcription", "input": "example voice input"}`
- The agent should output the text to be read as the following SSE, Voice Live will generate audio for the the `delta` text in the `output_audio_transcription.delta` event:
  ```
  data: {"type": "output_audio_transcription.delta", "delta": "The weather "}
  data: {"type": "output_audio_transcription.delta", "delta": "in Seattle "}
  data: {"type": "output_audio_transcription.delta", "delta": "is 52°F "}
  data: {"type": "output_audio_transcription.delta", "delta": "and partly cloudy."}
  data: {"type": "output_audio_transcription.done", "text": "The weather in Seattle is 52°F and partly cloudy."}
  data: {"type": "done"}
  ```
- The agent manifest must declare `voiceLiveCompatible: "true"` in the metadata section to indicate compatibility with Voice Live.

Here is a hosted agent sample with Invocations protocol that is compatible with Voice Live: [hello-world-invocations-voicelive](bring-your-own/voicelive/hello-world-invocations-voicelive/).

## Prerequisites

- **Azure subscription** with access to Microsoft Foundry
- **One of the following deploy tools:**
  - **Azure Developer CLI (`azd`) 1.27.1 or later** — [install](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent?pivots=azd), or
  - **Foundry Toolkit VS Code Extension** — [install](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent?pivots=vscode)
- **Python 3.12+**

That's it. Both `azd ai agent init` and the Foundry Toolkit VS Code extension will create a Foundry project and deploy a model for you if you don't already have one. Container images are built remotely using ACR Tasks by default — **Docker is not required** unless you want to build locally.

## Resources

- [Microsoft Foundry documentation](https://learn.microsoft.com/en-us/azure/foundry/what-is-foundry?view=foundry)
- [Hosted agents overview](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents?view=foundry)
- [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent)
- **Responses protocol:** [Python SDK (`azure-ai-agentserver-responses`)](https://pypi.org/project/azure-ai-agentserver-responses/) · [C# SDK (`Azure.AI.AgentServer.Responses`)](https://www.nuget.org/packages/Azure.AI.AgentServer.Responses)
- **Invocations protocol:** [Python SDK (`azure-ai-agentserver-invocations`)](https://pypi.org/project/azure-ai-agentserver-invocations/) · [C# SDK (`Azure.AI.AgentServer.Invocations`)](https://www.nuget.org/packages/Azure.AI.AgentServer.Invocations)
- **Core adapter (BYO):** [Python SDK (`azure-ai-agentserver-core`)](https://pypi.org/project/azure-ai-agentserver-core/) · [C# SDK (`Azure.AI.AgentServer.Core`)](https://www.nuget.org/packages/Azure.AI.AgentServer.Core)
- [Azure Developer CLI (azd)](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd)

## Contributing

This project welcomes contributions and suggestions.

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft trademarks or logos is subject to and must follow [Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general). Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship. Any use of third-party trademarks or logos are subject to those third-party's policies.
