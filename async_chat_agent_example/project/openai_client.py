from openai import AsyncOpenAI
import os
import httpx

SGP_API_KEY = os.getenv("SGP_API_KEY")
SGP_BASE_URL = os.getenv("SGP_BASE_URL")
if "v5" not in SGP_BASE_URL:
    SGP_BASE_URL = f"{SGP_BASE_URL}/v5/"
SGP_ACCOUNT_ID = os.getenv("SGP_ACCOUNT_ID", "68ffc1ffc7ff58ffd82e831a")
OPENAI_ORG_ID = os.getenv("OPENAI_ORG_ID", None)
max_retries = os.getenv("OPENAI_MAX_RETRIES", 100)
timeout = os.getenv("OPENAI_TIMEOUT", 10)

MAX_TOKENS = os.environ.get("OAI_MAX_TOKENS", 10000)
OAI_MODEL = os.environ.get("OAI_MODEL", "anthropic/claude-3-haiku-20240307")
TEMPERATURE_B100 = int(os.environ.get("OAI_TEMPERATURE_B100", 0))

# Check if running in local development mode
LOCAL_DEVELOPMENT = os.environ.get("LOCAL_DEVELOPMENT", "false").lower() == "true"

# Only disable SSL verification in local development mode
if LOCAL_DEVELOPMENT:
    http_client = httpx.AsyncClient(verify=False)
    openai_client = AsyncOpenAI(
        base_url=SGP_BASE_URL,
        api_key="",
        default_headers={
            "x-api-key": SGP_API_KEY,
            "x-selected-account-id": SGP_ACCOUNT_ID
        },
        http_client=http_client,
    )
else:
    # In production, use default SSL verification
    openai_client = AsyncOpenAI(
        base_url=SGP_BASE_URL,
        api_key="",
        default_headers={
            "x-api-key": SGP_API_KEY,
            "x-selected-account-id": SGP_ACCOUNT_ID
        },
    )
