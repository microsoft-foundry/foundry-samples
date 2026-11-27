# Prompt Agent with Files (File Search)

A prompt agent grounded in your own **documents** using the `files/` folder convention. On deploy, azd uploads [`files/`](./files/) to a vector store and wires an automatic `file_search` tool — no tool is declared in [`agent.yaml`](./agent.yaml).

## Deploy

```bash
azd up
azd ai agent invoke "What is the return window for opened items?"
```

## Managed Harness Agent

Not supported — this sample uses `file_search`, which the managed harness does not support. Do not add a `harness:` value. For document grounding on the harness, use [Azure AI Search](../07-azure-search-rag/) instead.
