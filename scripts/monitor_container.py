#!/usr/bin/env python3
"""
Monitor Docker container memory usage over time.

Polls `docker stats` at a fixed interval and writes to a CSV file.
Run alongside the load test to get the container-level view.

Usage:
    python scripts/monitor_container.py [container_name] [interval_seconds] [output_file]
    python scripts/monitor_container.py rocket-agentex-demo-langchain-chat-agent-1 2 container_memory.csv
"""

import csv
import json
import subprocess
import sys
import time
from datetime import datetime


def get_container_stats(container: str) -> dict:
    result = subprocess.run(
        ["docker", "stats", container, "--no-stream", "--format", "{{json .}}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return {"error": result.stderr.strip()}
    try:
        return json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        return {"error": f"bad json: {result.stdout.strip()}"}


def main():
    container = sys.argv[1] if len(sys.argv) > 1 else "rocket-agentex-demo-langchain-chat-agent-1"
    interval = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    output = sys.argv[3] if len(sys.argv) > 3 else "container_memory.csv"

    print(f"Monitoring container: {container}")
    print(f"Interval: {interval}s")
    print(f"Output: {output}")
    print("Press Ctrl+C to stop\n")

    with open(output, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "container", "mem_usage", "mem_percent", "cpu_percent", "net_io", "pids"])

        try:
            while True:
                stats = get_container_stats(container)
                if "error" in stats:
                    print(f"[{datetime.now().isoformat()}] Error: {stats['error']}")
                    time.sleep(interval)
                    continue

                ts = datetime.now().isoformat()
                row = [
                    ts,
                    stats.get("Name", container),
                    stats.get("MemUsage", ""),
                    stats.get("MemPerc", ""),
                    stats.get("CPUPerc", ""),
                    stats.get("NetIO", ""),
                    stats.get("PIDs", ""),
                ]
                writer.writerow(row)
                f.flush()

                print(f"[{ts}] MEM: {stats.get('MemUsage', 'N/A')} ({stats.get('MemPerc', 'N/A')})")
                time.sleep(interval)
        except KeyboardInterrupt:
            print(f"\nStopped. Data saved to {output}")


if __name__ == "__main__":
    main()
