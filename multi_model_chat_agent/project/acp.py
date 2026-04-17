"""
Multi-Model Chat Agent

Takes every user message and passes it to three different LLM providers
(GPT-4o, GPT-4o-mini, Claude 3.5 Sonnet) in parallel. Maintains separate
chat histories per model. Returns all three responses so you can compare.

Each model call gets its own traced span with proper model attribution so
the cost dashboard correctly breaks down tokens and cost per model.
"""

import asyncio
import os
from typing import Dict, List

from agentex.lib.core.tracing.tracing_processor_manager import (
    add_tracing_processor_config,
)
from agentex.lib.sdk.fastacp.fastacp import FastACP
from agentex.lib.types.acp import SendMessageParams
from agentex.lib.types.tracing import SGPTracingProcessorConfig
from agentex.lib.utils.model_utils import BaseModel
from agentex.lib import adk
from agentex.types.text_content import TextContent

from project.openai_client import openai_client, MODELS

# Register SGP tracing so spans flow to the cost dashboard
add_tracing_processor_config(
    SGPTracingProcessorConfig(
        sgp_api_key=os.environ.get("SGP_API_KEY", ""),
        sgp_account_id=os.environ.get("SGP_ACCOUNT_ID", ""),
        sgp_base_url=os.environ.get("SGP_BASE_URL", ""),
    )
)

acp = FastACP.create(acp_type="sync")

SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer the user's question concisely. "
    "Keep responses under 200 words unless more detail is needed."
)


class StateModel(BaseModel):
    """Durable state — one chat history list per model."""
    histories: Dict[str, List[dict]]
    turn_number: int


async def call_model(
    model: str,
    messages: List[dict],
    task_id: str,
    parent_span_id: str,
) -> dict:
    """
    Call a single model within its own traced span.
    Returns {"model": str, "reply": str, "prompt_tokens": int, "completion_tokens": int}.
    """
    async with adk.tracing.span(
        trace_id=task_id,
        name=f"llm:{model}",
        input={"model": model, "messages": messages[-3:]},  # last 3 for brevity
        data={"__span_type__": "COMPLETION"},
        parent_id=parent_span_id,
    ) as span:
        try:
            response = await openai_client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=1024,
            )
            reply = response.choices[0].message.content or ""
            prompt_tokens = response.usage.prompt_tokens if response.usage else 0
            completion_tokens = response.usage.completion_tokens if response.usage else 0
        except Exception as e:
            reply = f"[Error from {model}: {e}]"
            prompt_tokens = 0
            completion_tokens = 0

        if span:
            span.output = {
                "final_output": reply,
                "model": model,
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
            }

    return {
        "model": model,
        "reply": reply,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    }


@acp.on_message_send
async def handle_message_send(params: SendMessageParams):
    if not params.content or params.content.type != "text":
        return None

    task_id = params.task.id
    user_text = params.content.content

    # Load or create per-model chat histories
    task_state = await adk.state.get_by_task_and_agent(
        task_id=task_id, agent_id=params.agent.id
    )
    if not task_state:
        state = StateModel(
            histories={m: [{"role": "system", "content": SYSTEM_PROMPT}] for m in MODELS},
            turn_number=0,
        )
        task_state = await adk.state.create(
            task_id=task_id, agent_id=params.agent.id, state=state
        )
    else:
        state = StateModel.model_validate(task_state.state)
        # Handle new models added after state was created
        for m in MODELS:
            if m not in state.histories:
                state.histories[m] = [{"role": "system", "content": SYSTEM_PROMPT}]

    state.turn_number += 1

    # Append user message to all histories
    for m in MODELS:
        state.histories[m].append({"role": "user", "content": user_text})

    # Parent span for the entire turn
    async with adk.tracing.span(
        trace_id=task_id,
        name="multi_model_turn",
        input={"message": user_text, "models": MODELS, "turn": state.turn_number},
        data={"__span_type__": "CUSTOM"},
    ) as turn_span:
        parent_id = turn_span.id if turn_span else ""

        # Call all models in parallel — each gets its own child span
        results = await asyncio.gather(
            *[
                call_model(model, state.histories[model], task_id, parent_id)
                for model in MODELS
            ]
        )

        # Aggregate totals for the parent span
        total_prompt = sum(r["prompt_tokens"] for r in results)
        total_completion = sum(r["completion_tokens"] for r in results)

        if turn_span:
            turn_span.output = {
                "models_called": len(results),
                "usage": {
                    "prompt_tokens": total_prompt,
                    "completion_tokens": total_completion,
                    "total_tokens": total_prompt + total_completion,
                },
            }

    # Append assistant replies to each model's history
    for r in results:
        state.histories[r["model"]].append(
            {"role": "assistant", "content": r["reply"]}
        )

    # Persist state
    await adk.state.update(
        state_id=task_state.id,
        task_id=task_id,
        agent_id=params.agent.id,
        state=state,
    )

    # Format response showing all three model outputs
    parts = []
    for r in results:
        model_short = r["model"].split("/")[-1]
        tokens = f"({r['prompt_tokens']}in/{r['completion_tokens']}out)"
        parts.append(f"**{model_short}** {tokens}:\n{r['reply']}")

    combined = "\n\n---\n\n".join(parts)
    return TextContent(author="agent", content=combined)
