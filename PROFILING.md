# Memory Profiling & Load Testing

This repo includes a harness for profiling agent memory usage under sustained load. It was built to investigate unbounded RSS growth in agents running with SGP tracing.

## Components

| File | Purpose |
|---|---|
| `langchain_chat_agent_example/project/profiling.py` | Instruments the agent with `tracemalloc` and exposes `/debug/memory` endpoints |
| `scripts/load_test.py` | Sends sustained or burst HTTP traffic to the agent while polling memory |
| `scripts/monitor_container.py` | Polls `docker stats` to CSV for the container-level RSS view |
| `scripts/run_memory_test.sh` | One-shot orchestrator that builds, starts, tests, and collects results |

## Prerequisites

- Docker Desktop or Rancher Desktop running
- A `.env` file at the repo root with your API keys:
  ```
  SGP_API_KEY=...
  SGP_ACCOUNT_ID=...
  SGP_BASE_URL=...
  OPENAI_API_KEY=...
  ```
- A Python venv for the test scripts:
  ```bash
  uv venv scripts/.venv
  source scripts/.venv/bin/activate
  uv pip install aiohttp
  ```

## Quick Start

### Option A: One-shot script (burst mode)

```bash
./scripts/run_memory_test.sh 200 10 25
#                            ^    ^  ^
#                            |    |  burst size
#                            |    concurrency
#                            total requests
```

This builds the agent, starts Docker services, runs the load test, monitors container memory, and saves all results to `memory_test_results/<timestamp>/`.

### Option B: Manual (sustained mode, recommended)

**Terminal 1** -- build and start:

```bash
docker compose build langchain-chat-agent
docker compose up -d langchain-chat-agent

# Wait for the agent to be ready
until curl -sf http://localhost:8002/healthz > /dev/null 2>&1; do sleep 2; done
echo "Agent is ready"

# Verify the debug endpoint works
curl -s http://localhost:8002/debug/memory | python3 -m json.tool
```

**Terminal 2** -- container monitor:

```bash
source scripts/.venv/bin/activate
python scripts/monitor_container.py \
    rocket-agentex-demo-langchain-chat-agent-1 \
    2 \
    memory_test_results/container_memory.csv
```

**Terminal 3** -- load test:

```bash
source scripts/.venv/bin/activate

# Sustained 3 req/s for 2000 requests (~11 min), sample every 100
python scripts/load_test.py --mode sustained --rate 3 --total 2000 --sample-every 100

# Or burst mode for a quick smoke test (~2-4 min)
python scripts/load_test.py --mode burst --total 100 --concurrency 10 --burst 25
```

## Load Test Modes

### Sustained mode (realistic)

Sends requests at a fixed rate to simulate real traffic patterns.

```bash
python scripts/load_test.py --mode sustained --rate 3 --total 2000 --sample-every 100
```

| Flag | Default | Description |
|---|---|---|
| `--rate` | 3.0 | Requests per second |
| `--total` | 2000 | Total requests to send |
| `--sample-every` | 100 | Poll `/debug/memory` every N requests |

### Burst mode (quick)

Sends batches of concurrent requests for faster results.

```bash
python scripts/load_test.py --mode burst --total 500 --concurrency 10 --burst 50
```

| Flag | Default | Description |
|---|---|---|
| `--concurrency` | 10 | Max concurrent requests |
| `--total` | 2000 | Total requests to send |
| `--burst` | 50 | Requests per burst |

## What the Load Test Does

1. Resets the tracemalloc baseline via `GET /debug/memory/reset`
2. Takes a baseline memory snapshot
3. Sends JSON-RPC `message/send` requests to `http://localhost:8002/api`
4. Each request has a ~4KB system prompt, varied questions, and a UUID nonce to bust LLM caches
5. Periodically polls `GET /debug/memory` and prints a snapshot
6. Waits 30s after all requests for GC
7. Prints a summary with per-request growth and 2-hour projections
8. Saves all snapshots to `memory_snapshots.json`

## Debug Endpoints

The profiling module adds these endpoints to the agent:

### `GET /debug/memory`

Returns JSON with:

