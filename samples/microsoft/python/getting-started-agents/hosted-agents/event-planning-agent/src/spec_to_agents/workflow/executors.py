# Copyright (c) Microsoft. All rights reserved.

"""Custom executors for event planning workflow with human-in-the-loop."""

import json
from datetime import datetime
from typing import Any, List

from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    BaseContent, ChatAgent,
    ChatMessage,
    Executor,
    FunctionCallContent,
    FunctionResultContent,
    Role,
    TextContent,
    WorkflowContext,
    handler,
    response_handler,
)
from pydantic import ValidationError

from spec_to_agents.models.messages import HumanFeedbackRequest, SpecialistOutput


def convert_tool_content_to_text(messages: list[ChatMessage]) -> list[ChatMessage]:
    """
    Convert tool calls and results to text summaries for cross-agent communication.

    When passing conversation history between agents with different service thread IDs,
    tool calls and results must be converted to text to avoid thread ID validation errors
    in Azure AI Agent Client. This preserves the context of what tools were used and their
    outcomes while making the messages compatible with a different agent's thread.

    Parameters
    ----------
    messages : list[ChatMessage]
        Original messages that may contain FunctionCallContent and FunctionResultContent

    Returns
    -------
    list[ChatMessage]
        New messages with tool content converted to TextContent summaries

    Notes
    -----
    This addresses the error: "No thread ID was provided, but chat messages includes tool results."
    Tool calls and results are inherently tied to the service thread where they were executed.
    When routing between agents in a workflow, each agent has its own thread ID, so we must
    convert tool-related content to plain text to avoid thread ID conflicts.
    """
    converted_messages = []
    for message in messages:
        new_contents = []
        for content in message.contents:
            if isinstance(content, FunctionCallContent):
                # Convert function call to descriptive text
                if isinstance(content.arguments, dict):
                    args_str = json.dumps(content.arguments)
                else:
                    args_str = str(content.arguments)
                text_repr = f"[Tool Call: {content.name}({args_str})]"
                new_contents.append(TextContent(text=text_repr))
            elif isinstance(content, FunctionResultContent):
                # Convert function result to descriptive text
                if content.result is not None:
                    result_str = _to_function_output(content.result)
                    text_repr = f"[Tool Result for call {content.call_id}: {result_str}]"
                elif content.exception is not None:
                    text_repr = f"[Tool Error for call {content.call_id}: {content.exception}]"
                else:
                    text_repr = f"[Tool Result for call {content.call_id}: No result]"
                new_contents.append(TextContent(text=text_repr))
            else:
                # Keep other content types as-is (TextContent, ImageContent, etc.)
                new_contents.append(content)

        # Create new message with converted contents, preserving role and metadata
        converted_messages.append(
            ChatMessage(
                role=message.role,
                contents=new_contents,
                author_name=message.author_name,
                message_id=message.message_id,
            )
        )
    return converted_messages


def _to_function_output(result: Any) -> str:
    if isinstance(result, str):
        return result
    elif isinstance(result, list):
        text = []
        for item in result:
            if isinstance(item, BaseContent):
                text.append(item.to_dict())
            else:
                text.append(str(item))
        return json.dumps(text)
    else:
        return ""


