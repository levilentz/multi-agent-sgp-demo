from openai import AsyncOpenAI
import os
import httpx

SGP_API_KEY = os.getenv("SGP_API_KEY", "")
SGP_BASE_URL = os.getenv("SGP_BASE_URL", "")
if SGP_BASE_URL and "v5" not in SGP_BASE_URL:
    SGP_BASE_URL = f"{SGP_BASE_URL}/v5/"
SGP_ACCOUNT_ID = os.getenv("SGP_ACCOUNT_ID", "")

# Models to test against — all routed through SGP chat completions
MODELS = [
    os.environ.get("MODEL_1", "openai/gpt-4o"),
    os.environ.get("MODEL_2", "openai/gpt-4o-mini"),
    os.environ.get("MODEL_3", "anthropic/claude-3-5-sonnet-20241022"),
]

LOCAL_DEVELOPMENT = os.environ.get("LOCAL_DEVELOPMENT", "false").lower() == "true"

if LOCAL_DEVELOPMENT:
    http_client = httpx.AsyncClient(verify=False)
    openai_client = AsyncOpenAI(
        base_url=SGP_BASE_URL,
        api_key="",
        default_headers={
            "x-api-key": SGP_API_KEY,
            "x-selected-account-id": SGP_ACCOUNT_ID,
        },
        http_client=http_client,
    )
else:
    openai_client = AsyncOpenAI(
        base_url=SGP_BASE_URL,
        api_key="",
        default_headers={
            "x-api-key": SGP_API_KEY,
            "x-selected-account-id": SGP_ACCOUNT_ID,
        },
    )
