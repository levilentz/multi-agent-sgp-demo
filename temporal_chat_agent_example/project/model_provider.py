from typing import Optional

from agents import Model, ModelProvider, OpenAIProvider
from openai import AsyncOpenAI


class ChatCompletionsModelProvider(ModelProvider):
    """ModelProvider that forces Chat Completions API instead of the Responses API.

    TemporalStreamingModelProvider is hardcoded to use the Responses API, which
    SGP/litellm does not support for Anthropic models. This provider delegates to
    OpenAIProvider with use_responses=False so all model calls go through
    /v1/chat/completions instead.
    """

    def __init__(self, openai_client: Optional[AsyncOpenAI] = None):
        self._provider = OpenAIProvider(
            openai_client=openai_client,
            use_responses=False,
        )

    def get_model(self, model_name: Optional[str]) -> Model:
        return self._provider.get_model(model_name)
