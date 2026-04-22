#!/usr/bin/env python3
"""
Load test for the langchain chat agent.

Supports two modes:
  burst:     Send bursts of N requests with full concurrency (original mode)
  sustained: Send requests at a fixed rate (e.g., 3 req/s) to match real traffic

Usage:
    # Sustained 3 req/s for 2000 requests, sample memory every 100 requests
    python scripts/load_test.py --mode sustained --rate 3 --total 2000 --sample-every 100

    # Burst mode (original): 500 requests, 10 concurrent, bursts of 50
    python scripts/load_test.py --mode burst --total 500 --concurrency 10 --burst 50
"""

import argparse
import asyncio
import json
import time
import uuid

import aiohttp

AGENT_URL = "http://localhost:8002"
ACP_ENDPOINT = f"{AGENT_URL}/api"
MEMORY_ENDPOINT = f"{AGENT_URL}/debug/memory"
MEMORY_RESET_ENDPOINT = f"{AGENT_URL}/debug/memory/reset"

# ~4KB system prompt to simulate realistic agent workloads.
# The customer's sales agent has a large prompt that gets stored in each span's input.
LARGE_SYSTEM_PROMPT = """You are a senior sales consultant AI agent for Acme Corp. You help customers
with product selection, pricing, technical questions, and order management.

## Product Catalog
- Enterprise Suite ($50,000/yr): Full platform access, 100 seats, priority support, SLA 99.99%
- Professional Plan ($15,000/yr): Core features, 25 seats, standard support, SLA 99.9%
- Starter Plan ($3,000/yr): Basic features, 5 seats, community support, SLA 99.5%

## Pricing Rules
1. Volume discounts: 10% off for 3+ year commitments, 15% off for 5+ year commitments
2. Bundle discounts: 20% off when combining Enterprise Suite with Professional Services
3. Academic/nonprofit: 30% discount on all plans with valid verification
4. Competitive displacement: Up to 25% discount when switching from a named competitor
5. End-of-quarter deals: Additional 10% available in last 2 weeks of fiscal quarter

## Objection Handling Playbook
- "Too expensive": Emphasize ROI, offer payment plans, suggest starting with Professional
- "We use competitor X": Acknowledge strengths, highlight our differentiators, offer migration assistance
- "Need to think about it": Create urgency with time-limited offers, offer extended trial
- "Missing feature Y": Check roadmap, offer workaround, escalate to product team if critical
- "Security concerns": Reference SOC2 Type II, ISO 27001, GDPR compliance, offer security review call

## Conversation Guidelines
- Always be professional, helpful, and consultative
- Never pressure customers aggressively
- Document all pricing discussions for compliance
- Escalate to human sales rep for deals over $200,000
- Follow up within 24 hours on all open opportunities
- Track customer sentiment and buying signals throughout the conversation
- Use the customer's name and reference their specific use case
- Provide concrete examples and case studies when relevant
- Always confirm understanding before proceeding to next steps
""".strip()

VARIED_QUESTIONS = [
    "What's the difference between Enterprise and Professional plans?",
    "Can I get a discount if we commit for 3 years?",
    "We're currently using Competitor X, what makes your product better?",
    "What security certifications do you have?",
    "Can you walk me through the pricing for 50 seats?",
    "We're a nonprofit, do you offer special pricing?",
    "What's your uptime SLA for the Enterprise tier?",
    "I need to integrate with Salesforce, is that supported?",
    "Can we start with Professional and upgrade later?",
    "What kind of support response times do you guarantee?",
    "We had issues with onboarding at our last vendor. How do you handle that?",
    "Is there an API for automated provisioning?",
    "What does the migration process look like from our current system?",
    "Can you send me a proposal for our team of 75 people?",
    "What's the total cost of ownership over 5 years?",
    "Do you offer a proof of concept or trial period?",
]


def make_payload(task_id: str, message: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "method": "message/send",
        "id": 1,
        "params": {
            "agent": {
                "id": "load-test-agent",
                "acp_type": "sync",
                "created_at": "2024-01-01T00:00:00Z",
                "description": "load test agent",
                "name": "langchain-chat-agent-example",
                "updated_at": "2024-01-01T00:00:00Z",
            },
            "task": {"id": task_id},
            "content": {
                "type": "text",
                "author": "user",
                "content": message,
            },
            "stream": False,
        },
    }


async def send_request(session: aiohttp.ClientSession, request_num: int) -> dict:
    task_id = f"load-test-{uuid.uuid4().hex[:12]}"
    question = VARIED_QUESTIONS[request_num % len(VARIED_QUESTIONS)]
    # Random nonce in the prompt to bust any LLM cache
    nonce = uuid.uuid4().hex
    full_message = f"{LARGE_SYSTEM_PROMPT}\n\n[session_id: {nonce}]\n\nUser question: {question}"
    payload = make_payload(task_id, full_message)
    start = time.monotonic()
    try:
        async with session.post(ACP_ENDPOINT, json=payload) as resp:
            await resp.text()
            elapsed = time.monotonic() - start
            return {"status": resp.status, "elapsed": round(elapsed, 2), "request_num": request_num, "error": None}
    except Exception as e:
        elapsed = time.monotonic() - start
        return {"status": 0, "elapsed": round(elapsed, 2), "request_num": request_num, "error": str(e)}