- `rss_mb` -- current process RSS (from `/proc/self/status`)
- `traced_current_mb` / `traced_peak_mb` -- tracemalloc totals
- `smaps` -- `/proc/self/smaps_rollup` breakdown (Anonymous, Private_Dirty, etc.)
- `sgp_processors` -- span count in each SGP tracing processor's `_spans` dict
- `scale_gp_queue` -- internal export queue size and capacity
- `top_allocations` -- top 20 allocations by size (current)
- `diff_vs_baseline` -- top 20 growers since baseline (by line)
- `diff_traceback` -- top 15 growers with full call stacks
- `diff_vs_baseline_by_file` -- top 20 growers grouped by file

### `GET /debug/memory/reset`

Resets the tracemalloc baseline to the current moment. Useful for measuring growth across a specific test window.

## Interpreting Results

### Summary output

```
RESULTS SUMMARY
======================================================================
Total requests: 2000  |  OK: 2000  |  Errors: 0
Duration: 847s  |  Effective rate: 2.4 req/s

RSS:    310 MB -> 541 MB  (delta: +231.00 MB)
  Per-request: 118.5 KB/request
  Projected at 21600 req (2h @ 3/s): 2809 MB
Traced: 2.50 MB -> 25.00 MB  (delta: +22.50 MB)
```

### What to look for

| Signal | Likely cause |
|---|---|
| `sgp_processors.*.span_count` growing | `_spans` dict leak (fixed in agentex-sdk >= 0.10.2) |
| RSS growing linearly, traced memory flat | Leak in C extensions / JSON serialization / memory fragmentation |
| `copy.py` in top growers | `deepcopy` on span payloads (`scale_gp_beta` or `agentex-sdk` tracing) |
| `json/decoder.py` in top growers | JSON deserialization strings not being freed |
| Export queue size growing | `scale_gp_beta` queue not draining |
| Per-request growth > 50 KB/req | Likely a real leak (normal is ~10-30 KB/req) |

### Output files

| File | Content |
|---|---|
| `memory_snapshots.json` | Array of per-sample memory snapshots with tracemalloc diffs |
| `memory_test_results/container_memory.csv` | Docker stats time series (RSS, CPU, net I/O) |
| `memory_test_results/<timestamp>/load_test.log` | Full load test output (from `run_memory_test.sh`) |
| `memory_test_results/<timestamp>/final_memory.json` | Final `/debug/memory` dump |

## Testing Patches

### With local source packages

If you have source for `agentex-sdk` or `scale_gp_beta`, the Dockerfile is already set up to install local overrides:

1. Place the source in the agent directory:
   ```
   langchain_chat_agent_example/
     _local_sgp/          # scale_gp_beta source with pyproject.toml
     _local_agentex/      # agentex-sdk source with pyproject.toml
   ```

2. Rebuild and test:
   ```bash
   docker compose build langchain-chat-agent
   docker compose up -d langchain-chat-agent
   python scripts/load_test.py --mode sustained --rate 3 --total 2000 --sample-every 100
   ```

The Dockerfile installs PyPI packages first, then overwrites with `--no-deps` from the local source.

### Without source access (monkey-patching)

Add a monkey-patch in `acp.py` before requests are served:

```python
import scale_gp_beta.lib.tracing.span as _span_mod
from scale_gp_beta._utils import deepcopy_minimal
_span_mod.deepcopy = deepcopy_minimal
```

### Environment variable mitigations

Set in `docker-compose.yaml` to reduce memory fragmentation:

```yaml
environment:
  - PYTHONMALLOC=malloc            # bypass pymalloc, use glibc malloc
  - MALLOC_TRIM_THRESHOLD_=65536   # aggressively trim freed memory
```

Reduced per-request growth by ~10% in testing.

## Adding Profiling to Other Agents

1. Copy `langchain_chat_agent_example/project/profiling.py` to the agent's `project/` directory
2. In the agent's `acp.py`, add after the `FastACP.create()` call:
   ```python
   from project.profiling import setup_profiling
   setup_profiling(acp)
   ```
3. Rebuild the Docker image
4. Update `AGENT_URL` in `scripts/load_test.py` (or pass it via env) and adjust `make_payload()` for the agent's name and ACP type
