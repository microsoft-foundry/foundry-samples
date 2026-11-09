# Prompt Agent with Azure AI Search (RAG)

A prompt agent that answers with **RAG** grounded in an **Azure AI Search** index. [`azure.yaml`](./azure.yaml) declares the search tool and its `azure.ai.connection` sibling (Entra auth, no keys).

## Prerequisites

Requires azd 1.36.0 or later. The manifest pins Agents beta.21, Projects beta.14, and Connections
beta.10.

An existing Azure AI Search resource with an index:

```bash
azd env set AZURE_SEARCH_ENDPOINT https://<your-search>.search.windows.net
azd env set AZURE_SEARCH_INDEX_NAME <your-index-name>
```

The calling identity (`authType: AAD`) must have **Search Index Data Reader** and **Search Service Contributor** roles on the Azure AI Search resource. See the [Azure AI Search tool setup](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/ai-search) for details. This sample does not create the Search service, seed the index, or assign its Search roles.

The manifest sets `query_type: simple` on the index entry so keyword-only indexes work out of the box. Change `query_type` (for example, to `semantic`, `vector`, `vector_simple_hybrid`, or `vector_semantic_hybrid`) when your index is configured with a semantic configuration or integrated vectorizer.

## Deploy

```bash
azd up
azd ai agent invoke "What does the documentation say about the return policy?"
```

## Microsoft Copilot harness

The Microsoft Copilot harness accepts the `azure_ai_search` tool. To use it, add `harness.type: microsoft_copilot_preview` to a separately named agent service in [`azure.yaml`](./azure.yaml) and omit `toolChoice` (an explicit `tool_choice` is not supported on that harness).
