# Foundry Model Router — API & SDK Samples

Simple "Hello World" Python examples showing how to use [Foundry Model Router](https://learn.microsoft.com/azure/foundry/openai/how-to/model-router) across different Azure OpenAI APIs and SDKs.

Model Router is a deployable AI chat model in Azure AI Foundry that **automatically selects the best underlying LLM** for each prompt in real time. It delivers high performance and cost savings from a single deployment — you use it just like any other chat model.

## Examples

| Folder | API | Auth | Description |
| ------ | --- | ---- | ----------- |
| [`chat-completions/`](./model-router-chat-completions.py) | Chat Completions | API Key | Basic single-prompt chat completion via `AzureOpenAI` client |
| [`model-router-chat-completions-observability.py`](./model-router-chat-completions-observability.py) | Chat Completions | API Key | Displays the selected model, routing mode, attempts, latency, and status for each routing decision |
| [`model-router-chat-completions-session-affinity.py`](./model-router-chat-completions-session-affinity.py) | Chat Completions | API Key | Reuses a session ID across conversation turns to demonstrate session-aware model routing |
| [`foundry-responses-sdk/`](./model-router-foundry-responses.py) | Foundry SDK | Entra ID | Uses `AIProjectClient` → `get_openai_client()` → Responses API |

## Prerequisites

- **Python 3.9+**
- **Azure subscription** with an Azure OpenAI resource
- **Model Router deployment** — deploy `model-router` from the model catalog in [Microsoft Foundry](https://ai.azure.com/)
- For the Foundry SDK example only: **Azure CLI** installed and logged in (`az login`)

## Setup

1. **Create a virtual environment** (recommended)

   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # macOS/Linux
   source .venv/bin/activate
   ```

2. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

3. **Create your `.env` file**

   ```bash
   cp .env.sample .env
   ```

   Edit `.env` with your values:

   ```text
   AZURE_OPENAI_ENDPOINT=https://your-resource-name.openai.azure.com/
   AZURE_OPENAI_API_KEY=your-api-key-here
   MODEL_DEPLOYMENT_NAME=model-router
   AZURE_AI_PROJECT_ENDPOINT=https://your-ai-services-account-name.services.ai.azure.com/api/projects/your-project-name
   ```

## Run the Examples

### Chat Completions API

```bash
python model-router-chat-completions.py
```

### Chat Completions Observability

```bash
python model-router-chat-completions-observability.py
```

#### Model Selection Details

This sample reads `response.model_selection_details`. The code inside the `<response_observability_extract>` tags parses that response fragment to print the routing mode, routing latency, and each model attempt.

The following JSON shows the `model_selection_details` fragment parsed by that code when the router falls back from one model to another:

```json
{
   "model_selection_details": {
      "model_router_details": {
         "mode": "balanced",
         "routing_trace": [
            {
               "latency_ms": 19,
               "attempts": [
                  {
                     "model": "example-model-a",
                     "result": {
                        "status": 404,
                        "error": {
                           "code": "NotFound",
                           "message": "The request failed."
                        }
                     }
                  },
                  {
                     "model": "example-model-b",
                     "result": {
                        "status": 200
                     }
                  }
               ]
            }
         ]
      }
   }
}
```

This payload is illustrative. The selected models, number of attempts, errors, latency, and preview response schema can vary by request and service version.

### Chat Completions Session Affinity (Preview)

```bash
python model-router-chat-completions-session-affinity.py
```

This sample creates an opaque session ID and sends it in `routing_config.session_affinity.session_id` for two conversation turns. It parses the affinity mode, identity source, and final decision from a response fragment like this:

```json
{
   "model_selection_details": {
      "model_router_details": {
         "mode": "balanced",
         "session_affinity": {
            "mode": "sticky",
            "source": "session_id_payload",
            "decision": "initialize"
         }
      }
   }
}
```

| Decision | Meaning |
| -------- | ------- |
| `initialize` | No previous model association was available, and the initially selected model served the response. |
| `retain` | The associated model served the response. |
| `switch` | Eligibility or fallback caused another model to serve the response. |

The sample is designed to demonstrate `initialize` followed by `retain`, but fallback can produce `switch` on either turn. The sample reports the actual outcome instead of forcing a service failure. Use the Chat Completions observability sample to inspect the routing attempts behind a `switch` decision. Session affinity is best-effort and does not store conversation content or guarantee a provider cache hit.

**Sample output:**
```text
--- First turn ---
Serving model: grok-4-1-fast-reasoning
Routing mode: balanced
Affinity mode: sticky
Affinity source: session_id_payload
Affinity decision: initialize
Response:
### One-Day Family Trip Itinerary to Seattle

--- Second turn ---
Serving model: grok-4-1-fast-reasoning
Routing mode: balanced
Affinity mode: sticky
Affinity source: session_id_payload
Affinity decision: retain
Response:
### Updated One-Day Family Trip Itinerary to Seattle (with Restaurant Suggestions & Indoor Focus)

```

### Foundry Responses SDK (Entra ID)

```bash
az login
python model-router-foundry-responses.py
```

## What to Expect

Each example prints:

- **Which underlying model** was selected by the router (e.g. `gpt-4.1-mini-2025-04-14`)
- **The model's response** to the prompt
- Token usage

The `model` field in the response reveals which LLM the router chose. You control routing behavior (Balanced / Quality / Cost) at deployment time in the Foundry portal — not in code.

## Resources

- [Model Router documentation](https://learn.microsoft.com/azure/foundry/openai/how-to/model-router)
- [Model Router concepts](https://learn.microsoft.com/azure/foundry/openai/concepts/model-router)
- [Azure OpenAI Chat Completions quickstart](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/chatgpt)
- [Azure AI Projects SDK (PyPI)](https://pypi.org/project/azure-ai-projects/)

## License

MIT
