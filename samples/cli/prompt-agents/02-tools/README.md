# Prompt Agent with Function Tools

A prompt agent that declares **client-executed function tools** (`get_weather`, `convert_currency`) in [`azure.yaml`](./azure.yaml). `type: function` declares the schema only; the model emits a tool call and your application executes it and returns the result.

Requires azd 1.36.0 or later. The manifest pins Agents beta.21 and Projects beta.14.

## Deploy

```bash
azd up
azd ai agent invoke "What is the weather in Seattle in celsius?"
```

This sample does not include the application-side function implementations. An invocation
emits a `function_call` item without a text answer; the CLI does not fetch live weather, execute
currency conversion, or submit `function_call_output`. Pass `--new-conversation` when running
consecutive CLI invocations, or implement the function-result round trip in your client.

## Microsoft Copilot harness

To use non-strict function tools with the Microsoft Copilot harness, add this block to a separately named agent service in [`azure.yaml`](./azure.yaml):

```yaml
harness:
  type: microsoft_copilot_preview
```

Also set `strict: false` on each function tool (`strict: true` is not supported by the Copilot harness)
and remove `toolChoice: auto` (the Copilot harness rejects an explicit `tool_choice` setting).
