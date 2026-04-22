#!/usr/bin/env bash
#
# Memory profiling test for the langchain chat agent.
#
# Builds the agent with profiling instrumentation, starts the required
# services, runs the load test while monitoring container memory, and
# collects the results.
#
# Usage:
#   ./scripts/run_memory_test.sh [total_requests] [concurrency] [burst_size]
#   ./scripts/run_memory_test.sh 200 10 25
#
set -euo pipefail
cd "$(dirname "$0")/.."

TOTAL=${1:-100}
CONCURRENCY=${2:-10}
BURST=${3:-25}
CONTAINER="rocket-agentex-demo-langchain-chat-agent-1"
RESULTS_DIR="memory_test_results/$(date +%Y%m%d_%H%M%S)"

mkdir -p "$RESULTS_DIR"

echo "============================================"
echo " Memory Profiling Test — LangChain Agent"
echo "============================================"
echo "Requests:    $TOTAL"
echo "Concurrency: $CONCURRENCY"
echo "Burst size:  $BURST"
echo "Results dir: $RESULTS_DIR"
echo ""

# ── Step 1: Build ──────────────────────────────────────────────────
echo "=== Step 1: Building langchain-chat-agent ==="
docker compose build langchain-chat-agent

# ── Step 2: Start services ─────────────────────────────────────────
echo ""
echo "=== Step 2: Starting langchain-chat-agent (+ dependencies) ==="
docker compose up -d langchain-chat-agent

echo "Waiting for agent to be ready..."
for i in $(seq 1 60); do
    if curl -sf http://localhost:8002/healthz > /dev/null 2>&1; then
        echo "Agent is ready!"
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "ERROR: Agent did not become healthy within 120s"
        docker compose logs langchain-chat-agent --tail=50
        exit 1
    fi
    sleep 2
done

# Quick sanity check — can we hit the debug endpoint?
echo "Checking /debug/memory endpoint..."
if ! curl -sf http://localhost:8002/debug/memory > /dev/null 2>&1; then
    echo "ERROR: /debug/memory endpoint not available. Is profiling wired in?"
    exit 1
fi
echo "Debug endpoint is live."

# ── Step 3: Start container monitor in background ──────────────────
echo ""
echo "=== Step 3: Starting container memory monitor ==="
python3 scripts/monitor_container.py "$CONTAINER" 2 "$RESULTS_DIR/container_memory.csv" &
MONITOR_PID=$!
echo "Monitor PID: $MONITOR_PID"

# ── Step 4: Run load test ──────────────────────────────────────────
echo ""
echo "=== Step 4: Running load test ==="
python3 scripts/load_test.py "$TOTAL" "$CONCURRENCY" "$BURST" 2>&1 | tee "$RESULTS_DIR/load_test.log"

# Move the snapshots file into results dir
mv -f memory_snapshots.json "$RESULTS_DIR/" 2>/dev/null || true

# ── Step 5: Stop monitor ──────────────────────────────────────────
echo ""
echo "=== Step 5: Stopping monitor ==="
kill "$MONITOR_PID" 2>/dev/null || true
wait "$MONITOR_PID" 2>/dev/null || true

# ── Step 6: Collect final diagnostics ─────────────────────────────
echo ""
echo "=== Step 6: Collecting final diagnostics ==="
curl -s http://localhost:8002/debug/memory | python3 -m json.tool > "$RESULTS_DIR/final_memory.json"
docker stats "$CONTAINER" --no-stream > "$RESULTS_DIR/final_docker_stats.txt" 2>/dev/null || true

echo ""
echo "============================================"
echo " Done! Results saved to: $RESULTS_DIR/"
echo "============================================"
echo ""
echo "Key files:"
echo "  $RESULTS_DIR/load_test.log           — load test output + memory summaries"
echo "  $RESULTS_DIR/memory_snapshots.json   — per-burst memory snapshots (tracemalloc + SGP spans)"
echo "  $RESULTS_DIR/container_memory.csv    — docker container memory over time"
echo "  $RESULTS_DIR/final_memory.json       — final /debug/memory dump"
echo ""
echo "Look for:"
echo "  1. sgp_processors.*.span_count growing linearly with requests"
echo "  2. RSS growing and not reclaiming after GC wait"
echo "  3. diff_vs_baseline pointing at sgp_tracing_processor.py or scale_gp_beta"
