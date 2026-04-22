"""
Memory profiling instrumentation for debugging memory leaks.

Adds /debug/memory and /debug/memory/reset endpoints to the FastACP app.
Uses tracemalloc for Python allocation tracking and directly inspects
the SGP tracing processor's internal _spans dict (the suspected leak).

Usage: import and call setup_profiling(app) after creating the FastACP app.
"""

import gc
import sys
import tracemalloc
from datetime import datetime

from starlette.requests import Request
from starlette.responses import JSONResponse

# Start tracemalloc with moderate depth. 10 frames is enough to identify
# the source without the massive overhead of 25 frames during import.
tracemalloc.start(10)

_baseline_snapshot = None


def _get_rss_mb() -> float:
    """Get current RSS in MB. Uses /proc on Linux (Docker), falls back to resource module."""
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024  # VmRSS is in KB
    except FileNotFoundError:
        pass
    import platform
    import resource

    rusage = resource.getrusage(resource.RUSAGE_SELF)
    if platform.system() == "Darwin":
        return rusage.ru_maxrss / (1024 * 1024)  # macOS: bytes
    return rusage.ru_maxrss / 1024  # Linux: KB


def _get_smaps_summary() -> dict:
    """Parse /proc/self/smaps_rollup for memory breakdown (Linux/Docker only).

    This shows WHERE RSS is — heap, anonymous mmap, file-backed, etc.
    Critical for finding leaks that tracemalloc can't see (C extensions, fragmentation).
    """
    try:
        result = {}
        with open("/proc/self/smaps_rollup") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    key = parts[0].rstrip(":")
                    val_kb = int(parts[1])
                    if val_kb > 0:
                        result[key] = round(val_kb / 1024, 2)  # MB
        return result
    except FileNotFoundError:
        return {}
    except Exception as e:
        return {"error": str(e)}


def _get_pymalloc_stats() -> dict:
    """Get Python memory allocator stats via sys._debugmallocstats if available."""
    import io
    import contextlib

    try:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            sys._debugmallocstats()
        raw = buf.getvalue()
        # Extract key summary lines
        result = {"raw_lines": []}
        for line in raw.split("\n"):
            line = line.strip()
            if not line:
                continue
            if any(k in line.lower() for k in ["total", "arena", "pool", "allocated", "free"]):
                result["raw_lines"].append(line)
        return result
    except Exception:
        return {}


def _get_sgp_processor_info() -> dict:
    """Inspect the global tracing processor manager for accumulated spans."""
    try:
        from agentex.lib.core.tracing.tracing_processor_manager import (
            GLOBAL_TRACING_PROCESSOR_MANAGER as mgr,
        )

        info = {}
        for i, proc in enumerate(mgr.sync_processors):
            name = type(proc).__name__
            if hasattr(proc, "_spans"):
                spans = proc._spans
                info[f"sync_{i}_{name}"] = {
                    "span_count": len(spans),
                    "dict_shallow_bytes": sys.getsizeof(spans),
                    "sample_keys": list(spans.keys())[:5],
                }
        for i, proc in enumerate(mgr.async_processors):
            name = type(proc).__name__
            if hasattr(proc, "_spans"):
                spans = proc._spans
                info[f"async_{i}_{name}"] = {
                    "span_count": len(spans),
                    "dict_shallow_bytes": sys.getsizeof(spans),
                    "sample_keys": list(spans.keys())[:5],
                }
        return info
    except Exception as e:
        return {"error": str(e)}


def _get_scale_gp_queue_info() -> dict:
    """Inspect the scale_gp_beta internal tracing queue and OpenAI processor."""
    info = {}
    # Internal span export queue (bounded at 4000)
    try:
        from scale_gp_beta.lib.tracing.trace_queue_manager import (
            _global_tracing_queue_manager,
        )

        qm = _global_tracing_queue_manager
        if qm is not None and hasattr(qm, "_queue"):
            info["export_queue"] = {
                "size": qm._queue.qsize(),
                "maxsize": qm._queue.maxsize,
            }
    except Exception as e:
        info["export_queue_error"] = str(e)

    # OpenAI tracing SGP processor (has its own _spans dict)
    try:
        from scale_gp_beta.lib.tracing.integrations.openai.openai_tracing_sgp_processor import (
            OpenAITracingSGPProcessor,
        )
        # The processor is typically registered as a global; find it via gc
        for obj in gc.get_referrers(OpenAITracingSGPProcessor):
            pass  # just checking importability
        # More directly: check if any instances exist with _spans
        import scale_gp_beta.lib.tracing.integrations.openai.openai_tracing_sgp_processor as oai_mod
        for attr_name in dir(oai_mod):
            attr = getattr(oai_mod, attr_name, None)
            if isinstance(attr, OpenAITracingSGPProcessor) and hasattr(attr, "_spans"):
                info["openai_processor_spans"] = len(attr._spans)
    except Exception:
        pass  # Not all agents use this processor

    return info


