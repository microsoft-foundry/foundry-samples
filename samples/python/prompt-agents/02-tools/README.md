# Prompt Agent with Function Tools

A prompt agent that declares **client-executed function tools** (`get_weather`, `convert_currency`) in [`agent.yaml`](./agent.yaml). `type: function` declares the schema only — the model emits a tool call and your application executes it and returns the result.

## Deploy

```bash
azd up
azd ai agent invoke "What is the weather in Seattle in celsius?"
```

## Managed Harness Agent

Supported. To run this as a Managed Harness Agent, add one line to [`agent.yaml`](./agent.yaml):

```yaml
harness: github-copilot
```
