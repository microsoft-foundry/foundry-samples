# Foundry Local Python Responses Web-Service Sample

This sample starts the Foundry Local OpenAI-compatible web service, then calls the Responses API with the official OpenAI Python client.

It demonstrates:

- A non-streaming `/v1/responses` call
- A streaming `/v1/responses` call
- A function/tool-calling round trip using `previous_response_id`

## What gets installed

Install the sample dependencies from `requirements.txt`:

```bash
pip install -r requirements.txt
```

That installs:

- The unified `foundry-local-sdk` package on every supported platform
- `openai`

The Windows wheel includes Windows ML support. The sample registers missing
execution providers and downloads `qwen2.5-0.5b` only when it is not cached.

## Run the sample

From this directory:

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python src\app.py
```

On macOS or Linux, activate the virtual environment with:

```bash
source .venv/bin/activate
```

The sample starts the local web service, sends Responses API requests to `http://localhost:<port>/v1`, prints the model output, and then unloads the model and stops the web service.
