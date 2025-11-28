# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from dataclasses import dataclass
from typing import List
from uuid import uuid4

from agent_framework import (
    AIFunction, AgentRunResponseUpdate,
    AgentRunUpdateEvent,
    BaseChatClient,
    ChatMessage,
    Contents,
    Executor,
    Role as ChatRole,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework_azure_ai import AzureAIAgentClient
from azure.ai.agentserver.agentframework import from_agent_framework
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv(override=True)


@dataclass
class ReviewRequest:
    request_id: str
    user_messages: list[ChatMessage]
    agent_messages: list[ChatMessage]


@dataclass
class ReviewResponse:
    request_id: str
    feedback: str
    approved: bool


class Reviewer(Executor):
    """An executor that reviews messages and provides feedback."""

    def __init__(self, chat_client: BaseChatClient) -> None:
        super().__init__(id="reviewer")
        self._chat_client = chat_client
        self._agent = chat_client.create_agent(
            name="ToolClientAgent",
            instructions="You are a helpful assistant with access to various tools.",
        )

    @handler
    async def review(
        self, request: ReviewRequest, ctx: WorkflowContext[ReviewResponse]
    ) -> None:
        print(
            f"🔍 Reviewer: Evaluating response for request {request.request_id[:8]}..."
        )

        # Use the chat client to review the message and use structured output.
        # NOTE: this can be modified to use an evaluation framework.

        class _Response(BaseModel):
            feedback: str
            approved: bool

        # Define the system prompt.
        messages = [
            ChatMessage(
                role=ChatRole.SYSTEM,
                text="You are a reviewer for an AI agent, please provide feedback on the "
                "following exchange between a user and the AI agent, "
                "and indicate if the agent's responses are approved or not.\n"
                "Use the following criteria for your evaluation:\n"
                "- Relevance: Does the response address the user's query?\n"
                "- Accuracy: Is the information provided correct?\n"
                "- Clarity: Is the response easy to understand?\n"
                "- Completeness: Does the response cover all aspects of the query?\n"
                "Be critical in your evaluation and provide constructive feedback.\n"
                "Do not approve until all criteria are met.",
            )
        ]

        # Add user and agent messages to the chat history.
        messages.extend(request.user_messages)

        # Add agent messages to the chat history.
        messages.extend(request.agent_messages)

        # Add add one more instruction for the assistant to follow.
        messages.append(
            ChatMessage(
                role=ChatRole.USER,
                text="Please provide a review of the agent's responses to the user.",
            )
        )

        print("🔍 Reviewer: Sending review request to LLM...")
        # Get the response from the chat client.
        response = await self._agent.run(messages=messages, response_format=_Response)

        # Parse the response.
        parsed = _Response.model_validate_json(response.messages[-1].text)

        print(f"🔍 Reviewer: Review complete - Approved: {parsed.approved}")
        print(f"🔍 Reviewer: Feedback: {parsed.feedback}")

        # Send the review response.
        await ctx.send_message(
            ReviewResponse(
                request_id=request.request_id,
                feedback=parsed.feedback,
                approved=parsed.approved,
            )
        )


class Worker(Executor):
    """An executor that performs tasks for the user."""

    def __init__(self, tools: List[AIFunction], chat_client: AzureOpenAIChatClient) -> None:
        super().__init__(id="worker")
        self._agent = chat_client.create_agent(
            name="ToolClientAgent",
            instructions="You are a helpful assistant with access to various tools.",
            tools=tools,
        )
        self._pending_requests: dict[str, tuple[ReviewRequest, list[ChatMessage]]] = {}

    @handler
    async def handle_user_messages(
        self, user_messages: list[ChatMessage], ctx: WorkflowContext[ReviewRequest]
    ) -> None:
        print("🔧 Worker: Received user messages, generating response...")

        # Handle user messages and prepare a review request for the reviewer.
        messages = []

        # Add user messages.
        messages.extend(user_messages)

        print("🔧 Worker: Calling LLM to generate response...")
        # Get the response from the chat client.
        response = await self._agent.run(messages=messages)
        print(f"🔧 Worker: Response generated: {response.messages[-1].text}")

        # Add agent messages.
        messages.extend(response.messages)

        # Create the review request.
        request = ReviewRequest(
            request_id=str(uuid4()),
            user_messages=user_messages,
            agent_messages=[message for message in response.messages if message.role != ChatRole.TOOL],
        )

        print(
            f"🔧 Worker: Generated response, sending to reviewer (ID: {request.request_id[:8]})"
        )
        # Send the review request.
        await ctx.send_message(request)

        # Add to pending requests.
        self._pending_requests[request.request_id] = (request, messages)

    @handler
    async def handle_review_response(
        self, review: ReviewResponse, ctx: WorkflowContext[ReviewRequest]
    ) -> None:
        print(
            f"🔧 Worker: Received review for request {review.request_id[:8]} - Approved: {review.approved}"
        )

        # Handle the review response. Depending on the approval status,
        # either emit the approved response as AgentRunUpdateEvent, or
        # retry given the feedback.
        if review.request_id not in self._pending_requests:
            raise ValueError(
                f"Received review response for unknown request ID: {review.request_id}"
            )
        # Remove the request from pending requests.
        request, messages = self._pending_requests.pop(review.request_id)

        if review.approved:
            print("✅ Worker: Response approved! Emitting to external consumer...")
            # If approved, emit the agent run response update to the workflow's
            # external consumer.
            contents: list[Contents] = []
            for message in request.agent_messages:
                contents.extend(message.contents)
            # Emitting an AgentRunUpdateEvent in a workflow wrapped by a WorkflowAgent
            # will send the AgentRunResponseUpdate to the WorkflowAgent's
            # event stream.
            await ctx.add_event(
                AgentRunUpdateEvent(
                    self.id,
                    data=AgentRunResponseUpdate(
                        contents=contents, role=ChatRole.ASSISTANT
                    ),
                )
            )
            return

        print(f"❌ Worker: Response not approved. Feedback: {review.feedback}")
        print("🔧 Worker: Incorporating feedback and regenerating response...")

        # Construct new messages with feedback.
        messages.append(ChatMessage(role=ChatRole.SYSTEM, text=review.feedback))

        # Add additional instruction to address the feedback.
        messages.append(
            ChatMessage(
                role=ChatRole.SYSTEM,
                text="Please incorporate the feedback above, and provide a response to user's next message.",
            )
        )
        messages.extend(request.user_messages)

        # Get the new response from the chat client.
        response = await self._agent.run(messages=messages)
        print(
            f"🔧 Worker: New response generated after feedback: {response.messages[-1].text}"
        )

        # Process the response.
        messages.extend(response.messages)

        print(
            f"🔧 Worker: Generated improved response, sending for re-review (ID: {review.request_id[:8]})"
        )
        # Send an updated review request.
        new_request = ReviewRequest(
            request_id=review.request_id,
            user_messages=request.user_messages,
            agent_messages=response.messages,
        )
        await ctx.send_message(new_request)

        # Add to pending requests.
        self._pending_requests[new_request.request_id] = (new_request, messages)


def build_agent(tools: List[AIFunction], chat_client: AzureOpenAIChatClient):
    reviewer = Reviewer(chat_client=chat_client)
    worker = Worker(tools=tools, chat_client=chat_client)
    return (
        WorkflowBuilder()
        .add_edge(
            worker, reviewer
        )  # <--- This edge allows the worker to send requests to the reviewer
        .add_edge(
            reviewer, worker
        )  # <--- This edge allows the reviewer to send feedback back to the worker
        .set_start_executor(worker)
        .build()
        .as_agent()  # Convert the workflow to an agent.
    )


async def main() -> None:
    tool_connection_id = os.getenv("AZURE_AI_PROJECT_TOOL_CONNECTION_ID")

    async with DefaultAzureCredential() as credential:
        async with AzureAIAgentClient(async_credential=credential) as chat_client:
            await (from_agent_framework(
                lambda tools: build_agent(tools, chat_client),
                credentials=credential,
                tools=[{"type": "mcp", "project_connection_id": tool_connection_id}])
                   .run_async())


if __name__ == "__main__":
    asyncio.run(main())
