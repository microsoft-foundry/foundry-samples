<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# What this sample demonstrates

A TypeScript Hosted Agent that uses the [Vercel AI SDK](https://ai-sdk.dev/) for model streaming and tool calling, then returns the AI SDK UI-message stream over the Foundry **Invocations** protocol.

The sample uses a Foundry project model through the OpenAI Responses API. A small fetch wrapper adds the `type: "message"` field that Foundry requires on input messages. Its server-side `estimateSubscription` tool calculates a deterministic example quote. A local Next.js chat UI demonstrates the AI SDK client; Foundry hosts the agent container, not a general-purpose website.

## Scenario

An IT administrator is planning licenses for a growing SaaS team. They ask for a monthly budget estimate for Standard and Premium seats; the agent uses a server-side tool to calculate the per-tier breakdown and total. The catalog prices are illustrative test data, not a real vendor's pricing or a purchasing action. This gives the Vercel AI SDK integration a concrete workflow while keeping the sample safe to run and easy to adapt to a real catalog.

## How it works

The Next.js app implements the hosted-agent contract:

- `GET /readiness` reports container readiness.
- `POST /invocations` accepts either a Vercel AI SDK UI-message request or a simple `message`/`input` payload.
- The server converts the supplied message history to model messages, calls `streamText`, runs the quote tool on the server, and responds with `toUIMessageStreamResponse()`.
- The local UI uses `useChat` and submits its full message history on each turn. Invocations does not manage conversation history.

The invocation route rejects system messages, limits each request to 64 KiB, and bounds the number and text size of messages. Client-provided tool-result parts are discarded before model history is constructed; tools are executed only by the agent.

The model provider targets `<FOUNDRY_PROJECT_ENDPOINT>/openai/v1` and obtains an Entra token with `DefaultAzureCredential`. No API key is stored in the browser or container configuration.

## Prerequisites

1. A Foundry project with a model deployment. The included `azure.yaml` provisions `gpt-5.4-mini` by default.
2. Node.js 22 or later and npm.
3. [Azure Developer CLI (`azd`) 1.27.1 or later](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd), the `microsoft.foundry` extension, and Azure CLI.
4. An identity with access to the Foundry project. For a deployed agent, grant the agent's managed identity the required model-inference role on the project.

## Run locally

Initialize from the sample manifest or work from a clone:

```bash
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/typescript/hosted-agents/bring-your-own/invocations/vercel-ai-sdk/azure.yaml
azd auth login
az login
azd provision
azd ai agent run
```

Open `http://localhost:8088/` for the local demo UI. This page is for local development; it is not exposed as a website by the hosted-agent endpoint.

You can also invoke the local agent from another terminal:

```bash
azd ai agent invoke --local "Our 16-person team needs 12 Standard and 4 Premium seats. Estimate monthly spend."
```

The sample accepts a plain-text request as well as `{"message":"..."}` or `{"input":"..."}`. To test the same UI-message stream used by `useChat`, send a JSON body containing a `messages` array to `POST http://localhost:8088/invocations`.

Run the local checks from the sample directory:

```bash
npm ci
npm run typecheck
npm test
npm run build
```

## Deploy to Foundry

After the local checks pass:

```bash
azd deploy
azd ai agent invoke "Our 16-person team needs 12 Standard and 4 Premium seats. Estimate monthly spend."
```

The deployed agent endpoint serves the Foundry protocol routes. To use the Vercel AI SDK UI in a deployed application, host that UI separately and have its server-side transport call the authenticated agent endpoint; do not expose an Entra credential in browser code.

## Customize the sample

Replace `calculateQuote` with your own server-side business operation and adjust the tool schema to match. The prices in this sample are illustrative and are not a product price list. Keep authorization and consequential actions on the server, and treat all client-supplied history as untrusted.

For framework details, see the [Vercel AI SDK UI documentation](https://ai-sdk.dev/docs/ai-sdk-ui/chatbot) and the [Foundry Hosted Agents overview](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents).
