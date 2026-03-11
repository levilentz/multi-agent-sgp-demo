"""
Example Temporal activities for the temporal_chat_agent_example.

These activities are registered as tools on the OpenAI Agent via
`openai_agents.workflow.activity_as_tool()`, making every tool call a
durable, retriable Temporal activity execution.
"""

from pydantic import BaseModel, Field
from temporalio import activity

from agentex.lib import adk
from agentex.types.text_content import TextContent


# ============================================================================
# ACTIVITY: Add Numbers
# ============================================================================

class AddNumbersInput(BaseModel):
    """Input for adding two numbers together."""

    num1: float = Field(description="The first number to add")
    num2: float = Field(description="The second number to add")


@activity.defn
async def add_numbers(input: AddNumbersInput) -> str:
    """Add two numbers together and return the result as a string."""
    result = input.num1 + input.num2
    return str({
        "operation": "addition",
        "num1": input.num1,
        "num2": input.num2,
        "result": result,
        "message": f"{input.num1} + {input.num2} = {result}",
    })


# ============================================================================
# ACTIVITY: Call LangChain Agent via ACP
# ============================================================================

LANGCHAIN_AGENT_NAME = "langchain-chat-agent-example"


class CallLangchainAgentInput(BaseModel):
    """Input for delegating a query to the LangChain agent."""

    query: str = Field(
        description=(
            "The question or request to send to the LangChain agent. "
            "Use this tool when you need weather information or any other "
            "capability that the LangChain agent specialises in."
        )
    )


@activity.defn
async def call_langchain_agent(input: CallLangchainAgentInput) -> str:
    """
    Delegate a query to the LangChain agent running in Agentex via ACP.

    The activity:
    1. Creates a new task on the LangChain agent.
    2. Sends the query as a message and waits for the synchronous response.
    3. Extracts and returns the text content from the reply messages.

    Because this is a Temporal activity it is durable and retriable — if the
    worker crashes mid-call the activity will be replayed automatically.
    """
    logger = activity.logger

    logger.info(f"Calling LangChain agent with query: {input.query!r}")

    # 1. Create a new task on the LangChain agent
    task = await adk.acp.create_task(agent_name=LANGCHAIN_AGENT_NAME)
    logger.info(f"Created task {task.id} on agent '{LANGCHAIN_AGENT_NAME}'")

    # 2. Send the user query and collect the full synchronous response
    messages = await adk.acp.send_message(
        agent_name=LANGCHAIN_AGENT_NAME,
        task_id=task.id,
        content=TextContent(author="user", content=input.query),
    )
    logger.info(f"Received {len(messages) if messages else 0} message(s) from LangChain agent")

    # 3. Extract text from all returned messages
    if not messages:
        return "The LangChain agent returned no response."

    text_parts = []
    for msg in messages:
        content = msg.content
        # TextContent has a `.content` string attribute
        if hasattr(content, "content") and isinstance(content.content, str):
            text_parts.append(content.content)
        else:
            text_parts.append(str(content))

    return "\n".join(text_parts) if text_parts else "The LangChain agent returned no text."