async def get_memory(session: aiohttp.ClientSession) -> dict:
    try:
        async with session.get(MEMORY_ENDPOINT) as resp:
            return await resp.json()
    except Exception as e:
        return {"error": str(e)}


async def reset_baseline(session: aiohttp.ClientSession) -> dict:
    try:
        async with session.get(MEMORY_RESET_ENDPOINT) as resp:
            return await resp.json()
    except Exception as e:
        return {"error": str(e)}


def print_memory_summary(mem: dict, label: str = "") -> None:
    if label:
        print(f"  [{label}]")
    rss = mem.get("rss_mb", "N/A")
    traced = mem.get("traced_current_mb", "N/A")
    print(f"  RSS: {rss} MB | Traced: {traced} MB")

    # smaps breakdown (the key new data)
    smaps = mem.get("smaps", {})
    if smaps and "Anonymous" in smaps:
        print(f"  smaps: Anon={smaps.get('Anonymous','?')} MB, Shared={smaps.get('Shared_Clean',0)+smaps.get('Shared_Dirty',0):.1f} MB, Private={smaps.get('Private_Clean',0)+smaps.get('Private_Dirty',0):.1f} MB")

    sgp = mem.get("sgp_processors", {})
    for name, info in sgp.items():
        if isinstance(info, dict) and "span_count" in info:
            print(f"  {name}: {info['span_count']} spans")

    queue_info = mem.get("scale_gp_queue", {})
    eq = queue_info.get("export_queue", {})
    if eq:
        print(f"  Export queue: {eq.get('size', '?')}/{eq.get('maxsize', '?')}")

    # pymalloc arena stats (shows fragmentation)
    pymalloc = mem.get("pymalloc", {})
    arena_lines = [l for l in pymalloc.get("raw_lines", []) if "arena" in l.lower() or "total" in l.lower()]
    for line in arena_lines[:3]:
        print(f"  pymalloc: {line}")

    diff = mem.get("diff_vs_baseline", [])[:5]
    if diff:
        print("  Top growers vs baseline:")
        for d in diff:
            print(f"    {d['location']}: +{d['size_diff_kb']} KB ({d['count_diff']:+d} objs)")


def print_final_summary(baseline: dict, final: dict, total_sent: int, total_ok: int, total_err: int, duration_s: float):
    print(f"\n{'='*70}")
    print(f"RESULTS SUMMARY")
    print(f"{'='*70}")
    print(f"Total requests: {total_sent}  |  OK: {total_ok}  |  Errors: {total_err}")
    print(f"Duration: {duration_s:.0f}s  |  Effective rate: {total_sent/duration_s:.1f} req/s")

    b_rss = baseline.get("rss_mb", 0)
    f_rss = final.get("rss_mb", 0)
    print(f"\nRSS:    {b_rss} MB -> {f_rss} MB  (delta: {f_rss - b_rss:+.2f} MB)")
    if total_sent > 0:
        print(f"  Per-request: {(f_rss - b_rss) / total_sent * 1024:.1f} KB/request")
        print(f"  Projected at 21600 req (2h @ 3/s): {b_rss + (f_rss - b_rss) / total_sent * 21600:.0f} MB")

    b_traced = baseline.get("traced_current_mb", 0)
    f_traced = final.get("traced_current_mb", 0)
    print(f"Traced: {b_traced} MB -> {f_traced} MB  (delta: {f_traced - b_traced:+.2f} MB)")

    # smaps comparison
    b_smaps = baseline.get("smaps", {})
    f_smaps = final.get("smaps", {})
    for key in ["Anonymous", "Rss", "Private_Dirty", "Private_Clean"]:
        bv = b_smaps.get(key, 0)
        fv = f_smaps.get(key, 0)
        if bv or fv:
            print(f"  smaps {key}: {bv} -> {fv} MB (delta: {fv - bv:+.2f} MB)")

    b_sgp = baseline.get("sgp_processors", {})
    f_sgp = final.get("sgp_processors", {})
    for key in f_sgp:
        if isinstance(f_sgp[key], dict) and "span_count" in f_sgp[key]:
            b_count = b_sgp.get(key, {}).get("span_count", 0) if isinstance(b_sgp.get(key), dict) else 0
            f_count = f_sgp[key]["span_count"]
            print(f"\n  {key}: {b_count} -> {f_count} spans (delta: {f_count - b_count})")


