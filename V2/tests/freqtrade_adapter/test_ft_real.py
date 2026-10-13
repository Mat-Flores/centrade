"""Essai réel : une instance Freqtrade en dry-run sur le Docker local, de bout en bout.

Sautée sans Docker, sans l'image épinglée (`make engines-pull`) ou sans réseau. Lancer :
`CENTRADE_TEST_VENUE=kraken uv run pytest -q -s tests/freqtrade_adapter/test_ft_real.py`
La venue ne sert qu'aux données publiques du dry-run (aucune clé) ; kraken est une valeur
d'exemple, la première joignable depuis le poste d'essai, pas une recommandation.
Le réseau d'essai est un pont ordinaire (le dry-run lit les données de la venue) : en production
le réseau `engines` est interne, avec liste blanche de sorties (M7). Rien n'est publié sur l'hôte.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import socket
import time
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import docker
import pytest
from centrade_core.engine.contract import owned_drifts
from centrade_core.engine.types import Deployment, InstanceSpec
from centrade_core.engine.verification import entry_refusals
from centrade_freqtrade.adapter import FreqtradeAdapter
from centrade_freqtrade.image import (
    ENGINE_MEMORY_BYTES,
    FREQTRADE_DIGEST,
    FREQTRADE_IMAGE,
    FREQTRADE_REF,
    FREQTRADE_TAG,
)
from centrade_worker.runner import DockerRunner
from docker.errors import DockerException, NotFound
from runner.support import DOCKER_OK

from .local_runtime import STRATEGY, LocalRuntime
from .support import make_spec, sma_manifest

pytestmark = [pytest.mark.docker, pytest.mark.network]

VENUE = os.environ.get("CENTRADE_TEST_VENUE", "kraken")


def _venue_reachable() -> bool:
    try:
        socket.create_connection((f"api.{VENUE}.com", 443), timeout=5).close()
    except OSError:
        return False
    return True


def _image_present() -> bool:
    try:
        docker.from_env(timeout=10).images.get(FREQTRADE_REF)
    except DockerException:
        return False
    return True


@pytest.fixture(scope="module", autouse=True)
def _prerequisites() -> None:
    if not DOCKER_OK:
        pytest.skip("Docker local absent")
    if not _image_present():
        pytest.skip("image du moteur absente : make engines-pull")
    if not _venue_reachable():
        pytest.skip(f"venue {VENUE} injoignable depuis ce poste")


async def until(check: Callable[[], Any], what: str, timeout_s: float, every_s: float = 2.0) -> Any:
    end = time.monotonic() + timeout_s
    while True:
        got = await check()
        if got:
            return got
        if time.monotonic() > end:
            raise AssertionError(f"délai dépassé : {what}")
        await asyncio.sleep(every_s)


@pytest.fixture
async def stack(tmp_path: Path) -> AsyncIterator[Any]:
    raw = docker.from_env(timeout=60)
    tag = secrets.token_hex(4)
    net = raw.networks.create(f"centrade-test-engines-{tag}")
    runtime_dir = tmp_path / "run-centrade"
    runtime_dir.mkdir(mode=0o755)
    runner = DockerRunner(
        "tcp://non-utilise:2375",
        client=raw,
        runtime_dir=runtime_dir,
        network=net.name,
        host_memory_mb=int(raw.info()["MemTotal"]) // 1024**2,
    )
    runtime = LocalRuntime(runtime_dir)
    iid = uuid4()

    def address(instance_id: UUID) -> str:
        c = raw.containers.get(f"centrade-engine-{instance_id}")
        c.reload()
        return f"http://{c.attrs['NetworkSettings']['Networks'][net.name]['IPAddress']}:8080"

    adapter = FreqtradeAdapter(runner, runtime, address=address)
    try:
        yield adapter, runner, runtime, raw, iid
    finally:
        try:
            raw.containers.get(f"centrade-engine-{iid}").remove(force=True)
        except NotFound:
            pass
        try:
            raw.volumes.get(f"centrade-data-{iid}").remove()
        except NotFound:
            pass
        net.remove()


async def test_dry_run_instance_starts_reports_trades_and_stops(stack: Any) -> None:
    adapter, runner, runtime, raw, iid = stack
    t0 = time.monotonic()
    log: list[str] = []

    def note(msg: str) -> None:
        line = f"[{time.monotonic() - t0:6.1f}s] {msg}"
        log.append(line)
        print(line)

    manifest = sma_manifest(stoploss="-0.05").model_copy(
        update={
            "name": "enter-every-candle",
            "entrypoint": "user_data/strategies/EnterEveryCandle.py",
            "timeframes": ("1m",),
        }
    )
    pairs = [f"crypto:{VENUE}:BTC/USDT", f"crypto:{VENUE}:ETH/USDT"]
    spec = make_spec("paper", manifest).model_copy(
        update={
            "instance_id": iid,
            "params": {"pairs": pairs},
            "deployment": Deployment(
                fingerprint="e" * 64,
                config_hash="c" * 64,
                code=STRATEGY,
                image=f"{FREQTRADE_IMAGE}:{FREQTRADE_TAG}",
                digest=FREQTRADE_DIGEST,
                engine_version=FREQTRADE_TAG,
            ),
        }
    )
    assert adapter.check_source(manifest, STRATEGY).ok
    generated = adapter.render_config(spec)

    ref = await adapter.deploy(spec)
    note("conteneur créé et démarré")
    status = await until(_reachable(adapter, ref), "API du moteur joignable", 120)
    note(f"état observé : {status.state}, mode {status.mode}")
    assert (status.state, status.mode) == ("exits_only", "paper")

    c = raw.containers.get(f"centrade-engine-{iid}")
    host = c.attrs["HostConfig"]
    assert c.attrs["Config"]["User"] == runtime.container_user()
    assert host["ReadonlyRootfs"] is True and not host["PortBindings"]
    assert host["Memory"] == ENGINE_MEMORY_BYTES and host["CapDrop"] == ["ALL"]
    assert "FREQTRADE__" not in " ".join(c.attrs["Config"]["Env"])
    ls = c.exec_run(["ls", "/data/engine"])
    assert b"trades-paper.sqlite" in ls.output, ls.output  # écrit sous /data
    assert c.exec_run(["touch", "/freqtrade/essai"]).exit_code != 0  # racine en lecture seule
    note("utilisateur, racine en lecture seule, écriture sur /data : vérifiés")

    # Vérification de F9, comme le worker la fait avant d'ouvrir les entrées.
    effective = await adapter.effective_config(ref)
    drifts = owned_drifts(generated, effective, tuple(adapter.config_drift(generated, effective)))
    refusals = entry_refusals(
        spec=spec,
        status=status,
        effective=effective,
        drifts=drifts,
        recorded_fingerprint="e" * 64,
        now=datetime.now(UTC),
        stale_after_s=30,
    )
    note(f"dérives : {[d.key for d in drifts]} ; refus : {[r.code for r in refusals]}")
    assert drifts == () and refusals == ()

    await asyncio.sleep(12)  # une bougie courte passe : en sorties seules, aucune entrée
    snap = await adapter.snapshot(ref)
    assert snap.positions == () and snap.orders == ()

    await adapter.resume_entries(ref)
    running = await until(_state(adapter, ref, "running"), "état running", 30)
    note(f"après resume_entries : {running.state}")

    events: list[Any] = []

    async def trade_visible() -> Any:
        events.extend([e async for e in adapter.events(ref)])
        s = await adapter.snapshot(ref)
        return s if s.positions else None

    snap = await until(trade_visible, "un trade rempli", 240, 3)
    # La position a pu apparaître entre le relevé des événements et l'instantané : on relit.
    events.extend([e async for e in adapter.events(ref)])
    pos = snap.positions[0]
    note(
        f"trade remonté : position {pos.position_id} {pos.symbol} qty {pos.qty} "
        f"@ {pos.entry_price}, stop {snap.stops[0].price} tenu par {snap.stops[0].held_by}, "
        f"{len(snap.orders)} ordre(s) ouvert(s), soldes {[(b.currency, str(b.total)) for b in snap.balances]}"  # noqa: E501
    )
    assert snap.stops[0].held_by == "engine" and snap.stops[0].price is not None

    await adapter.pause_entries(ref)
    paused = await until(_state(adapter, ref, "exits_only"), "état exits_only", 30)
    note(f"après pause_entries : {paused.state}")

    await adapter.close_position(ref, pos.position_id)

    async def closed_visible() -> Any:
        events.extend([e async for e in adapter.events(ref)])
        s = await adapter.snapshot(ref)
        return s.closed or None

    closed = await until(closed_visible, "un trade clos", 60, 2)
    done = closed[0]
    note(
        f"trade clos remonté : {done.position_id} cause {done.exit_cause} pnl {done.pnl} "
        f"frais {done.fees} entrée {done.entry_cause}"
    )
    assert done.position_id == pos.position_id and done.exit_cause == "manual"
    kinds = {e.type.value for e in events}
    note(f"types d'événements vus : {sorted(kinds)}")
    assert {"order.submitted", "order.filled", "position.updated", "position.closed"} <= kinds
    assert len({e.id for e in events}) == len(events)

    await adapter.flatten(ref)
    assert (await runner.inspect(iid)).status == "running"  # flatten n'arrête jamais le conteneur
    await adapter.stop(ref)
    stopped = await adapter.status(ref)
    note(f"après stop : {stopped.state}")
    assert stopped.state == "stopped"
    assert not (runtime.root / str(iid) / "credentials.json").exists()
    c.reload()
    assert c.status == "exited"
    note("fichiers d'identifiants supprimés")

    # Relance : identifiants renouvelés, sorties seules, historique du volume /data conservé.
    await adapter.start(ref)
    again = await until(_reachable(adapter, ref), "API après relance", 120)
    kept = len((await adapter.snapshot(ref)).closed)
    note(f"après start : {again.state}, trades clos conservés : {kept}")
    assert again.state == "exits_only" and (await adapter.snapshot(ref)).closed
    await adapter.stop(ref)


def _reachable(adapter: FreqtradeAdapter, ref: Any) -> Callable[[], Any]:
    async def check() -> Any:
        try:
            return await adapter.status(ref)
        except Exception:
            return None

    return check


def _state(adapter: FreqtradeAdapter, ref: Any, want: str) -> Callable[[], Any]:
    async def check() -> Any:
        s = await adapter.status(ref)
        return s if s.state == want else None

    return check


__all__ = ["InstanceSpec"]
