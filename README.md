# AgentEx Demo Agents

Four example agents demonstrating different patterns for building on the [AgentEx SDK](https://github.com/scaleapi/agentex) and deploying via the Scale GenAI Platform (SGP).

---

## Prerequisites

- Docker and Docker Compose v2.20+
- `uv` package manager

Install `uv` on macOS/Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Stop local Redis if running — it conflicts with Docker's Redis on port 6379:

```bash
brew services stop redis   # macOS
```

Then install the AgentEx SDK:

```bash
uv tool install agentex-sdk
```

---

## 1. Clone with Submodules

The AgentEx backend (`scale-agentex/`) is included as a git submodule. Clone with:

```bash
git clone --recurse-submodules <repo-url>
```

Or if already cloned:

```bash
git submodule update --init --recursive
```

---

## 2. Configure Each Agent

Copy `.env.example` to `.env` at the repo root and fill in your credentials:

```bash
cp .env.example .env
```

```bash
SGP_API_KEY=<your-sgp-api-key>
SGP_ACCOUNT_ID=<your-sgp-account-id>
SGP_BASE_URL=<your-sgp-base-url>   # e.g. https://egp.dashboard.scale.com/api
OAI_MODEL=<e.g. openai/gpt-4o or anthropic/claude-3-haiku-20240307>
```

All agents share this single file. The local AgentEx backend URL (`http://agentex:5003`) is injected separately by docker-compose and does not need to be set here.

---

## 3. One-time UI Setup

The AgentEx UI is built as a production Next.js bundle inside Docker. Environment variables are baked in at build time, so copy the example env file before the first build:

```bash
cp scale-agentex/agentex-ui/example.env.development scale-agentex/agentex-ui/.env.local
```

---

## 4. Start Everything

A single `docker compose up` starts the full stack: AgentEx backend infrastructure (Postgres, Redis, MongoDB, Temporal), the AgentEx UI, and all 4 demo agents.

```bash
docker compose up --build -d
```

| Service | URL |
|---|---|
| **AgentEx UI** | http://localhost:3000 |
| **AgentEx API** | http://localhost:5003 |
| Temporal UI | http://localhost:8080 |
| Swagger Docs | http://localhost:5003/swagger |

The demo agents are reachable at:

| Agent | Host Port | Pattern |
|---|---|---|
| `async-chat-agent` | 8001 | Stateless async |
| `langchain-chat-agent` | 8002 | Streaming LangGraph ReAct |
| `sync-chat-agent` | 8003 | Blocking sync + durable state |
| `temporal-chat-agent` | 8004 | Durable Temporal workflow |
| `temporal-chat-worker` | — | Temporal worker (no port) |

The demo agents wait for the AgentEx backend to be healthy before starting, so the full stack may take a minute to come up on first run.

---

## 5. Tear Down

```bash
docker compose down
```

---

## How the Agents Work

All four agents implement the **Agent Communication Protocol (ACP)** via `FastACP` from `agentex-sdk`. ACP is the interface between the AgentEx backend and the agent: it handles task lifecycle events (message received, task created, task cancelled) and routes them to your handler functions.

Every agent exposes a single entry point:

```
uvicorn project.acp:acp --host 0.0.0.0 --port 8000
```

### ACP Types

`FastACP.create(acp_type=...)` controls how the agent handles requests:

- **`"sync"`** — the handler is called inline and returns a value directly; the HTTP response is held open until the handler returns
- **`"agentic"`** — the handler signals a Temporal workflow and returns immediately; the workflow pushes responses back via `adk.messages.create()`

---

### Agent 1: Sync Chat Agent (`sync_chat_agent_example`) — port 8003

**Pattern:** Blocking request/response with durable multi-turn memory

The handler runs the OpenAI agent synchronously and blocks until it returns. Between turns, conversation history is persisted in the AgentEx state store via `adk.state`, so the agent remembers prior messages across separate HTTP requests.

```
User message → handler → load state from adk.state
                       → Runner.run(agent, full history)
                       → save updated state to adk.state
                       → return TextContent reply
```

Best for: agents that need reliable multi-turn memory without the overhead of a workflow engine.

---

### Agent 2: Async Chat Agent (`async_chat_agent_example`) — port 8001

**Pattern:** Stateless fire-and-forget

Also `acp_type="sync"` but intentionally stateless — each message is handled independently with no memory of previous turns. Useful as the simplest possible baseline, or for single-shot tasks where context carries over in the user message itself.

```
User message → handler → Runner.run(agent, message only)
                       → return TextContent reply
```

Best for: simple, context-free tasks or as a starting template.

---

### Agent 3: LangChain Chat Agent (`langchain_chat_agent_example`) — port 8002

**Pattern:** Streaming ReAct agent via LangGraph

Uses a `StateGraph` (`START → agent → [tools_condition] → tools → agent → END`) and streams events back to the caller as they happen. Cross-request memory is handled by the **AgentEx HTTP Checkpointer**, which persists LangGraph state between turns without any manual state management.

```
User message → handler → graph.astream(...)
                       → stream tokens + tool call events → caller
                       → checkpointer persists graph state for next turn
```

Best for: agents that benefit from streaming output, complex tool-use chains, or LangChain/LangGraph ecosystem integrations.

---

### Agent 4: Temporal Chat Agent (`temporal_chat_agent_example`) — port 8004

**Pattern:** Durable long-running workflow via Temporal

Uses `acp_type="agentic"` with a `TemporalACPConfig`. When a message arrives, the ACP server signals a Temporal workflow rather than running the agent inline. The workflow handles the conversation durably — if the process crashes mid-run, Temporal replays the workflow from its event log.

Requires two containers running from the same image:
- **`temporal-chat-agent`** — the ACP HTTP server (receives messages, signals workflows)
- **`temporal-chat-worker`** — the Temporal worker (executes the workflow and activities)

Tool calls inside the workflow are wrapped as Temporal activities, making each one a durable, retriable unit of work. The agent can also call other agents (e.g. the LangChain agent) via ACP as an inter-agent activity.

```
User message → ACP server → signal Temporal workflow
                                   ↓
              Temporal worker picks up workflow
                                   ↓
              workflow → activity (LLM call) → activity (tool call) → ...
                                   ↓
              adk.messages.create() pushes reply back to caller
```

Best for: long-running tasks, tasks that must survive restarts, or complex multi-step pipelines that need guaranteed execution.

---

## Project Structure

```
rocket-agentex-demo/
├── docker-compose.yaml          # Starts full stack via `include` + 4 demo agents
├── scale-agentex/               # Git submodule — AgentEx backend + UI
│   ├── agentex/docker-compose.yml   # Included by root compose
│   └── agentex-ui/              # Next.js frontend
├── async_chat_agent_example/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── project/
│       ├── acp.py          # FastACP entry point
│       ├── openai_client.py
│       └── tools.py
├── langchain_chat_agent_example/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── project/
│       ├── acp.py          # FastACP entry point + event streaming
│       ├── graph.py        # LangGraph StateGraph definition
│       ├── openai_client.py
│       └── tools.py
├── sync_chat_agent_example/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── project/
│       ├── acp.py          # FastACP entry point + adk.state
│       ├── openai_client.py
│       └── tools.py
└── temporal_chat_agent_example/
    ├── Dockerfile
    ├── pyproject.toml
    └── project/
        ├── acp.py          # FastACP entry point (agentic/Temporal)
        ├── workflow.py     # Temporal workflow definition
        ├── activities.py   # Durable Temporal activities
        ├── run_worker.py   # Temporal worker entry point
        └── openai_client.py
```

---

## Local Development (without Docker)

Each agent can be run directly for faster iteration:

```bash
cd <agent_directory>
uv sync
agentex agents run --manifest manifest.yaml
# or directly:
uvicorn project.acp:acp --host 0.0.0.0 --port 800X --reload
```

For the Temporal agent, run the worker in a second terminal:

```bash
cd temporal_chat_agent_example
uv run python -m project.run_worker
```

When running outside Docker, set `AGENTEX_API_BASE_URL=http://localhost:5003` in your `.env` so the agent can reach the backend.
