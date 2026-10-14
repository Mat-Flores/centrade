"""Worker-side F9 verification (SPEC F9, I3, I5, I10): re-reads what runs, decides with the
pure function of `centrade_core.engine.verification`, records, alerts, pauses.

Two uses: just before sending what increases risk (`gate`), and at every observed start
then at a fixed cadence (`check`). The worker knows no engine: the configuration comparison
comes from the adapter (`config_drift`), completed by `owned_drifts`.
No command that reduces risk waits for anything from here (I4).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

import structlog
from centrade_core.audit import SYSTEM_WORKER, write_audit
from centrade_core.commands import ACTIVE
from centrade_core.deployment import config_hash, deployment_fingerprint
from centrade_core.engine.contract import (
    CommandRejected,
    EngineAdapter,
    EngineUnreachable,
    observe_status,
    owned_drifts,
)
from centrade_core.engine.types import (
    Deployment,
    Drift,
    EffectiveConfig,
    EngineConfig,
    Exits,
    InstanceRef,
    InstanceSpec,
    InstanceStatus,
    Manifest,
    Sizing,
)
from centrade_core.engine.verification import (
    CRITICAL,
    DRIFT,
    ERROR,
    FINGERPRINT,
    FOUND,
    GATED,
    MODE,
    Refusal,
    command_refusals,
    entry_refusals,
)
from centrade_core.ids import uuid7
from centrade_core.models.trading import Alert, Command, Engine, Instance, StrategyVersion
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

log = structlog.get_logger("guard")

Note = Callable[[str, UUID], None]

# Alert rule and invariant of each observed drift.
_RULE: dict[str, tuple[str, str | None]] = {
    MODE: ("mode_mismatch", "I3"),
    DRIFT: ("config_drift", None),
    FINGERPRINT: ("fingerprint_mismatch", "I10"),
}
REFUSED_RULE = "entries_refused"
UNREADABLE_RULE = "config_unreadable"  # re-read impossible on a running engine (§13)
HALTED_RULE = "engine_halted"  # state never requested by the platform (F9)
_VERIFIABLE = ("exits_only", "running")  # states where an engine runs and can be re-read


@dataclass(frozen=True)
class Target:
    spec: InstanceSpec
    generated: EngineConfig
    recorded: str | None  # fingerprint recorded at deployment


def spec_for(
    inst: Instance, engine: Engine, version: StrategyVersion | None, adapter: EngineAdapter
) -> tuple[InstanceSpec, EngineConfig]:
    """Specification and generated configuration, from the registry. Pure for given rows.
    Without a strategy version (simulated M1 instances): default manifest, no code;
    the adapter's `check_source` decides at deployment whether an engine accepts it."""
    if version is None:
        manifest = Manifest(
            name=inst.name,
            engine=engine.kind,
            version=1,
            entrypoint="-",
            asset_classes=("crypto",),
            trading_mode="spot",
            timeframes=("5m",),
            modes=("paper",),
            sizing=Sizing(stake_amount=Decimal("50"), max_open_positions=3),
            exits=Exits(stoploss=Decimal("-0.05"), stop_on_venue=True),
        )
        code, code_hash = "", ""
        exits = manifest.exits.model_dump(mode="json")
    else:
        manifest = Manifest.model_validate(version.manifest)
        code, code_hash, exits = version.code, version.code_hash, version.exits
    if manifest.engine != engine.kind:
        raise ValueError("la version de stratégie vise un autre moteur que celui de l'instance")
    spec = InstanceSpec(
        instance_id=inst.id,
        engine=engine.kind,
        mode=inst.mode,  # validated by Pydantic: an unknown value is refused
        account_id="paper-sim" if inst.account_id is None else str(inst.account_id),
        manifest=manifest,
        params=inst.params,
    )
    generated = adapter.render_config(spec)
    chash = config_hash(generated.values, exclude=generated.mode_keys)
    deployment = Deployment(
        fingerprint=deployment_fingerprint(
            code_hash=code_hash,
            params=inst.params,
            exits=exits,
            image=engine.image,
            digest=engine.digest or "",
            config_hash=chash,
        ),
        config_hash=chash,
        code=code,
        image=engine.image,
        digest=engine.digest or "",
        engine_version=engine.version,
        memory_mb=engine.memory_reservation_mb,
        cpus=engine.cpu_reservation,
    )
    return spec.model_copy(update={"deployment": deployment}), generated


