# syntax=docker/dockerfile:1.3
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
    nodejs \
    npm \ 
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/**

RUN uv pip install --system --upgrade pip setuptools wheel

ENV UV_HTTP_TIMEOUT=1000

# Copy just the pyproject.toml file to optimize caching
COPY langchain_chat_agent_example/pyproject.toml /app/langchain_chat_agent_example/pyproject.toml

WORKDIR /app/langchain_chat_agent_example

# Install the required Python packages using uv
RUN uv pip install --system .

# Copy the project code
COPY langchain_chat_agent_example/project /app/langchain_chat_agent_example/project

# Set environment variables
ENV PYTHONPATH=/app

# Run the agent using uvicorn
CMD ["uvicorn", "project.acp:acp", "--host", "0.0.0.0", "--port", "8000"] 