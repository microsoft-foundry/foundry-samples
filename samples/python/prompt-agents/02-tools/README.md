# Prompt Agent with Function Tools

A prompt agent that declares **client-executed function tools** (`get_weather`, `convert_currency`) in [`azure.yaml`](./azure.yaml). `type: function` declares the schema only; the model emits a tool call and your application executes it and returns the result.

## Deploy

```bash
azd up
azd ai agent invoke "What is the weather in Seattle in celsius?"
```

## GitHub Copilot Harness

Supported with non-strict function tools. To use the GitHub Copilot harness, add this block to the agent service in [`azure.yaml`](./azure.yaml):

```yaml
harness:
  type: github_copilot_preview
```

Also set `strict: false` on each function tool. Strict function mode is not supported by the GitHub Copilot harness.
