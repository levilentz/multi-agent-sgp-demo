import os
import sys

from datetime import timedelta

from temporalio.contrib.openai_agents import OpenAIAgentsPlugin, ModelActivityParameters
from agentex.lib.core.temporal.plugins.openai_agents.interceptors.context_interceptor import ContextInterceptor
from agentex.lib.core.temporal.plugins.openai_agents.models.temporal_streaming_model import (
    TemporalStreamingModelProvider,
)
from agentex.lib.sdk.fastacp.fastacp import FastACP
from agentex.lib.types.fastacp import TemporalACPConfig
from agents import set_default_openai_client, set_default_openai_api

from project.openai_client import openai_client

set_default_openai_client(openai_client)
set_default_openai_api("chat_completions")


# === DEBUG SETUP (AgentEx CLI Debug Support) ===
if os.getenv("AGENTEX_DEBUG_ENABLED") == "true":
    try:
        import debugpy
        from agentex.lib.utils.logging import make_logger

        logger = make_logger(__name__)
        debug_port = int(os.getenv("AGENTEX_DEBUG_PORT", "5679"))
        debug_type = os.getenv("AGENTEX_DEBUG_TYPE", "acp")
        wait_for_attach = os.getenv("AGENTEX_DEBUG_WAIT_FOR_ATTACH", "false").lower() == "true"

        debugpy.configure(subProcess=False)
        debugpy.listen(debug_port)

        logger.info(f"[{debug_type.upper()}] Debug server listening on port {debug_port}")

        if wait_for_attach:
            logger.info(f"[{debug_type.upper()}] Waiting for debugger to attach...")
            debugpy.wait_for_client()
            logger.info(f"[{debug_type.upper()}] Debugger attached!")
        else:
            logger.info(f"[{debug_type.upper()}] Ready for debugger attachment")

    except ImportError:
        print("debugpy not available. Install with: pip install debugpy")
        sys.exit(1)
    except Exception as e:
        print(f"Debug setup failed: {e}")
        sys.exit(1)
# === END DEBUG SETUP ===

context_interceptor = ContextInterceptor()
streaming_model_provider = TemporalStreamingModelProvider(openai_client=openai_client)


# Create the ACP server
acp = FastACP.create(
    acp_type="agentic",
    config=TemporalACPConfig(
        # When deployed to the cluster, the Temporal address will be set automatically.
        # For local development, set TEMPORAL_ADDRESS to point to your local Temporal service.
        type="temporal",
        temporal_address=os.getenv("TEMPORAL_ADDRESS", "localhost:7233"),
        plugins=[OpenAIAgentsPlugin(
            model_params=ModelActivityParameters(
                start_to_close_timeout=timedelta(days=1)
            ),
            model_provider=streaming_model_provider
        )],
        interceptors=[context_interceptor]
    )
)


# Notice that we don't need to register any handlers when we use type="temporal"
# If you look at the code in agentex.lib.sdk.fastacp.impl.temporal_acp
# You can see that these handlers are automatically registered when the ACP is created

# @acp.on_task_create
# This will be handled by the method in your workflow that is decorated with @workflow.run

# @acp.on_task_event_send
# This will be handled by the method in your workflow that is decorated with @workflow.signal(name=SignalName.RECEIVE_EVENT)

# @acp.on_task_cancel
# This does not need to be handled by your workflow.
# It is automatically handled by the temporal client which cancels the workflow directly