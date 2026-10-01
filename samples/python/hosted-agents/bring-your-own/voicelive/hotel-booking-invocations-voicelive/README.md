<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. 
<!-- End standard disclaimer -->

# What this sample demonstrates

A hosted hotel-booking agent built with the **Invocations protocol** in Python, designed for **Voice Live compatible**.

The sample shows how to:

- Accept speech input via `input_audio.transcription` events.
- Accept UI/button actions via JSON click events (`select_hotel`, `confirm_booking`, `cancel`).
- Maintain per-session state for multi-turn conversations.
- Stream responses as SSE with `output_audio_transcription.delta` / `.done` plus custom UI events.

This sample uses a small in-memory hotel catalog and keyword-based intent handling. It does not require a model call.

## How it works

The agent in [main.py](src/hotel-booking-python-invocations-voicelive/main.py) uses the [Azure AI AgentServer Invocations SDK](https://pypi.org/project/azure-ai-agentserver-invocations/) to host an invocations endpoint.

At runtime it handles two input paths:

1. Voice path: `{"type":"input_audio.transcription","input":"..."}`
2. Click/UI path: arbitrary JSON with an `action` property

Depending on session state, the agent emits:

- Spoken text streaming events (`output_audio_transcription.delta`, then `.done`)
- Custom typed UI events (`ui.hotel_cards`, `ui.hotel_detail`, `ui.action_buttons`, `ui.booking_confirmed`, `ui.booking_update`)
- Final `done`

### Voice Live compatibility

For **Invocations** protocol agents, to make the agent work with Voice Live, the agent needs:

- The agent can process voice live transcription input: `{"type": "input_audio.transcription", "input": "example voice input"}`
- The agent should output the text to be read as the following SSE, Voice Live will generate audio for the the `delta` text in the `output_audio_transcription.delta` event:
  ```
  data: {"type": "output_audio_transcription.delta", "delta": "The weather "}
  data: {"type": "output_audio_transcription.delta", "delta": "in Seattle "}
  data: {"type": "output_audio_transcription.delta", "delta": "is 52°F "}
  data: {"type": "output_audio_transcription.delta", "delta": "and partly cloudy."}
  data: {"type": "output_audio_transcription.done", "text": "The weather in Seattle is 52°F and partly cloudy."}
  data: {"type": "done"}
  ```
- The agent manifest must declare `voiceLiveCompatible: "true"` in the metadata section to indicate compatibility with Voice Live.

### Custom structured input and passthrough events

#### Invoke input

In addition to speech-triggered invocations, clients can also send custom structured data to your agent by including an `invoke_input` field in `response.create` messages. Voice Live passes this JSON verbatim to your container.

For example, if the client sends:

```json
{
  "type": "response.create",
  "response": {
    "invoke_input": {
      "type": "button.click",
      "action": "confirm_booking"
    }
  }
}
```

Your container receives a POST to `/invocations` with body:

```json
{
  "type": "button.click",
  "action": "confirm_booking"
}
```

#### Passthrough event

Your agent can send any custom event type in the SSE stream. Voice Live forwards these to the client as `response.invocation.delta` messages.

For example, if your agent emits:

```json
data: {"type": "ui.flight_card", "flight": "AA 1234", "price": "$850"}
```

The client receives:

```json
{"type": "response.invocation.delta", "delta": {"type": "ui.flight_card", "flight": "AA 1234", "price": "$850"}}
```

This allows you to send structured data or UI cards to the client alongside speech responses.



## Running the agent locally

### Prerequisites

Before running this sample, ensure you have:

1. **Azure Developer CLI (`azd`)**
	 - [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd) and the AI agent extension: `azd ext install azure.ai.agents`
	 - Authenticated: `azd auth login`
2. **Python 3.12 or later**
   - Verify your version: `python --version`
3. **[uv](https://docs.astral.sh/uv/getting-started/installation/)** installed outside the project virtual environment

### Environment variables

This sample can run without extra environment variables.

See [`.env.example`](src/hotel-booking-python-invocations-voicelive/.env.example). `FOUNDRY_PROJECT_ENDPOINT` is optional and only needed in scenarios where your workflow expects it.

### Install dependencies

```bash
uv sync --frozen
```

### Start the agent

```bash
uv run --no-sync python main.py
```

The service listens on `http://localhost:8088`.

### Test with curl

Send a voice transcription event:

```bash
curl -sS -N -X POST "http://localhost:8088/invocations" \
	-H "Content-Type: application/json" \
	-d '{"type":"input_audio.transcription","input":"Find me a hotel in Seattle"}'
```

Use the same `agent_session_id` across turns to keep conversation and booking state.

## Using `azd`

No cloning required. Create a new folder, initialize from the manifest, then provision and run:

```bash
mkdir hotel-booking-agent && cd hotel-booking-agent

azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/bring-your-own/voicelive/hotel-booking-invocations-voicelive/azure.yaml

azd provision
azd ai agent run
```

Then invoke locally:

```bash
azd ai agent invoke --local '{"type":"input_audio.transcription","input":"Find me a hotel in Seattle"}'
```

## Deploying to Microsoft Foundry

```bash
azd provision
azd deploy
```

After deployment:

```bash
azd ai agent invoke '{"type":"input_audio.transcription","input":"Find me a hotel in Seattle"}'
```

Stream logs:

```bash
azd ai agent monitor
```

For full deployment guidance, see [Azure AI Foundry hosted agents](https://aka.ms/azdaiagent/docs).

### Sample client

We also provide a sample web UI client in the [../client/hotel-booking-sample-client](../client/hotel-booking-sample-client) folder. It demonstrates how to connect to the agent and do interaction with voice and custom events.

## Notes for production use

- Session state is in-memory and resets when the process restarts.
- Replace the in-memory store with Redis/Cosmos DB for durable sessions.
- Replace keyword intent matching with model-based NLU for robust behavior.
