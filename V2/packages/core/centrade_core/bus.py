"""Redis Streams bus: consumer group, explicit acknowledgement, recovery of unacknowledged messages.

The Redis client must be created with `decode_responses=True`. Stream names are parameters.
At-least-once delivery: an unacknowledged message is redelivered (idempotent processing).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import structlog
from redis.asyncio import Redis
from redis.exceptions import ResponseError

log = structlog.get_logger("bus")

EVENTS_STREAM = "events"
FIELD = "data"  # a single key: the message JSON


@dataclass(frozen=True)
class Message:
    id: str
    data: str


class Bus:
    def __init__(self, redis: Redis, group: str, consumer: str) -> None:
        self._r = redis
        self._group = group
        self._consumer = consumer

    async def publish(self, stream: str, data: str) -> str:
        return str(await self._r.xadd(stream, {FIELD: data}))

    async def ensure_group(self, stream: str) -> None:
        try:
            await self._r.xgroup_create(stream, self._group, id="0", mkstream=True)
        except ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def read(self, stream: str, count: int = 100) -> list[Message]:
        """Pending messages first (restart), then new ones. No waiting."""
        await self.ensure_group(stream)
        # Zero idle delay: the group's only consumer (the worker) takes back everything
        # pending. shortcut: with several consumers, a delay greater than the processing
        # time becomes necessary.
        claimed: Any = await self._r.xautoclaim(
            stream, self._group, self._consumer, 0, "0-0", count=count
        )
        # [next id, [(id, fields)], deleted ids]; deleted entries are ignored
        out = [Message(i, f[FIELD]) for i, f in claimed[1] if f]
        if len(out) < count:
            fresh: Any = await self._r.xreadgroup(
                self._group, self._consumer, {stream: ">"}, count=count - len(out)
            )
            for _name, entries in fresh or []:  # RESP2: [[stream, [(id, fields)]]]
                out.extend(Message(i, f[FIELD]) for i, f in entries)
        return out

    async def ack(self, stream: str, *ids: str) -> None:
        if ids:
            await self._r.xack(stream, self._group, *ids)


HEARTBEAT_KEY = (
    "worker:heartbeat"  # value: ISO UTC timestamp; the key expires if the worker goes quiet
)

NOTIFY_CHANNEL = "notify"  # Pub/Sub: something changed, the API re-reads the database (no state)


async def notify(redis: Redis, kind: str, ident: object) -> None:
    """Notifies the SSE streams (`instance`, `command`, `alert`, `order`, `position`, `trade`).
    Best effort: the database is authoritative."""
    try:
        await redis.publish(NOTIFY_CHANNEL, json.dumps({"kind": kind, "id": str(ident)}))
    except Exception:
        log.warning("notification_lost", kind=kind)  # the stream resynchronises at the next round
