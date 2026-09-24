# Prompt Agent with Azure AI Search (RAG)

A prompt agent that answers with **RAG** grounded in an **Azure AI Search** index. [`azure.yaml`](./azure.yaml) declares the search tool and its `azure.ai.connection` sibling (Entra auth, no keys).

## Prerequisites

An existing Azure AI Search resource with an index:

```bash
azd env set AZURE_SEARCH_ENDPOINT https://<your-search>.search.windows.net
azd env set AZURE_SEARCH_INDEX_NAME <your-index-name>
```

## Deploy

```bash
azd up
azd ai agent invoke "What does the documentation say about the return policy?"
```

## GitHub Copilot Harness

Not supported. The GitHub Copilot harness does not accept Azure AI Search grounding.
