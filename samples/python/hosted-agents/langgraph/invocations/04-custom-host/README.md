# What this sample demonstrates

A location-aware LangGraph chat agent hosted over the **Invocations protocol**. It demonstrates when and how to use custom InvocationsHostServer implementations for custom input and graph states.
The agent uses calculator, current-time, and fake-weather tools.

`LocationAwareInvocationsHostServer` adds support for:

- an `x-client-user-locale` header that controls language and temperature units; and
- a message list that can contain a custom location message.

Normal text messages, streaming, and `agent_session_id` conversations remain
supported.

## Custom request

The first turn can send a user message alongside a location message:

```json
{
  "message": [
    {
      "type": "message",
      "role": "developer",
      "content": "The user shared a location from the client.",
      "message_type": "location",
      "location": {
        "label": "Seattle",
        "latitude": 47.6062,
        "longitude": -122.3321
      }
    },
    {
      "type": "message",
      "role": "user",
      "content": [
        {
          "type": "input_text",
          "text": "What weather should I expect here?"
        }
      ]
    }
  ]
}
```

`message_type` and `location` are application-defined message extensions.
`LocationAwareInvocationsHostServer.parse_request` extracts the current text
and location. It also reads `x-client-user-locale`; for example, `en-US` selects
Fahrenheit while `fr-FR` selects Celsius.

```text
Turn 1: location message + "What weather should I expect here?"
Turn 2: "Will I need an umbrella tomorrow?" + agent_session_id
```

## How the customization works

`LocationAwareInvocationsHostServer.parse_request` reads `x-client-user-locale` and
extracts the custom location message. Standard graph execution and output
handling remain delegated to `InvocationsHostServer`. The graph receives:

```python
class AssistantState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    locale: str
    location: Location
```

## Run with Azure Developer CLI

1. Install and authenticate the required tools:

   ```bash
   azd ext install microsoft.foundry
   azd auth login
   ```

2. Initialize from this sample:

   ```bash
   mkdir hosted-langgraph-custom-host && cd hosted-langgraph-custom-host
   azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/langgraph/invocations/04-custom-host/azure.yaml
   ```

3. Start the agent:

   ```bash
   azd ai agent run --no-client
   ```

4. Deploy after local testing:

   ```bash
   azd deploy
   ```

## Run directly with Python

From `src/langgraph-custom-host-invocations`:

```bash
python -m pip install uv
uv sync --frozen
cp .env.example .env
az login
uv run --no-sync python main.py
```

Send a location-aware request. The `-i` flag shows the
`x-agent-session-id` response header:

```bash
curl -i -X POST http://127.0.0.1:8088/invocations \
  -H "Content-Type: application/json" \
  -H "x-client-user-locale: en-US" \
  -d '{
    "message": [
      {
        "type": "message",
        "role": "developer",
        "content": "The user shared a location from the client.",
        "message_type": "location",
        "location": {
          "label": "Seattle",
          "latitude": 47.6062,
          "longitude": -122.3321
        }
      },
      {
        "type": "message",
        "role": "user",
        "content": [
          {
            "type": "input_text",
            "text": "What weather should I expect here?"
          }
        ]
      }
    ]
  }'
```

Use the returned session ID for a normal text follow-up:

```bash
curl -X POST \
  'http://127.0.0.1:8088/invocations?agent_session_id=REPLACE_WITH_SESSION_ID' \
  -H "Content-Type: application/json" \
  -H "x-client-user-locale: en-US" \
  -d '{"message":"Will I need an umbrella tomorrow?"}'
```
