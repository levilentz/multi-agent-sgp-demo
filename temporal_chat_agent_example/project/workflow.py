from datetime import timedelta
from typing import List, Dict, Any

from temporalio import workflow
from temporalio.contrib import openai_agents
from pydantic import BaseModel

from agentex.lib import adk
from agentex.lib.types.acp import CreateTaskParams, SendEventParams
from agentex.lib.core.temporal.workflows.workflow import BaseWorkflow
from agentex.lib.core.temporal.types.workflow import SignalName
from agentex.lib.core.temporal.plugins.openai_agents.hooks.hooks import TemporalStreamingHooks
from agentex.lib.utils.logging import make_logger
from agentex.lib.environment_variables import EnvironmentVariables
from agentex.types.text_content import TextContent
from agents import Agent, Runner, set_default_openai_client, set_default_openai_api

from project.openai_client import openai_client, OAI_MODEL
from project.activities import add_numbers, call_langchain_agent

set_default_openai_client(openai_client)
set_default_openai_api("chat_completions")

environment_variables = EnvironmentVariables.refresh()

if environment_variables.WORKFLOW_NAME is None:
    raise ValueError("Environment variable WORKFLOW_NAME is not set")

if environment_variables.AGENT_NAME is None:
    raise ValueError("Environment variable AGENT_NAME is not set")

logger = make_logger(__name__)


class StateModel(BaseModel):
    """
    Durable in-workflow state that persists across conversation turns.

    Because this lives inside a Temporal workflow instance, it survives
    worker restarts and is replayed automatically by the Temporal SDK.
    """

    input_list: List[Dict[str, Any]]
    turn_number: int


class TurnInput(BaseModel):
    input_list: List[Dict[str, Any]]


class TurnOutput(BaseModel):
    final_output: Any


@workflow.defn(name=environment_variables.WORKFLOW_NAME)
class TemporalChatAgentExampleWorkflow(BaseWorkflow):
    """
    Temporal workflow for the temporal_chat_agent_example.

    This workflow demonstrates how to:
    - Maintain conversation history across turns inside Temporal workflow state
    - Use `openai_agents.workflow.activity_as_tool()` so every tool call the
      OpenAI agent makes is executed as a durable, retriable Temporal activity
    - Stream text responses back to the UI via TemporalStreamingModelProvider
      (configured in acp.py / run_worker.py)
    """

    def __init__(self):
        super().__init__(display_name=environment_variables.AGENT_NAME)
        self._complete_task = False
        self._state: StateModel = StateModel(input_list=[], turn_number=0)
        self._task_id = None
        self._trace_id = None
        self._parent_span_id = None

    def _normalize_to_simple_format(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert all messages to simple Chat Completions format."""
        normalized = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            # Handle Responses API format (content is a list of typed parts)
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") in ("input_text", "output_text", "text"):
                            text_parts.append(item.get("text", ""))
                        elif "text" in item:
                            text_parts.append(item.get("text", ""))
                content = " ".join(text_parts)

            if content:
                normalized.append({"role": role, "content": content})

        return normalized

    @workflow.signal(name=SignalName.RECEIVE_EVENT)
    async def on_task_event_send(self, params: SendEventParams) -> None:
        logger.info(f"Received task event: {params}")

        try:
            self._state.turn_number += 1

            self._task_id = params.task.id
            self._trace_id = params.task.id
            self._parent_span_id = params.task.id

            user_message_content = params.event.content.content
            self._state.input_list.append({"role": "user", "content": user_message_content})

            normalized_input = self._normalize_to_simple_format(self._state.input_list)

            logger.info(
                f"Turn {self._state.turn_number}: {len(normalized_input)} messages in history"
            )

            # Echo the user's message back so it appears in the UI immediately
            await adk.messages.create(task_id=params.task.id, content=params.event.content)

            temporal_streaming_hooks = TemporalStreamingHooks(task_id=params.task.id)

            turn_input = TurnInput(input_list=self._state.input_list)
            async with adk.tracing.span(
                trace_id=params.task.id,
                name=f"Turn {self._state.turn_number}",
                input=turn_input.model_dump(),
            ) as span:
                self._parent_span_id = span.id if span else None

                # Build the agent fresh each turn.
                # Tools are registered as Temporal activities via activity_as_tool(),
                # which makes every tool call a durable Temporal activity execution.
                agent = Agent(
                    name="temporal-chat-agent",
                    instructions=(
                        "You are a helpful assistant. "
                        "You have access to tools that can help you answer the user's questions. "
                        "Use them whenever they are relevant. "
                        "When the user asks about weather or anything the LangChain agent "
                        "specialises in, delegate to it using the call_langchain_agent tool."
                    ),
                    model=OAI_MODEL,
                    tools=[
                        openai_agents.workflow.activity_as_tool(
                            add_numbers,
                            start_to_close_timeout=timedelta(minutes=2),
                        ),
                        openai_agents.workflow.activity_as_tool(
                            call_langchain_agent,
                            start_to_close_timeout=timedelta(minutes=5),
                        ),
                    ],
                )

                logger.info(f"Turn {self._state.turn_number}: Starting Runner.run()")

                # TemporalStreamingModelProvider (configured in acp.py + run_worker.py)
                # streams text tokens back to the UI as they are generated.
                # TemporalStreamingHooks handles tool-call and handoff events.
                result = await Runner.run(agent, normalized_input, hooks=temporal_streaming_hooks)

                logger.info(
                    f"Turn {self._state.turn_number}: Runner.run() complete, "
                    f"final_output type: {type(result.final_output)}"
                )

                if result.final_output:
                    self._state.input_list.append(
                        {"role": "assistant", "content": str(result.final_output)}
                    )

                if span:
                    turn_output = TurnOutput(final_output=result.final_output)
                    span.output = turn_output.model_dump()

            logger.info(f"Turn {self._state.turn_number}: Completed successfully")

        except Exception as e:
            logger.error(
                f"Turn {self._state.turn_number}: Exception in signal handler: {e}",
                exc_info=True,
            )
            try:
                await adk.messages.create(
                    task_id=params.task.id,
                    content=TextContent(
                        author="agent",
                        content=f"I encountered an error processing your request: {e}. Please try again.",
                    ),
                )
            except Exception as msg_error:
                logger.error(f"Failed to send error message to user: {msg_error}")

    @workflow.run
    async def on_task_create(self, params: CreateTaskParams) -> str:
        logger.info(f"Received task create params: {params}")

        await workflow.wait_condition(
            lambda: self._complete_task,
            timeout=None,
        )
        return "Task completed"
