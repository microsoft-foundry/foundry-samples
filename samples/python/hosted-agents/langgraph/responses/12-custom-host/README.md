# What this sample demonstrates

A location-aware LangGraph chat agent hosted over the **Responses protocol**. It demonstrates when and how to use custom ResponsesHostServer implementations for custom input and graph states.

The agent uses calculator, current-time, and fake-weather tools.
`LocationAwareResponsesHostServer` adds support for:

- an `x-client-user-locale` header that controls language and temperature units; and
- a custom location message containing a map location shared by the user.

Normal user messages, streaming, and `previous_response_id` conversations still
use standard Responses behavior.

## Custom request

The client can send a standard user message alongside a location message:

```json
{
  "input": [
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

`message_type` and `location` are application-defined extensions on a standard
Responses message item. The custom host reads them into the graph state and
reads `x-client-user-locale`; for example, `en-US` selects Fahrenheit while `fr-FR`
selects Celsius.

```text
Turn 1: location message + "What weather should I expect here?"
Turn 2: "Will I need an umbrella tomorrow?" + previous_response_id
```

## How the customization works

The locale middleware reads `x-client-user-locale`.
`LocationAwareResponsesHostServer.build_input` extracts the location and then
delegates standard message conversion to `ResponsesHostServer`. The graph
receives:

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
   azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/langgraph/responses/12-custom-host/azure.yaml
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

From `src/langgraph-custom-host-responses`:

```bash
python -m pip install uv
uv sync --frozen
cp .env.example .env
az login
uv run --no-sync python main.py
```

Send a location-aware request:

```bash
curl -X POST http://127.0.0.1:8088/responses \
  -H "Content-Type: application/json" \
  -H "x-client-user-locale: en-US" \
  -d '{
    "input": [
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

Pass the returned response ID as `previous_response_id` on later requests to
continue the conversation without sending the location again.
