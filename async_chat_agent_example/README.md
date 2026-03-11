# async-chat-agent-example - AgentEx Async Chat Agent

This example demonstrates how to build an **asynchronous** chat agent using the AgentEx framework. It mirrors the workflow of the `sync_chat_agent_example` but uses the async ACP pattern, where the agent processes events in the background and pushes replies back to the client proactively via `adk.messages.create()`.

## Key Differences from the Sync Agent

| | Sync Agent | Async Agent |
|---|---|---|
| `acp_type` | `"sync"` | `"async"` |
| Entry point | `@acp.on_message_send` | `@acp.on_task_create` + `@acp.on_task_event_send` + `@acp.on_task_cancel` |
| Response delivery | Return value from handler | `adk.messages.create()` called inside handler |
| Request/response model | Blocking — caller waits | Fire-and-forget — server acknowledges immediately, agent runs async |
| Event cursor | N/A | Must call `adk.agent_task_tracker.update(tracker_id, last_processed_event_id)` to commit progress |

## How It Works

1. **`on_task_create`** — Called when a new task is created. Initializes an empty `StateModel` (conversation history) in durable storage.

2. **`on_task_event_send`** — Called for each user message (event). The agent:
   - Loads conversation history from durable state
   - Appends the user message
   - Runs the OpenAI agent with all available tools
   - Appends the assistant reply
   - Persists updated state
   - Pushes the reply to the client via `adk.messages.create()`
   - Commits the event cursor via `adk.agent_task_tracker.update()`

3. **`on_task_cancel`** — Called when the task is cancelled. Sends a cancellation message to the client.

## Running the Agent

```bash
export ENVIRONMENT=development && agentex agents run --manifest manifest.yaml
```

## Project Structure

```
async_chat_agent_example/
├── project/
│   ├── __init__.py
│   ├── acp.py            # Async ACP server and event handlers
│   ├── openai_client.py  # OpenAI/SGP client configuration
│   └── tools.py          # Agent tools (e.g. add_numbers)
├── Dockerfile
├── manifest.yaml
├── pyproject.toml
└── requirements.txt
```

## Interacting with the Agent

```bash
# Submit a task via CLI
agentex tasks submit --agent async-chat-agent-example --task "What is 42 + 58?"
```
