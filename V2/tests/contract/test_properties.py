"""Propriétés (Hypothesis) : enveloppe canonique et FakeEngine."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from itertools import pairwise
from uuid import UUID

import pytest
from centrade_core.engine.types import InstanceRef
from centrade_core.events import CanonicalEvent, EventType, OrderPayload
from centrade_fake.engine import Failure, FakeEngine
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from .contract_support import make_id_factory, make_spec

decimals = st.decimals(
    min_value=Decimal("-1e9"),
    max_value=Decimal("1e9"),
    places=8,
    allow_nan=False,
    allow_infinity=False,
)
uuids = st.builds(UUID, int=st.integers(min_value=0, max_value=2**128 - 1))
times = st.datetimes(timezones=st.just(UTC))


@given(
    qty=decimals,
    price=decimals,
    fee=st.none() | decimals,
    eid=uuids,
    iid=uuids,
    seq=st.integers(min_value=1, max_value=2**40),
    ts=times,
)
def test_envelope_roundtrip_keeps_decimals(
    qty: Decimal, price: Decimal, fee: Decimal | None, eid: UUID, iid: UUID, seq: int, ts: datetime
) -> None:
    ev = CanonicalEvent(
        id=eid,
        ts=ts,
        seq=seq,
        type=EventType.ORDER_FILLED,
        engine="fake",
        instance_id=iid,
        payload=OrderPayload(
            client_order_id=eid,
            intent="exit",
            symbol="crypto:fake:BTC/USDT",
            side="sell",
            qty=qty,
            price=price,
            fee=fee,
            currency="USDT",
        ),
    )
    raw = ev.model_dump_json()
    assert CanonicalEvent.model_validate_json(raw) == ev
    body = json.loads(raw)["payload"]
    assert body["qty"] == str(qty) and isinstance(body["price"], str)


def test_float_is_refused() -> None:
    with pytest.raises(ValidationError):
        OrderPayload(
            client_order_id=UUID(int=1),
            intent="entry",
            symbol="crypto:fake:BTC/USDT",
            side="buy",
            qty=0.1,
            price=Decimal(1),
            currency="USDT",
        )


def test_bad_symbol_is_refused() -> None:
    with pytest.raises(ValidationError):
        OrderPayload(
            client_order_id=UUID(int=1),
            intent="entry",
            symbol="BTCUSDT",
            side="buy",
            qty=Decimal(1),
            price=Decimal(1),
            currency="USDT",
        )


ops = st.lists(st.sampled_from(["step", "step", "step", "pause", "resume", "flatten"]), max_size=60)


async def _run(seed: int, script: list[str], failures: tuple[Failure, ...]):  # type: ignore[no-untyped-def]
    eng = FakeEngine(
        clock=lambda: datetime(2026, 10, 10, tzinfo=UTC), seed=seed, new_id=make_id_factory()
    )
    ref: InstanceRef = await eng.deploy(make_spec())
    for f in failures:
        eng.set_failure(ref, f)
    seqs: list[int] = []
    for op in script:
        if op == "step":
            eng.step(ref)
        else:
            await {
                "pause": eng.pause_entries,
                "resume": eng.resume_entries,
                "flatten": eng.flatten,
            }[op](ref)
        seqs += [e.seq async for e in eng.events(ref)]
    return seqs, await eng.snapshot(ref)


@given(seed=st.integers(0, 10_000), script=ops)
@settings(max_examples=60, deadline=None)
def test_clean_sequences_strictly_increase(seed: int, script: list[str]) -> None:
    seqs, _ = asyncio.run(_run(seed, script, ()))
    assert all(a < b for a, b in pairwise(seqs))


@given(
    seed=st.integers(0, 10_000),
    script=ops,
    failures=st.sets(
        st.sampled_from([Failure.DUPLICATE, Failure.OUT_OF_ORDER, Failure.DROP]), min_size=1
    ).map(tuple),
)
@settings(max_examples=60, deadline=None)
def test_snapshot_stays_the_truth_under_stream_faults(
    seed: int, script: list[str], failures: tuple[Failure, ...]
) -> None:
    """Les pannes de flux ne touchent que les événements : instantané == moteur sain."""
    _, faulty = asyncio.run(_run(seed, script, failures))
    _, clean = asyncio.run(_run(seed, script, ()))
    assert faulty == clean
