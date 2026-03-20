from openai import AsyncOpenAI, OpenAI
import os
import httpx

SGP_API_KEY = os.getenv("SGP_API_KEY", "")
SGP_BASE_URL = os.getenv("SGP_BASE_URL", "")
if SGP_BASE_URL and "v5" not in SGP_BASE_URL:
    SGP_BASE_URL = f"{SGP_BASE_URL}/v5/"
SGP_ACCOUNT_ID = os.getenv("SGP_ACCOUNT_ID", "")

OAI_MODEL = os.environ.get("OAI_MODEL")

SGP_HEADERS = {
    "x-api-key": SGP_API_KEY,
    "x-selected-account-id": SGP_ACCOUNT_ID,
}

# Check if running in local development mode
LOCAL_DEVELOPMENT = os.environ.get("LOCAL_DEVELOPMENT", "false").lower() == "true"

# Only disable SSL verification in local development mode
if LOCAL_DEVELOPMENT:
    sync_http_client = httpx.Client(verify=False)
    async_http_client = httpx.AsyncClient(verify=False)
    openai_client = AsyncOpenAI(
        base_url=SGP_BASE_URL,
        api_key="",
        default_headers=SGP_HEADERS,
        http_client=async_http_client,
    )
    sync_openai_client = OpenAI(
        base_url=SGP_BASE_URL,
        api_key="",
        default_headers=SGP_HEADERS,
        http_client=sync_http_client,
    )
else:
    openai_client = AsyncOpenAI(
        base_url=SGP_BASE_URL,
        api_key="",
        default_headers=SGP_HEADERS,
    )
    sync_openai_client = OpenAI(
        base_url=SGP_BASE_URL,
        api_key="",
        default_headers=SGP_HEADERS,
    )
