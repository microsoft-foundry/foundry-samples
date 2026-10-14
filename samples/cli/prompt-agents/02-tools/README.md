# Prompt Agent with Function Tools

A prompt agent that declares **client-executed function tools** (`get_weather`, `convert_currency`) in [`azure.yaml`](./azure.yaml). `type: function` declares the schema only; the model emits a tool call and your application executes it and returns the result.

## Deploy

```bash
azd up
azd ai agent invoke "What is the weather in Seattle in celsius?"
```
