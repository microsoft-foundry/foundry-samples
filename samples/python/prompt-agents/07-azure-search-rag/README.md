# Prompt Agent with Azure AI Search (RAG)

A prompt agent that answers with **RAG** grounded in an **Azure AI Search** index. The `azure_ai_search` tool and its `connections:` entry in [`agent.yaml`](./agent.yaml) wire the search connection (Entra auth, no keys).

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

## Managed Harness Agent

Supported. To run this as a Managed Harness Agent, add one line to [`agent.yaml`](./agent.yaml):

```yaml
harness: github-copilot
```
