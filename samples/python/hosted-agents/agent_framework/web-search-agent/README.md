# Web Search Agent

A hosted agent that uses Bing Grounding to search the web for current information.

## Local Development

### Prerequisites

- Python 3.10+
- Azure CLI logged in (`az login`)
- An Azure AI Foundry project with:
  - A model deployment (e.g., `gpt-4.1-mini`)
  - A Bing Grounding connection

### Setup

1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

2. Create a `.env` file with the following environment variables:

```bash
AZURE_AI_PROJECT_ENDPOINT=https://<your-foundry-account>.services.ai.azure.com/api/projects/<your-project>
AZURE_AI_MODEL_DEPLOYMENT_NAME=<your-model-deployment>  # e.g., gpt-4.1-mini
BING_GROUNDING_CONNECTION_ID=/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<foundry-account>/projects/<project>/connections/<bing-connection-name>
```

### Run the agent locally

```bash
python main.py
```

The server will start on `http://localhost:8088`.

### Test the agent

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "What is the latest news in AI?"}' | jq .
```

## Troubleshooting

### Images built on Apple Silicon or other ARM64 machines do not work on our service

We **recommend using `azd` cloud build**, which always builds images with the correct architecture.

If you choose to **build locally**, and your machine is **not `linux/amd64`** (for example, an Apple Silicon Mac), the image will **not be compatible with our service**, causing runtime failures.

**Fix for local builds**

Use this command to build the image locally:

```shell
docker build --platform=linux/amd64 -t image .
```

This forces the image to be built for the required `amd64` architecture.
