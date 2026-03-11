FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.6.4 /uv /uvx /bin/

# Install system dependencies
RUN apt-get update && apt-get install -y \
    htop \
    vim \
    curl \
    tar \
    python3-dev \
    postgresql-client \
    build-essential \
    libpq-dev \
    gcc \
    cmake \
    netcat-openbsd \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install tctl (Temporal CLI)
RUN curl -L https://github.com/temporalio/tctl/releases/download/v1.18.1/tctl_1.18.1_linux_arm64.tar.gz -o /tmp/tctl.tar.gz && \
    tar -xzf /tmp/tctl.tar.gz -C /usr/local/bin && \
    chmod +x /usr/local/bin/tctl && \
    rm /tmp/tctl.tar.gz

RUN uv pip install --system --upgrade pip setuptools wheel

# Copy dependency requirements
COPY agentex-py/pyproject.toml /app/agentex-py/pyproject.toml
COPY agentex-py/uv.lock /app/agentex-py/uv.lock
COPY agentex-py/README.md /app/agentex-py/README.md

ENV UV_HTTP_TIMEOUT=1000

# Install agentex-py dependencies
RUN uv pip install --system -r /app/agentex-py/pyproject.toml

# Copy the agentex-py code
COPY agentex-py /app/agentex-py

# Copy just the requirements file to optimize caching
COPY rocket/rocket-agentex-demo/temporal_chat_agent_example/requirements.txt /app/rocket/rocket-agentex-demo/temporal_chat_agent_example/requirements.txt

WORKDIR /app/rocket/rocket-agentex-demo/temporal_chat_agent_example

# Install the required Python packages
RUN uv pip install --system -r requirements.txt

# Copy the project code
COPY rocket/rocket-agentex-demo/temporal_chat_agent_example/project /app/rocket/rocket-agentex-demo/temporal_chat_agent_example/project

WORKDIR /app/rocket/rocket-agentex-demo/temporal_chat_agent_example/project

# Run the ACP server using uvicorn
CMD ["uvicorn", "acp:acp", "--host", "0.0.0.0", "--port", "8000"]

# When we deploy the worker, we will replace the CMD with the following
# CMD ["python", "-m", "run_worker"] 