def setup_profiling(app) -> None:
    """Attach /debug/memory and /debug/memory/reset endpoints to the app."""
    global _baseline_snapshot

    @app.on_event("startup")
    async def _take_baseline():
        global _baseline_snapshot
        gc.collect()
        _baseline_snapshot = tracemalloc.take_snapshot()

    @app.get("/debug/memory")
    async def debug_memory(request: Request):
        global _baseline_snapshot
        gc.collect()
        current = tracemalloc.take_snapshot()
        traced_current, traced_peak = tracemalloc.get_traced_memory()

        # Top 20 allocations by size (current snapshot)
        top_stats = current.statistics("lineno")[:20]
        top_allocs = [
            {
                "location": str(stat.traceback),
                "size_kb": round(stat.size / 1024, 2),
                "count": stat.count,
            }
            for stat in top_stats
        ]

        # Diff vs baseline — what GREW since startup
        diff_vs_baseline = []
        if _baseline_snapshot:
            diff = current.compare_to(_baseline_snapshot, "lineno")[:20]
            diff_vs_baseline = [
                {
                    "location": str(stat.traceback),
                    "size_diff_kb": round(stat.size_diff / 1024, 2),
                    "count_diff": stat.count_diff,
                }
                for stat in diff
            ]

        # Full traceback diff — shows the CALL STACK leading to each allocation
        # This reveals WHO is calling copy.deepcopy / json.loads etc.
        diff_traceback = []
        if _baseline_snapshot:
            diff_tb = current.compare_to(_baseline_snapshot, "traceback")[:15]
            for stat in diff_tb:
                frames = []
                for frame in stat.traceback:
                    frames.append(f"{frame.filename}:{frame.lineno}")
                diff_traceback.append({
                    "frames": frames,
                    "size_diff_kb": round(stat.size_diff / 1024, 2),
                    "count_diff": stat.count_diff,
                })

        # Diff vs baseline grouped by filename (coarser view)
        diff_by_file = []
        if _baseline_snapshot:
            diff_f = current.compare_to(_baseline_snapshot, "filename")[:20]
            diff_by_file = [
                {
                    "file": str(stat.traceback),
                    "size_diff_kb": round(stat.size_diff / 1024, 2),
                    "count_diff": stat.count_diff,
                }
                for stat in diff_f
            ]

        # Check which deepcopy function span.py is using
        import scale_gp_beta.lib.tracing.span as _span_check
        _dc_fn = getattr(_span_check, "deepcopy", None) or getattr(_span_check, "deepcopy_minimal", None)
        patch_status = {
            "deepcopy_fn": str(_dc_fn),
            "module": getattr(_dc_fn, "__module__", "unknown"),
            "qualname": getattr(_dc_fn, "__qualname__", "unknown"),
        }

        return JSONResponse(
            {
                "timestamp": datetime.now().isoformat(),
                "monkey_patch": patch_status,
                "rss_mb": round(_get_rss_mb(), 2),
                "traced_current_mb": round(traced_current / (1024 * 1024), 2),
                "traced_peak_mb": round(traced_peak / (1024 * 1024), 2),
                "gc_stats": gc.get_stats(),
                "smaps": _get_smaps_summary(),
                "pymalloc": _get_pymalloc_stats(),
                "sgp_processors": _get_sgp_processor_info(),
                "scale_gp_queue": _get_scale_gp_queue_info(),
                "top_allocations": top_allocs,
                "diff_vs_baseline": diff_vs_baseline,
                "diff_traceback": diff_traceback,
                "diff_vs_baseline_by_file": diff_by_file,
            }
        )

    @app.get("/debug/memory/reset")
    async def reset_baseline(request: Request):
        """Reset the baseline snapshot to now (useful for before/after comparisons)."""
        global _baseline_snapshot
        gc.collect()
        _baseline_snapshot = tracemalloc.take_snapshot()
        return JSONResponse(
            {
                "status": "baseline_reset",
                "timestamp": datetime.now().isoformat(),
                "rss_mb": round(_get_rss_mb(), 2),
            }
        )
