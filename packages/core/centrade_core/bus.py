"""Bus Redis Streams : groupe de consommateurs, acquittement explicite, reprise des non-acquittés.

Le client Redis doit être créé avec `decode_responses=True`. Les noms de stream sont des paramètres.
Livraison au moins une fois : un message non acquitté est relivré (traitement idempotent).
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
FIELD = "data"  # une seule clé : le JSON du message


@dataclass(frozen=True)
class Message:
    id: str
    data: str


class Bus:
    def __init__(self, redis: Redis, group: str, consumer: str, reclaim_idle_ms: int = 0) -> None:
        # reclaim_idle_ms=0 : un seul consommateur par groupe (le worker) reprend tout ce qui est
        # en attente. Avec plusieurs consommateurs, fixer un délai supérieur au temps de traitement.
        self._r = redis
        self._group = group
        self._consumer = consumer
        self._reclaim_idle_ms = reclaim_idle_ms

    async def publish(self, stream: str, data: str) -> str:
        return str(await self._r.xadd(stream, {FIELD: data}))

    async def ensure_group(self, stream: str) -> None:
        try:
            await self._r.xgroup_create(stream, self._group, id="0", mkstream=True)
        except ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def read(self, stream: str, count: int = 100) -> list[Message]:
        """D'abord les messages en attente (redémarrage), puis les nouveaux. Sans attente."""
        await self.ensure_group(stream)
        claimed: Any = await self._r.xautoclaim(
            stream, self._group, self._consumer, self._reclaim_idle_ms, "0-0", count=count
        )
        # [prochain id, [(id, champs)], ids supprimés] ; les entrées supprimées sont ignorées
        out = [Message(i, f[FIELD]) for i, f in claimed[1] if f]
        if len(out) < count:
            fresh: Any = await self._r.xreadgroup(
                self._group, self._consumer, {stream: ">"}, count=count - len(out)
            )
            for _name, entries in fresh or []:  # RESP2 : [[flux, [(id, champs)]]]
                out.extend(Message(i, f[FIELD]) for i, f in entries)
        return out

    async def ack(self, stream: str, *ids: str) -> None:
        if ids:
            await self._r.xack(stream, self._group, *ids)

    async def pending(self, stream: str) -> int:
        return int((await self._r.xpending(stream, self._group))["pending"])


HEARTBEAT_KEY = (
    "worker:heartbeat"  # valeur : horodatage ISO UTC ; la clé expire si le worker se tait
)

NOTIFY_CHANNEL = "notify"  # Pub/Sub : quelque chose a changé, l'API relit la base (pas d'état ici)


async def notify(redis: Redis, kind: str, ident: object) -> None:
    """Prévient les flux SSE (`instance`, `command`, `alert`). Au mieux : la base fait foi."""
    try:
        await redis.publish(NOTIFY_CHANNEL, json.dumps({"kind": kind, "id": str(ident)}))
    except Exception:
        log.warning("notification_perdue", kind=kind)  # le flux se resynchronise au prochain tour
