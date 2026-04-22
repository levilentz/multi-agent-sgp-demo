FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.6.4 /uv /uvx /bin/

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
    && rm -rf /var/lib/apt/lists/*

RUN uv pip install --system --upgrade pip setuptools wheel

ENV UV_HTTP_TIMEOUT=1000

COPY pyproject.toml /app/pyproject.toml

WORKDIR /app

RUN uv pip install --system .

# Install patched local packages over the PyPI versions
COPY _local_sgp /app/_local_sgp
COPY _local_agentex /app/_local_agentex
RUN uv pip install --system --no-deps /app/_local_sgp && \
    uv pip install --system --no-deps /app/_local_agentex

COPY project /app/project

ENV PYTHONPATH=/app

CMD ["uvicorn", "project.acp:acp", "--host", "0.0.0.0", "--port", "8000"]
