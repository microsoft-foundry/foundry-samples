# Copyright (c) Microsoft. All rights reserved.

import json
import os
from collections.abc import AsyncGenerator

from agent_framework import Agent, AgentSession
from agent_framework.foundry import FoundryChatClient
from azure.ai.agentserver.invocations import InvocationAgentServerHost
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

# Load environment variables from .env file
load_dotenv()


# In-memory session store — keyed by session ID.
# WARNING: This is lost on restart. Use durable storage in production.
_sessions: dict[str, AgentSession] = {}

# Create the agent
client = FoundryChatClient(
    project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
    model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
    credential=DefaultAzureCredential(),
)

agent = Agent(
    client=client,
    instructions="You are a friendly assistant. Keep your answers brief.",
    # History will be managed by the hosting infrastructure, thus there
    # is no need to store history by the service. Learn more at:
    # https://developers.openai.com/api/reference/resources/responses/methods/create
    default_options={"store": False},
)

app = InvocationAgentServerHost()


def _sse(payload: dict) -> str:
    """Serialize one Server-Sent Events frame.

    The guardrail's `streamSelectors` read the `type` field of each frame to decide
    which frames carry model text, so every frame must be a JSON object with a
    `type`. See the README for why this sample streams structured frames rather
    than bare text.
    """
    return f"data: {json.dumps(payload)}\n\n"


@app.invoke_handler
async def handle_invoke(request: Request):
    """Handle streaming and buffered multi-turn chat over the invocations protocol."""
    data = await request.json()
    session_id = request.state.session_id

    stream = data.get("stream", False)
    user_message = data.get("message", None)
    if user_message is None:
        error = "Missing 'message' in request"
        if stream:
            return StreamingResponse(content=error, status_code=400)
        return Response(content=error, status_code=400)

    session = _sessions.setdefault(session_id, AgentSession(session_id=session_id))

    if stream:

        async def stream_response() -> AsyncGenerator[str]:
            async for update in agent.run(user_message, session=session, stream=True):
                if update.text:
                    yield _sse({"type": "message.delta", "text": update.text})
            yield _sse({"type": "message.done"})

        return StreamingResponse(
            stream_response(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    response = await agent.run([user_message], session=session, stream=stream)
    return JSONResponse({"response": response.text})


if __name__ == "__main__":
    app.run()