class EventPlanningCoordinator(Executor):
    """
    Coordinates event planning workflow with intelligent routing and human-in-the-loop.

    This coordinator manages dynamic execution of specialist agents using
    structured output routing (next_agent field). It leverages service-managed
    threads for conversation history, eliminating manual state tracking.

    Architecture
    ------------
    - Star topology: Coordinator ←→ Each specialist (bidirectional edges)
    - Structured output routing: Specialists indicate next agent via response
    - Handler-based routing: Logic in executor methods, not workflow edges
    - Framework-native HITL: Uses ctx.request_info() + @response_handler
    - Service-managed threads: Framework handles conversation history automatically

    Responsibilities
    ----------------
    - Receive initial user requests and route to venue specialist
    - Use structured output (SpecialistOutput) to determine next agent
    - Detect user_input_needed and request human feedback via ctx.request_info()
    - Route human responses back to requesting specialist
    - Synthesize final event plan after all specialists complete

    Parameters
    ----------
    coordinator_agent : ChatAgent
        The agent instance for synthesis and coordination logic
    """

    def __init__(self, coordinator_agent: ChatAgent):
        super().__init__(id="event_coordinator")
        self._agent = coordinator_agent

    @handler
    async def start(self, messages: List[ChatMessage], ctx: WorkflowContext[AgentExecutorRequest, str]) -> None:
        """
        Handle initial user request and route to venue specialist.

        Creates the initial conversation with the user's request and routes
        it to the venue specialist to begin the workflow.

        Parameters
        ----------
        prompt : str
            Initial user request (e.g., "Plan a corporate party for 50 people")
        ctx : WorkflowContext[AgentExecutorRequest]
            Workflow context for sending messages to specialists
        """
        # Route to venue specialist with user's initial request
        # _route_to_agent will wrap it in a ChatMessage
        context = ChatMessage(
            Role.ASSISTANT,
            text=f"Today's date is {datetime.now().strftime('%Y-%m-%d')}.",
        )
        prompt = "\n".join([msg.text for msg in messages])
        await self._route_to_agent("venue", prompt, ctx, prior_conversation=[context])

    @handler
    async def on_specialist_response(
        self,
        response: AgentExecutorResponse,
        ctx: WorkflowContext[AgentExecutorRequest, str],
    ) -> None:
        """
        Handle specialist response and route based on structured output.

        Uses SpecialistOutput fields to determine routing:
        - If user_input_needed=True: Pause for human input
        - Elif next_agent is set: Route to that specialist
        - Else: Synthesize final plan (workflow complete)

        Extracts full_conversation from the response to pass context to next agent.

        Parameters
        ----------
        response : AgentExecutorResponse
            Response from specialist containing SpecialistOutput
        ctx : WorkflowContext[AgentExecutorRequest, str]
            Workflow context for routing and requesting input
        """
        # Parse structured output from specialist
        specialist_output = self._parse_specialist_output(response)

        # Extract full conversation from specialist response
        conversation = list(response.full_conversation or response.agent_run_response.messages)

        # Route based ONLY on structured output fields
        if specialist_output.user_input_needed:
            # Pause workflow for human input, preserving conversation
            await ctx.request_info(
                request_data=HumanFeedbackRequest(
                    prompt=specialist_output.user_prompt or "Please provide input",
                    context={},
                    request_type="clarification",
                    requesting_agent=response.executor_id,
                    conversation=conversation,
                ),
                response_type=str,
            )
        elif specialist_output.next_agent:
            # Route to next specialist with full conversation history
            next_context = (
                f"Previous specialist ({response.executor_id}) completed their analysis. "
                f"Please review the conversation history and continue with your specialized analysis."
            )
            await self._route_to_agent(
                specialist_output.next_agent,
                next_context,
                ctx,
                prior_conversation=conversation,
            )
        else:
            # Workflow complete: next_agent=None and no user input needed
            await self._synthesize_plan(ctx, conversation)

    @response_handler
    async def on_human_feedback(
        self,
        original_request: HumanFeedbackRequest,
        feedback: str,
        ctx: WorkflowContext[AgentExecutorRequest, str],
    ) -> None:
        """
        Handle human feedback and route back to requesting specialist.

        Restores conversation history from the original request and adds
        the user's feedback to continue the conversation.

        Parameters
        ----------
        original_request : HumanFeedbackRequest
            Original request containing requesting_agent ID and conversation history
        feedback : str
            User's response (selection, clarification, approval)
        ctx : WorkflowContext[AgentExecutorRequest]
            Workflow context for routing
        """
        # Retrieve conversation history from original request
        conversation = list(original_request.conversation)

        # Route back to specialist with feedback and full conversation history
        feedback_context = (
            f"User provided the following input: {feedback}\nPlease continue with your analysis based on this feedback."
        )
        await self._route_to_agent(
            original_request.requesting_agent,
            feedback_context,
            ctx,
            prior_conversation=conversation,
        )

    async def _synthesize_plan(
        self,
        ctx: WorkflowContext[AgentExecutorRequest, str],
        conversation: list[ChatMessage],
    ) -> None:
        """
        Synthesize final event plan from all specialist recommendations.

        This method is called after all specialists have completed their work.
        Uses the conversation history with tool content converted to text summaries.

        Parameters
        ----------
        ctx : WorkflowContext[AgentExecutorRequest, str]
            Workflow context for yielding final output
        conversation : list[ChatMessage]
            Complete conversation history including all specialist interactions.
            Tool calls/results are converted to text summaries before synthesis.
        """
        # Convert tool content to text for coordinator's thread
        clean_conversation = convert_tool_content_to_text(conversation)

        # Add synthesis instruction
        synthesis_instruction = ChatMessage(
            Role.USER,
            text=(
                "All specialists have completed their work. Please synthesize a comprehensive "
                "event plan that integrates all specialist recommendations including venue "
                "selection, budget allocation, catering options, and logistics coordination. "
                "Provide a cohesive final plan."
            ),
        )
        clean_conversation.append(synthesis_instruction)

        # Run coordinator agent with converted conversation context
        synthesis_result = await self._agent.run(messages=clean_conversation)

        # Yield final plan as workflow output
        if synthesis_result.text:
            await ctx.yield_output(synthesis_result.text)

    def _parse_specialist_output(self, response: AgentExecutorResponse) -> SpecialistOutput:
        """
        Parse SpecialistOutput from agent response.

        Parameters
        ----------
        response : AgentExecutorResponse
            Agent's response containing structured output

        Returns
        -------
        SpecialistOutput
            Parsed structured output with routing decision

        Raises
        ------
        ValueError
            If response does not contain SpecialistOutput, includes actual response text for debugging
        """
        # Try to parse structured output if not already parsed
        if response.agent_run_response.value is None:
            response.agent_run_response.try_parse_value(SpecialistOutput)

        response_text = response.agent_run_response.text if response.agent_run_response.text else ""

        if response.agent_run_response.value and isinstance(response.agent_run_response.value, SpecialistOutput):
            return response.agent_run_response.value  # type: ignore[no-any-return]

        error_msg = ""
        if response_text:
            # Attempt to extract JSON from response text for debugging
            try:
                json_start = response_text.index("{")
                json_end = response_text.rindex("}") + 1
                json_str = response_text[json_start:json_end]
                return SpecialistOutput.model_validate_json(json_str)
            except ValidationError as e:
                error_msg = f"Failed to validate SpecialistOutput model: {e}"

        # Enhanced error message with debugging information
        num_messages = len(response.agent_run_response.messages) if response.agent_run_response.messages else 0

        # Analyze message contents to understand what's in the response
        content_analysis = self._analyze_message_contents(response.agent_run_response.messages)

        full_error_msg = (
            f"Specialist '{response.executor_id}' must return SpecialistOutput.\n"
            f"Response text: '{response_text}'\n"
            f"Number of messages: {num_messages}\n"
            f"Value is None: {response.agent_run_response.value is None}\n"
            f"\nMessage content analysis:\n{content_analysis}\n"
            f"\nPossible causes:\n"
            f"- Agent made tool calls but didn't generate final structured JSON output\n"
            f"- Agent response was truncated or incomplete\n"
            f"- Agent hit token limits before generating structured output\n"
            f"- Tool execution failed, preventing agent from completing response\n"
            f"Error message: {error_msg}"
        )
        raise ValueError(full_error_msg)

    def _analyze_message_contents(self, messages: list[ChatMessage] | None) -> str:
        """
        Analyze message contents to understand what types of content are present.

        Parameters
        ----------
        messages : list[ChatMessage] | None
            List of ChatMessage objects from AgentRunResponse

        Returns
        -------
        str
            Human-readable analysis of message contents
        """
        if not messages:
            return "  No messages in response"

        analysis_lines: list[str] = []
        for i, msg in enumerate(messages):
            if not hasattr(msg, "contents") or not msg.contents:
                analysis_lines.append(f"  Message {i}: No contents")
                continue

            content_types: list[str] = []
            for content in msg.contents:
                content_type = type(content).__name__
                content_types.append(content_type)

                # Add details for specific content types
                if hasattr(content, "name"):  # FunctionCallContent
                    content_types[-1] += f"(name={content.name})"  # type: ignore
                elif hasattr(content, "text") and content.text:  # type: ignore # TextContent
                    preview = content.text[:50] + "..." if len(content.text) > 50 else content.text  # type: ignore
                    content_types[-1] += f'(text="{preview}")'

            role = getattr(msg, "role", "unknown")
            analysis_lines.append(f"  Message {i} ({role}): {', '.join(content_types)}")

        return "\n".join(analysis_lines)

    async def _route_to_agent(
        self,
        agent_id: str,
        message: str,
        ctx: WorkflowContext[AgentExecutorRequest, str],
        prior_conversation: list[ChatMessage] | None = None,
    ) -> None:
        """
        Route message to specialist agent with conversation history.

        Builds complete conversation by combining prior history with new routing message.
        Converts tool calls and results to text summaries to avoid thread ID conflicts
        when passing messages between agents with different service threads.

        Parameters
        ----------
        agent_id : str
            ID of specialist to route to ("venue", "budget", "catering", "logistics")
        message : str
            New message/context for specialist
        ctx : WorkflowContext[AgentExecutorRequest]
            Workflow context for sending messages
        prior_conversation : list[ChatMessage] | None, optional
            Previous conversation history to preserve. If None, starts fresh conversation.
            Tool calls/results in prior conversation are converted to text summaries.

        Notes
        -----
        Tool content conversion is necessary because each agent has its own service-managed
        thread ID. Passing tool calls/results directly would cause Azure AI to reject the
        request with "No thread ID provided, but chat messages includes tool results."
        """
        # Convert prior conversation to remove tool-specific content
        conversation = convert_tool_content_to_text(prior_conversation) if prior_conversation else []

        # Add new routing message
        conversation.append(ChatMessage(Role.USER, text=message))

        await ctx.send_message(
            AgentExecutorRequest(
                messages=conversation,
                should_respond=True,
            ),
            target_id=agent_id,
        )
