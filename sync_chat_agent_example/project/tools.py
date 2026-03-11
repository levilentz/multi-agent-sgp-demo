"""
Tools for the agent.
Simple example tool demonstrating the tool pattern.
"""

from typing import Any
from agents import RunContextWrapper, FunctionTool
from pydantic import BaseModel, Field
from agentex.lib.utils.logging import make_logger

logger = make_logger(__name__)

# ============================================================================
# TOOL: Add Numbers
# ============================================================================


class AddNumbersParams(BaseModel):
    """Parameters for adding two numbers together."""

    num1: float = Field(
        description="The first number to add"
    )
    num2: float = Field(
        description="The second number to add"
    )


async def add_numbers_impl(ctx: RunContextWrapper[Any], args: str) -> str:
    """
    Add two numbers together and return the result.
    """
    logger.info(f"Adding numbers with args: {args}")
    args_parsed = AddNumbersParams.model_validate_json(args)
    
    result = args_parsed.num1 + args_parsed.num2
    
    return str({
        "operation": "addition",
        "num1": args_parsed.num1,
        "num2": args_parsed.num2,
        "result": result,
        "message": f"{args_parsed.num1} + {args_parsed.num2} = {result}"
    })


ADD_NUMBERS_TOOL = FunctionTool(
    name="add_numbers",
    description=(
        "Add two numbers together. Use this tool when you need to perform addition. "
        "Provide two numbers (num1 and num2) and get their sum."
    ),
    params_json_schema=AddNumbersParams.model_json_schema(),
    strict_json_schema=True,
    on_invoke_tool=add_numbers_impl,
)


# ============================================================================
# Export all tools
# ============================================================================

ALL_TOOLS = [
    ADD_NUMBERS_TOOL,
]