# ── Sustained mode: fixed request rate ─────────────────────────────
async def run_sustained(total: int, rate: float, sample_every: int):
    """Send requests at a fixed rate, sampling memory periodically."""
    interval = 1.0 / rate
    connector = aiohttp.TCPConnector(limit=100)
    timeout = aiohttp.ClientTimeout(total=600)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        print("=== RESETTING BASELINE ===")
        await reset_baseline(session)
        baseline = await get_memory(session)
        print("\n=== BASELINE ===")
        print_memory_summary(baseline)

        snapshots = [{"phase": "baseline", "requests_sent": 0, **baseline}]
        pending = set()
        results = []
        sent = 0
        ok = 0
        err = 0
        test_start = time.monotonic()

        async def fire_and_collect(req_num):
            nonlocal ok, err
            r = await send_request(session, req_num)
            results.append(r)
            if r["error"]:
                err += 1
            else:
                ok += 1

        while sent < total:
            loop_start = time.monotonic()

            # Launch one request
            task = asyncio.create_task(fire_and_collect(sent))
            pending.add(task)
            task.add_done_callback(pending.discard)
            sent += 1

            # Sample memory at intervals
            if sent % sample_every == 0:
                elapsed = time.monotonic() - test_start
                print(f"\n=== {sent}/{total} requests sent ({elapsed:.0f}s elapsed, {ok} ok, {err} err) ===")
                mem = await get_memory(session)
                snapshots.append({"phase": f"sample_{sent}", "requests_sent": sent, "elapsed_s": round(elapsed, 1), **mem})
                print_memory_summary(mem, f"after {sent} requests")

            # Throttle to target rate
            sleep_time = interval - (time.monotonic() - loop_start)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

        # Wait for all in-flight requests
        if pending:
            print(f"\nWaiting for {len(pending)} in-flight requests...")
            await asyncio.gather(*pending, return_exceptions=True)

        duration = time.monotonic() - test_start

        # Post-test GC wait
        print("\n=== WAITING 30s FOR GC ===")
        await asyncio.sleep(30)
        final = await get_memory(session)
        snapshots.append({"phase": "post_gc_wait", "requests_sent": sent, **final})
        print_memory_summary(final, "after 30s GC wait")

        # Save
        with open("memory_snapshots.json", "w") as f:
            json.dump(snapshots, f, indent=2, default=str)

        print_final_summary(baseline, final, sent, ok, err, duration)
        print(f"\nSnapshots saved to memory_snapshots.json")


# ── Burst mode (original) ──────────────────────────────────────────
async def run_burst(total: int, concurrency: int, burst_size: int):
    connector = aiohttp.TCPConnector(limit=concurrency)
    timeout = aiohttp.ClientTimeout(total=600)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        print("=== RESETTING BASELINE ===")
        await reset_baseline(session)
        baseline = await get_memory(session)
        print("\n=== BASELINE ===")
        print_memory_summary(baseline)

        snapshots = [{"phase": "baseline", "requests_sent": 0, **baseline}]
        all_results = []
        sent = 0
        burst_num = 0
        test_start = time.monotonic()

        while sent < total:
            burst_num += 1
            batch = min(burst_size, total - sent)
            print(f"\n=== BURST {burst_num}: {batch} requests (concurrency={concurrency}) ===")

            tasks = [send_request(session, sent + i) for i in range(batch)]
            batch_results = await asyncio.gather(*tasks)
            all_results.extend(batch_results)
            sent += batch

            successes = sum(1 for r in batch_results if r["status"] == 200)
            errors = sum(1 for r in batch_results if r["error"])
            avg_time = sum(r["elapsed"] for r in batch_results) / len(batch_results)
            print(f"  {successes}/{batch} ok, {errors} errors, avg latency: {avg_time:.2f}s")

            mem = await get_memory(session)
            snapshots.append({"phase": f"burst_{burst_num}", "requests_sent": sent, **mem})
            print_memory_summary(mem, f"after {sent} requests")

        duration = time.monotonic() - test_start

        print("\n=== WAITING 30s FOR GC ===")
        await asyncio.sleep(30)
        final = await get_memory(session)
        snapshots.append({"phase": "post_gc_wait", "requests_sent": sent, **final})
        print_memory_summary(final, "after 30s GC wait")

        with open("memory_snapshots.json", "w") as f:
            json.dump(snapshots, f, indent=2, default=str)

        total_ok = sum(1 for r in all_results if r["status"] == 200)
        total_err = sum(1 for r in all_results if r["error"])
        print_final_summary(baseline, final, sent, total_ok, total_err, duration)
        print(f"\nSnapshots saved to memory_snapshots.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Memory leak load test")
    parser.add_argument("--mode", choices=["burst", "sustained"], default="sustained")
    parser.add_argument("--total", type=int, default=2000, help="Total requests to send")
    parser.add_argument("--rate", type=float, default=3.0, help="Sustained mode: requests per second")
    parser.add_argument("--sample-every", type=int, default=100, help="Sustained mode: sample memory every N requests")
    parser.add_argument("--concurrency", type=int, default=10, help="Burst mode: max concurrent requests")
    parser.add_argument("--burst", type=int, default=50, help="Burst mode: requests per burst")
    args = parser.parse_args()

    print(f"Target: {ACP_ENDPOINT}")
    print(f"Mode:   {args.mode}")
    if args.mode == "sustained":
        print(f"Rate:   {args.rate} req/s | Total: {args.total} | Sample every: {args.sample_every}")
        asyncio.run(run_sustained(args.total, args.rate, args.sample_every))
    else:
        print(f"Total: {args.total} | Concurrency: {args.concurrency} | Burst: {args.burst}")
        asyncio.run(run_burst(args.total, args.concurrency, args.burst))
