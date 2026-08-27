"""Reproducible MORICE latency benchmark for the local production pipeline.

The default run is read-only: it reuses an already-running llama server, sends
short model prompts, exercises only the deterministic router, and prints JSON.
Use --restart-server explicitly when a true cold-load measurement is desired.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(len(ordered) - 1, lower + 1)
    blend = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * blend


def classify(milliseconds: float) -> str:
    if milliseconds < 500:
        return "EXCELLENT"
    if milliseconds < 1_000:
        return "GOOD"
    if milliseconds < 2_000:
        return "ACCEPTABLE"
    if milliseconds < 4_000:
        return "SLOW"
    return "CRITICAL"


def hardware_snapshot() -> dict[str, object]:
    values: dict[str, object] = {
        "logicalCpuCount": os.cpu_count() or 1,
    }
    try:
        import ctypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memoryLoad", ctypes.c_ulong),
                ("totalPhysical", ctypes.c_ulonglong),
                ("availablePhysical", ctypes.c_ulonglong),
                ("totalPageFile", ctypes.c_ulonglong),
                ("availablePageFile", ctypes.c_ulonglong),
                ("totalVirtual", ctypes.c_ulonglong),
                ("availableVirtual", ctypes.c_ulonglong),
                ("availableExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            values["ramTotalMb"] = round(status.totalPhysical / 1024 / 1024, 1)
            values["ramAvailableMb"] = round(
                status.availablePhysical / 1024 / 1024, 1
            )
    except (AttributeError, OSError, TypeError, ValueError):
        pass
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
            creationflags=(
                getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            ),
        )
        name, utilization, used, total = [
            item.strip() for item in completed.stdout.splitlines()[0].split(",")
        ]
        values.update(
            {
                "gpu": name,
                "gpuPercent": float(utilization),
                "vramUsedMb": float(used),
                "vramTotalMb": float(total),
            }
        )
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        pass
    return values


def benchmark_router(runs: int) -> dict[str, object]:
    from morice.pc_control import FastActionRouter

    router = FastActionRouter()
    phrases = (
        "Open Calculator.",
        "Pause.",
        "Resume.",
        "Next.",
        "Volume 30%.",
        "What's my RAM usage?",
        "What's using my GPU?",
    )
    samples: list[float] = []
    model_invocations = 0
    for index in range(max(1, runs)):
        started = time.perf_counter()
        decision = router.route(phrases[index % len(phrases)])
        samples.append((time.perf_counter() - started) * 1_000)
        model_invocations += decision.model_invocations
    p50 = percentile(samples, 0.50)
    p95 = percentile(samples, 0.95)
    return {
        "runs": len(samples),
        "p50Ms": round(p50, 3),
        "p95Ms": round(p95, 3),
        "maxMs": round(max(samples), 3),
        "classification": classify(p95),
        "modelInvocations": model_invocations,
    }


def benchmark_model(gguf: str, runs: int) -> dict[str, object]:
    from morice.llm_client import stream_chat

    rows: list[dict[str, float]] = []
    for _ in range(max(1, runs)):
        cancel = threading.Event()
        started = time.perf_counter()
        first_at: float | None = None
        characters = 0
        for delta in stream_chat(
            [],
            "Give one direct sentence explaining why streaming reduces latency.",
            gguf_path=gguf,
            timeout=60,
            cancel_event=cancel,
            max_tokens=96,
        ):
            now = time.perf_counter()
            if first_at is None:
                first_at = now
            characters += len(str(delta or ""))
        finished = time.perf_counter()
        ttft_ms = ((first_at or finished) - started) * 1_000
        total_seconds = max(0.001, finished - started)
        rows.append(
            {
                "ttftMs": ttft_ms,
                "totalMs": (finished - started) * 1_000,
                # This is deliberately end-to-end visible throughput. The
                # OpenAI-compatible stream can hide reasoning tokens, so a
                # decode-only rate inferred from visible deltas would be fake.
                "estimatedEndToEndVisibleTokensPerSecond": (
                    (characters / 4.0) / total_seconds
                ),
            }
        )
    ttft = [row["ttftMs"] for row in rows]
    speeds = [row["estimatedEndToEndVisibleTokensPerSecond"] for row in rows]
    return {
        "runs": rows,
        "warmTtftP50Ms": round(percentile(ttft, 0.50), 1),
        "warmTtftP95Ms": round(percentile(ttft, 0.95), 1),
        "endToEndVisibleTokensPerSecondMedian": round(
            statistics.median(speeds), 2
        ),
        "classification": classify(percentile(ttft, 0.50)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gguf", default=os.getenv("MORICE_GGUF_PATH", ""))
    parser.add_argument("--model-runs", type=int, default=5)
    parser.add_argument("--router-runs", type=int, default=5_000)
    parser.add_argument(
        "--restart-server",
        action="store_true",
        help="Stop MORICE's managed server before measuring cold load.",
    )
    args = parser.parse_args()
    gguf = str(Path(args.gguf).expanduser().resolve()) if args.gguf else ""
    if not gguf or not Path(gguf).is_file():
        parser.error("--gguf must point to an existing GGUF model")
    os.environ["MORICE_GGUF_PATH"] = gguf
    os.environ.setdefault("MORICE_REUSE_LLAMA_SERVER", "1")

    reset_model_runtime = None
    try:
        cold_load_ms: float | None = None
        if args.restart_server:
            from morice.llm_client import prewarm_local_model, reset_model_runtime

            reset_model_runtime()
            started = time.perf_counter()
            prewarm_local_model(gguf)
            cold_load_ms = (time.perf_counter() - started) * 1_000

        report = {
            "createdAt": time.time(),
            "configuration": {
                "gguf": gguf,
                "ctx": os.getenv("MORICE_CTX", "8192"),
                "batch": os.getenv("MORICE_BATCH", "256"),
                "ubatch": os.getenv("MORICE_UBATCH_SIZE", "128"),
                "threads": os.getenv(
                    "MORICE_THREADS", str(max(2, (os.cpu_count() or 4) // 2))
                ),
                "batchThreads": os.getenv(
                    "MORICE_BATCH_THREADS",
                    str(max(8, max(2, (os.cpu_count() or 4) // 2))),
                ),
                "flashAttention": os.getenv("MORICE_FLASH_ATTN", "auto"),
            },
            "coldModelLoadMs": (
                round(cold_load_ms, 1) if cold_load_ms is not None else None
            ),
            "router": benchmark_router(args.router_runs),
            "model": benchmark_model(gguf, args.model_runs),
            "hardware": hardware_snapshot(),
        }
        print(json.dumps(report, indent=2))
    finally:
        # A cold benchmark owns the server it starts. Do not leave a detached
        # benchmark process on MORICE's normal inference port.
        if args.restart_server and reset_model_runtime is not None:
            reset_model_runtime()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