async def raise_alert(
    s: AsyncSession,
    *,
    rule: str,
    severity: str,
    message: str,
    target_id: UUID,
    target_kind: str = "instance",
    invariant: str | None = None,
    correlation_id: UUID | None = None,
) -> UUID | None:
    """One open alert per rule and per target. Returns its identifier if it is created."""
    open_id = await s.scalar(
        select(Alert.id)
        .where(Alert.rule == rule, Alert.target_id == target_id, Alert.status != "resolved")
        .limit(1)
    )
    if open_id is not None:
        return None
    alert = Alert(
        rule=rule,
        severity=severity,
        target_kind=target_kind,
        target_id=target_id,
        message=message,
        correlation_id=correlation_id,
        invariant=invariant,
    )
    s.add(alert)
    await s.flush()
    await write_audit(
        s,
        actor=SYSTEM_WORKER,
        action="alert.raised",
        target=f"alert:{alert.id}",
        after={"rule": rule, "severity": severity},
    )
    return alert.id


class Guard:
    def __init__(
        self,
        *,
        sessions: async_sessionmaker[AsyncSession],
        adapters: Mapping[str, EngineAdapter],
        clock: Callable[[], datetime],
        call_timeout_s: float,
        stale_after_s: float,
        every_s: float,
        pause_deadline_s: float,
        note: Note,
        unreadable_after_s: float = 60.0,
        pinned_digests: Mapping[str, str] | None = None,
    ) -> None:
        self._sessions = sessions
        self._adapters = adapters
        self._clock = clock
        self._call_timeout_s = call_timeout_s
        self._stale_after_s = stale_after_s
        self._every_s = every_s
        self._pause_deadline_s = pause_deadline_s
        self._note = note
        # Last verification per instance: (state, mode) observed, time, reasons.
        self._last: dict[UUID, tuple[tuple[str, str | None], datetime, tuple[Refusal, ...]]] = {}
        self._unreadable_after_s = unreadable_after_s
        # Digest announced by the registered adapter, per engine: the `engines` table is modified
        # in the database, not these constants.
        self._pinned = dict(pinned_digests or {})
        # Last successful re-read of a running engine (failing that, first attempt).
        self._read_at: dict[UUID, datetime] = {}
        self._halted: set[UUID] = set()  # `halted` episodes already reported
        # Instances whose automatic pause awaits sending (by the instance's task).
        self.pause_requested: set[UUID] = set()

    async def target(self, instance_id: UUID) -> Target:
        async with self._sessions() as s:
            inst = await s.get_one(Instance, instance_id)
            engine = await s.get_one(Engine, inst.engine_id)
            version = (
                None
                if inst.strategy_version_id is None
                else await s.get_one(StrategyVersion, inst.strategy_version_id)
            )
            spec, generated = spec_for(inst, engine, version, self._adapters[engine.kind])
            return Target(spec, generated, inst.deployment_fingerprint)

    async def deployment(self, instance_id: UUID) -> InstanceSpec:
        """At deployment: records the generated configuration hash and the fingerprint (I10),
        then returns the specification to hand to the adapter."""
        t = await self.target(instance_id)
        dep = t.spec.deployment
        assert dep is not None  # noqa: S101  # set by spec_for
        checked = self._adapters[t.spec.engine].check_source(t.spec.manifest, dep.code)
        if not checked.ok:
            raise CommandRejected("code de stratégie refusé : " + " ; ".join(checked.errors))
        pinned = self._pinned.get(t.spec.engine)
        if pinned is not None and dep.digest != pinned:
            log.error(
                "digest_changed_in_database", instance_id=str(instance_id), engine=t.spec.engine
            )
            raise CommandRejected(
                "digest de l'image en base différent de celui de l'adaptateur : déploiement refusé"
            )
        async with self._sessions.begin() as s:
            await s.execute(
                update(Instance)
                .where(Instance.id == instance_id)
                .values(
                    config_hash=dep.config_hash,
                    deployment_fingerprint=dep.fingerprint,
                    updated_at=self._clock(),
                )
            )
            await write_audit(
                s,
                actor=SYSTEM_WORKER,
                action="deployment.recorded",
                target=f"instance:{instance_id}",
                before={"deployment_fingerprint": t.recorded},
                after={"deployment_fingerprint": dep.fingerprint, "config_hash": dep.config_hash},
            )
        self._last.pop(instance_id, None)  # new deployment: new verification
        return t.spec

    async def _read(
        self, ref: InstanceRef, generated: EngineConfig
    ) -> tuple[EffectiveConfig | None, tuple[Drift, ...] | None]:
        adapter = self._adapters[ref.engine]
        try:
            async with asyncio.timeout(self._call_timeout_s):
                effective = await adapter.effective_config(ref)
        except (EngineUnreachable, TimeoutError):
            return None, None
        return effective, owned_drifts(
            generated, effective, tuple(adapter.config_drift(generated, effective))
        )

    async def _verify(
        self, ref: InstanceRef, status: InstanceStatus, correlation_id: UUID | None
    ) -> tuple[tuple[Refusal, ...], bool]:
        """Re-reads, decides, records. Returns (reasons, full re-read)."""
        t = await self.target(ref.instance_id)
        effective, drifts = await self._read(ref, t.generated)
        refusals = entry_refusals(
            spec=t.spec,
            status=status,
            effective=effective,
            drifts=drifts,
            recorded_fingerprint=t.recorded,
            now=self._clock(),
            stale_after_s=self._stale_after_s,
        )
        await self._record(ref.instance_id, status, effective, drifts, refusals, correlation_id)
        return refusals, effective is not None

    async def gate(
        self,
        command_type: str,
        ref: InstanceRef,
        mode: str,
        correlation_id: UUID | None = None,
    ) -> tuple[Refusal, ...]:
        """Reasons for refusing to send the command. Nothing is read for what reduces risk."""
        if command_type not in GATED:
            return ()
        try:
            status = entries = None
            if mode == "paper" and command_type != "deploy":
                status = await observe_status(
                    self._adapters[ref.engine], ref, self._clock, self._call_timeout_s
                )
                if command_type == "resume_entries":
                    entries, _ = await self._verify(ref, status, correlation_id)
            out = command_refusals(
                command_type,
                mode=mode,
                status=status,
                entries=entries,
                now=self._clock(),
                stale_after_s=self._stale_after_s,
            )
        except Exception as exc:  # any doubt is a refusal (I5); nothing is sent
            log.exception("verification_unavailable", instance_id=str(ref.instance_id))
            out = (Refusal(ERROR, f"Vérification impossible ({type(exc).__name__}) : refus."),)
        if out:
            async with self._sessions.begin() as s:
                alert_id = await raise_alert(
                    s,
                    rule=REFUSED_RULE,
                    severity="warning",
                    message=f"Commande {command_type} refusée : "
                    + " ".join(r.message for r in out),
                    target_id=ref.instance_id,
                    invariant="I5",
                    correlation_id=correlation_id,
                )
            if alert_id is not None:
                self._note("alert", alert_id)
        return out

    async def check(self, ref: InstanceRef, status: InstanceStatus) -> tuple[Refusal, ...] | None:
        """At every observed start (first snapshot, state or mode change), then every
        `every_s` seconds. Returns the last known reasons; None if nothing runs."""
        iid = ref.instance_id
        now = self._clock()
        if status.state == "halted":
            await self._on_halted(iid, now)
        else:
            self._halted.discard(iid)
        if status.state not in _VERIFIABLE:
            self._last.pop(iid, None)  # the next observed start will be re-verified
            self._read_at.pop(iid, None)
            return None
        sig = (status.state, status.mode)
        last = self._last.get(iid)
        if last and last[0] == sig and abs((now - last[1]).total_seconds()) < self._every_s:
            return last[2]
        self._read_at.setdefault(iid, now)
        try:
            refusals, complete = await self._verify(ref, status, None)
        except Exception:
            await self._on_unreadable(iid, status, now)
            raise
        if complete:
            self._last[iid] = (sig, now, refusals)
            self._read_at[iid] = now
        else:  # new attempt next round; past the delay, alert and pause
            await self._on_unreadable(iid, status, now)
        return refusals

    async def _on_unreadable(self, iid: UUID, status: InstanceStatus, now: datetime) -> None:
        """Entries open on a configuration that can no longer be re-read since
        `unreadable_after_s`: we no longer know what runs (§13, I5). Critical alert and pause."""
        since = self._read_at.get(iid, now)
        if status.state != "running" or (now - since).total_seconds() < self._unreadable_after_s:
            return
        async with self._sessions.begin() as s:
            alert_id = await raise_alert(
                s,
                rule=UNREADABLE_RULE,
                severity="critical",
                message="La configuration effective d'un moteur en marche n'a pas pu être relue "
                f"depuis {int(self._unreadable_after_s)} s : entrées mises en pause.",
                target_id=iid,
                invariant="I5",
            )
            await self._pause(s, iid, ["unreadable"], None, now)
        if alert_id is not None:
            self._note("alert", alert_id)

    async def _on_halted(self, iid: UUID, now: datetime) -> None:
        """F9: `halted` observed => alert and return to exits-only. Once per episode: if
        the engine does not leave it, the command expires and its alert says so, with no retry loop.
        `pause_entries` is the contract call that puts an engine back in exits-only without
        verifying or waiting for anything (I4); `start` increases risk, held on doubt."""
        if iid in self._halted:
            return
        async with self._sessions.begin() as s:
            alert_id = await raise_alert(
                s,
                rule=HALTED_RULE,
                severity="critical",
                message="Moteur observé `halted` : sa boucle de trading est arrêtée, les "
                "positions ne sont plus gérées. Retour en sorties seules demandé.",
                target_id=iid,
            )
            await self._pause(s, iid, ["halted"], None, now)
        self._halted.add(iid)
        if alert_id is not None:
            self._note("alert", alert_id)

    async def _record(
        self,
        instance_id: UUID,
        status: InstanceStatus,
        effective: EffectiveConfig | None,
        drifts: tuple[Drift, ...] | None,
        refusals: tuple[Refusal, ...],
        correlation_id: UUID | None,
    ) -> None:
        codes = {r.code for r in refusals}
        found = [r for r in refusals if r.code in FOUND]
        # An alert resolves only if the matching check actually took place.
        cleared = [c for c in (DRIFT, FINGERPRINT) if effective is not None and c not in codes]
        if status.mode is not None and MODE not in codes:
            cleared.append(MODE)
        rules = [_RULE[c][0] for c in cleared]
        if effective is not None:
            rules.append(UNREADABLE_RULE)
        if status.state in _VERIFIABLE:
            rules.append(HALTED_RULE)
        if not refusals:  # verification passes again: the previous refusal is lifted
            rules.append(REFUSED_RULE)
        now = self._clock()
        async with self._sessions.begin() as s:
            if effective is not None:  # the instance row first, the audit after
                await s.execute(
                    update(Instance)
                    .where(Instance.id == instance_id)
                    .values(
                        effective_config={
                            **effective.values,
                            # read by the API for "What is actually running"
                            **(
                                {"engine_version": effective.engine_version}
                                if effective.engine_version
                                else {}
                            ),
                        },
                        effective_config_at=effective.observed_at,
                        drift=[d.model_dump() for d in drifts or ()],
                    )
                )
            for r in found:
                rule, invariant = _RULE[r.code]
                alert_id = await raise_alert(
                    s,
                    rule=rule,
                    severity="critical" if r.code in CRITICAL else "warning",
                    message=r.message,
                    target_id=instance_id,
                    invariant=invariant,
                    correlation_id=correlation_id,
                )
                if alert_id is not None:
                    self._note("alert", alert_id)
            resolved = (
                await s.scalars(
                    update(Alert)
                    .where(
                        Alert.rule.in_(rules),
                        Alert.target_id == instance_id,
                        Alert.status != "resolved",
                    )
                    .values(status="resolved", resolved_at=func.now())
                    .returning(Alert.id)
                )
            ).all()
            for alert_id in resolved:
                await write_audit(
                    s,
                    actor=SYSTEM_WORKER,
                    action="alert.resolved",
                    target=f"alert:{alert_id}",
                    before={"status": "open"},
                    after={"status": "resolved"},
                )
                self._note("alert", alert_id)
            if found and status.state == "running":
                await self._pause(s, instance_id, sorted(codes & FOUND), correlation_id, now)
        self._note("instance", instance_id)
        if refusals:
            log.warning(
                "f9_verification_rejected",
                instance_id=str(instance_id),
                codes=sorted(codes),
                observed_state=status.state,
                observed_mode=status.mode,
            )

    async def _pause(
        self,
        s: AsyncSession,
        instance_id: UUID,
        codes: list[str],
        correlation_id: UUID | None,
        now: datetime,
    ) -> None:
        """Entries open while verification fails: `pause_entries`, through the normal command
        cycle (traced, verified, expired). Only one pending at a time."""
        pending = await s.scalar(
            select(Command.id)
            .where(
                Command.instance_id == instance_id,
                Command.type == "pause_entries",
                Command.status.in_(ACTIVE),
            )
            .limit(1)
        )
        if pending is not None:
            return
        cmd = Command(
            id=uuid7(),
            instance_id=instance_id,
            type="pause_entries",
            actor=SYSTEM_WORKER,
            idempotency_key=f"auto-pause:{uuid7()}",
            status="requested",
            correlation_id=correlation_id or uuid7(),
            requested_at=now,
            deadline_at=now + timedelta(seconds=self._pause_deadline_s),
            updated_at=now,
        )
        s.add(cmd)
        await s.flush()
        await write_audit(
            s,
            actor=SYSTEM_WORKER,
            action="auto.pause_entries",
            target=f"instance:{instance_id}",
            after={"command_id": str(cmd.id), "reasons": codes},
        )
        self._note("command", cmd.id)
        self.pause_requested.add(instance_id)
        log.warning("automatic_pause", instance_id=str(instance_id), codes=codes)
