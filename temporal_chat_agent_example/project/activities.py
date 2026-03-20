"""
Example Temporal activities for the temporal_chat_agent_example.

These activities are registered as tools on the OpenAI Agent via
`openai_agents.workflow.activity_as_tool()`, making every tool call a
durable, retriable Temporal activity execution.
"""

from temporalio import activity

from agentex.lib import adk
from agentex.types.text_content import TextContent


# ============================================================================
# ACTIVITY: Add Numbers
# ============================================================================

@activity.defn
async def add_numbers(num1: float, num2: float) -> str:
    """Add two numbers together and return the result as a string.

    Args:
        num1: The first number to add.
        num2: The second number to add.
    """
    result = num1 + num2
    return str({
        "operation": "addition",
        "num1": num1,
        "num2": num2,
        "result": result,
        "message": f"{num1} + {num2} = {result}",
    })


# ============================================================================
# ACTIVITY: Call LangChain Agent via ACP
# ============================================================================

LANGCHAIN_AGENT_NAME = "langchain-chat-agent-example"


@activity.defn
async def call_langchain_agent(query: str) -> str:
    """Delegate a query to the LangChain agent running in Agentex via ACP.

    The activity creates a new task on the LangChain agent, sends the query,
    waits for the synchronous response, and returns the text content.
    Because this is a Temporal activity it is durable and retriable.

    Args:
        query: The question or request to send to the LangChain agent.
    """
    logger = activity.logger

    logger.info(f"Calling LangChain agent with query: {query!r}")

    # 1. Create a new task on the LangChain agent
    task = await adk.acp.create_task(agent_name=LANGCHAIN_AGENT_NAME)
    logger.info(f"Created task {task.id} on agent '{LANGCHAIN_AGENT_NAME}'")

    # 2. Send the user query and collect the full synchronous response
    messages = await adk.acp.send_message(
        agent_name=LANGCHAIN_AGENT_NAME,
        task_id=task.id,
        content=TextContent(author="user", content=query),
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
