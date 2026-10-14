"""Measures the memory and CPU of N Freqtrade instances in dry-run on the local Docker.

    uv run python scripts/measure-capacity.py --count 3 --venue kraken

Statistics are read on the host (direct Docker, outside the socket proxy). Everything the script
creates (containers, volumes, network, folder) is removed at the end, even on failure. Ordinary
test network: the dry-run reads the venue's public data (no key). The venue is
an example value, not a recommendation.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import statistics
import sys
import tempfile
import time
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
for sub in ("packages/core", "packages/adapters/freqtrade", "apps/worker", "tests"):
    sys.path.insert(0, str(ROOT / sub))

import docker  # noqa: E402
from centrade_core.engine.types import Deployment  # noqa: E402
from centrade_freqtrade.adapter import FreqtradeAdapter  # noqa: E402
from centrade_freqtrade.image import (  # noqa: E402
    ENGINE_MEMORY_BYTES,
    ENGINE_NANO_CPUS,
    FREQTRADE_DIGEST,
    FREQTRADE_IMAGE,
    FREQTRADE_TAG,
)
from centrade_worker.runner import DockerRunner  # noqa: E402
from docker.errors import NotFound  # noqa: E402
from freqtrade_adapter.local_runtime import STRATEGY, LocalRuntime  # noqa: E402
from freqtrade_adapter.support import make_spec, sma_manifest  # noqa: E402

MIB = 1024**2


def cpu_percent(s: dict) -> float:
    cpu, pre = s["cpu_stats"], s["precpu_stats"]
    d_cpu = cpu["cpu_usage"]["total_usage"] - pre["cpu_usage"]["total_usage"]
    d_sys = cpu.get("system_cpu_usage", 0) - pre.get("system_cpu_usage", 0)
    return 0.0 if d_sys <= 0 else 100.0 * d_cpu / d_sys * cpu.get("online_cpus", 1)


def mem_mib(s: dict) -> float:
    m = s["memory_stats"]
    return (m["usage"] - m.get("stats", {}).get("inactive_file", 0)) / MIB


async def main(count: int, venue: str, settle_s: int, samples: int) -> None:
    raw = docker.from_env(timeout=60)
    tag = secrets.token_hex(4)
    net = raw.networks.create(f"centrade-capacity-{tag}")
    iids: list[UUID] = []
    with tempfile.TemporaryDirectory(prefix="centrade-capacity-") as tmp:
        root = Path(tmp)
        root.chmod(0o755)  # noqa: ASYNC240
        runner = DockerRunner(
            "tcp://unused:2375",
            client=raw,
            runtime_dir=root,
            network=net.name,
            host_memory_mb=int(raw.info()["MemTotal"]) // MIB,
        )
        adapter = FreqtradeAdapter(
            runner,
            LocalRuntime(root),
            address=lambda i: (
                "http://"
                + raw.containers.get(f"centrade-engine-{i}").attrs["NetworkSettings"]["Networks"][
                    net.name
                ]["IPAddress"]
                + ":8080"
            ),
        )
        manifest = sma_manifest().model_copy(
            update={
                "entrypoint": "user_data/strategies/EnterEveryCandle.py",
                "timeframes": ("1m",),
            }
        )
        dep = Deployment(
            fingerprint="e" * 64,
            config_hash="c" * 64,
            code=STRATEGY,
            image=f"{FREQTRADE_IMAGE}:{FREQTRADE_TAG}",
            digest=FREQTRADE_DIGEST,
            engine_version=FREQTRADE_TAG,
        )
        try:
            refs = []
            for _ in range(count):
                iid = uuid4()
                iids.append(iid)
                spec = make_spec("paper", manifest).model_copy(
                    update={
                        "instance_id": iid,
                        "params": {
                            "pairs": [f"crypto:{venue}:BTC/USDT", f"crypto:{venue}:ETH/USDT"]
                        },
                        "deployment": dep,
                    }
                )
                refs.append(await adapter.deploy(spec))
            for ref in refs:
                for _ in range(90):
                    try:
                        await adapter.status(ref)
                        break
                    except Exception:
                        await asyncio.sleep(2)
                await adapter.resume_entries(ref)
            print(f"{count} instances en marche, stabilisation {settle_s} s", flush=True)
            await asyncio.sleep(settle_s)
            per: dict[str, list[tuple[float, float]]] = {str(i): [] for i in iids}
            for _ in range(samples):
                for i in iids:
                    st = raw.containers.get(f"centrade-engine-{i}").stats(stream=False)
                    per[str(i)].append((mem_mib(st), cpu_percent(st)))
                await asyncio.sleep(5)
            info = raw.info()
            out = {
                "host": {"cpus": info["NCPU"], "memory_mib": info["MemTotal"] // MIB},
                "reservation": {
                    "memory_mib": ENGINE_MEMORY_BYTES // MIB,
                    "cpu": ENGINE_NANO_CPUS / 1e9,
                },
                "instances": {
                    k: {
                        "memory_mib_avg": round(statistics.mean(m for m, _ in v), 1),
                        "memory_mib_max": round(max(m for m, _ in v), 1),
                        "cpu_pct_avg": round(statistics.mean(c for _, c in v), 1),
                        "cpu_pct_max": round(max(c for _, c in v), 1),
                    }
                    for k, v in per.items()
                },
            }
            print(json.dumps(out, indent=2))
        finally:
            for i in iids:
                try:
                    raw.containers.get(f"centrade-engine-{i}").remove(force=True)
                except NotFound:
                    pass
                try:
                    raw.volumes.get(f"centrade-data-{i}").remove()
                except NotFound:
                    pass
            net.remove()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=3)
    ap.add_argument("--venue", default="kraken")
    ap.add_argument("--settle", type=int, default=90)
    ap.add_argument("--samples", type=int, default=6)
    a = ap.parse_args()
    t0 = time.monotonic()
    asyncio.run(main(a.count, a.venue, a.settle, a.samples))
    print(f"durée {time.monotonic() - t0:.0f} s")
