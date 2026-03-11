# acp-chat-agent-example - AgentEx Starter Template

This is a generic starter template for building agents with the AgentEx framework. It provides a basic implementation of the Agent 2 Client Protocol (ACP) to help you get started quickly.

## What You'll Learn

- **Tasks**: A task is a grouping mechanism for related messages. Think of it as a conversation thread or a session.
- **Messages**: Messages are communication objects within a task. They can contain text, data, or instructions.
- **ACP Events**: The agent responds to four main events:
  - `task_received`: When a new task is created
  - `task_message_received`: When a message is sent within a task
  - `task_approved`: When a task is approved
  - `task_canceled`: When a task is canceled

## Running the Agent

1. Run the agent locally:
```bash
agentex agents run --manifest manifest.yaml
```

The agent will start on port 8000 and print messages whenever it receives any of the ACP events.

## What's Inside

This template:
- Sets up a basic ACP server
- Handles each of the required ACP events with simple print statements
- Provides a foundation for building more complex agents

## Next Steps

For more advanced agent development, check out the AgentEx tutorials:

- **Tutorials 00-08**: Learn about building synchronous agents with ACP
- **Tutorials 09-10**: Learn how to use Temporal to power asynchronous agents
  - Tutorial 09: Basic Temporal workflow setup
  - Tutorial 10: Advanced Temporal patterns and best practices

These tutorials will help you understand:
- How to handle long-running tasks
- Implementing state machines
- Managing complex workflows
- Best practices for async agent development

## The Manifest File

The `manifest.yaml` file is your agent's configuration file. It defines:
- How your agent should be built and packaged
- What files are included in your agent's Docker image
- Your agent's name and description
- Local development settings (like the port your agent runs on)

This file is essential for both local development and deployment of your agent.

## Project Structure

```
acp_chat_agent_example/
├── project/                  # Your agent's code
│   ├── __init__.py
│   └── acp.py               # ACP server and event handlers
├── Dockerfile               # Container definition
├── manifest.yaml            # Deployment config
└── requirements.txt         # Dependencies
```

## Development

1. **Customize Event Handlers**
   - Modify the handlers in `acp.py` to implement your agent's logic
   - Add your own tools and capabilities
   - Implement custom state management

2. **Add Dependencies**
   - Add required packages to `requirements.txt`
   - Update the manifest with any needed credentials

## Local Development

1. **Install AgentEx**
```bash
cd agentex-py
uv venv
source .venv/bin/activate
uv sync
```

2. **Start the Agentex Server**
```bash
# Navigate to the backend directory
cd agentex

# Start all services using Docker Compose
make dev

# Optional: In a separate terminal, use lazydocker for a better UI (everything should say "healthy")
lzd
```

3. **Run your agent**
```bash
# From this directory
export ENVIRONMENT=development && agentex agents run --manifest manifest.yaml
```

4. **Interact with your agent**

Option 1: CLI
```bash
# Submit a task via CLI
agentex tasks submit --agent acp-chat-agent-example --task "Your task here"
```

Option 2: Web UI
```bash
# Start the local web interface
cd agentex-web
make dev

# Then open http://localhost:3000 in your browser to chat with your agent
```

## Development Tips

1. **Local Testing**
- Set environment variables in project/.env for any required credentials