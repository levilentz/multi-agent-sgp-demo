import os
from typing import List

from agentex.lib.sdk.fastacp.fastacp import FastACP
from agentex.lib.types.acp import SendMessageParams
from agentex.lib.utils.model_utils import BaseModel
from agentex.types.text_content import TextContent
from agents import Agent, Runner, set_default_openai_client
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from agentex.lib.core.tracing.tracing_processor_manager import (
    add_tracing_processor_config,
)
from agentex.lib.types.tracing import SGPTracingProcessorConfig
from agentex.lib import adk

from project.openai_client import openai_client, OAI_MODEL
from project.tools import ALL_TOOLS

set_default_openai_client(openai_client)

add_tracing_processor_config(
    SGPTracingProcessorConfig(
        sgp_api_key=os.environ.get("SGP_API_KEY", ""),
        sgp_account_id=os.environ.get("SGP_ACCOUNT_ID", ""),
        sgp_base_url=os.environ.get("SGP_BASE_URL", ""),
    )
)

# Create an ACP server
acp = FastACP.create(acp_type="sync")

# Create the agent with the tools from tools.py
chat_agent = Agent(
    name="ChatAgent",
    model=OpenAIChatCompletionsModel(model=OAI_MODEL, openai_client=openai_client),
    instructions=(
        "You are a helpful assistant. "
        "You have access to tools that can help you answer the user's questions. "
        "Use them whenever they are relevant."
    ),
    tools=ALL_TOOLS,
)


class StateModel(BaseModel):
    """Durable state model to track conversation history across turns"""
    input_list: List[dict]
    turn_number: int


@acp.on_message_send
async def handle_message_send(params: SendMessageParams):
    if not params.content or params.content.type != "text":
        return None

    task_id = params.task.id
    user_text = params.content.content

    # Retrieve durable state; fall back to a fresh state if missing
    task_state = await adk.state.get_by_task_and_agent(task_id=task_id, agent_id=params.agent.id)
    if not task_state:
        state = StateModel(input_list=[], turn_number=0)
        task_state = await adk.state.create(task_id=task_id, agent_id=params.agent.id, state=state)
    else:
        state = StateModel.model_validate(task_state.state)

    state.turn_number += 1
    state.input_list.append({"role": "user", "content": user_text})

    # Run the agent with the full conversation history
    result = await Runner.run(chat_agent, input=state.input_list)

    assistant_reply = result.final_output
    state.input_list.append({"role": "assistant", "content": assistant_reply})

    # Persist updated state for the next turn
    await adk.state.update(
        state_id=task_state.id,
        task_id=task_id,
        agent_id=params.agent.id,
        state=state,
    )

    return TextContent(author="agent", content=assistant_reply)
