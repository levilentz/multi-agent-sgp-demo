import os

from agentex.lib.sdk.fastacp.fastacp import FastACP
from agentex.lib.types.acp import SendMessageParams
from agentex.types.task_message_content import TextContent
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

acp = FastACP.create(acp_type="sync")

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


@acp.on_message_send
async def handle_message_send(params: SendMessageParams) -> TextContent:
    if not params.content or params.content.type != "text":
        return TextContent(author="agent", content="Unsupported message type.", format="plain")

    user_text = params.content.content

    async with adk.tracing.span(
        trace_id=params.task.id,
        name="handle_message",
        input={"user_text": user_text, "model": OAI_MODEL},
        data={"__span_type__": "COMPLETION"},
    ) as span:
        result = await Runner.run(chat_agent, input=user_text)
        assistant_reply = result.final_output

        total_input = 0
        total_output = 0
        for resp in result.raw_responses:
            total_input += resp.usage.input_tokens
            total_output += resp.usage.output_tokens

        if span:
            span.output = {
                "final_output": assistant_reply,
                "model": OAI_MODEL,
                "usage": {
                    "prompt_tokens": total_input,
                    "completion_tokens": total_output,
                    "total_tokens": total_input + total_output,
                },
            }

    return TextContent(author="agent", content=assistant_reply, format="markdown")
