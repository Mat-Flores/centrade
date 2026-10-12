"""Vérification de F9 côté worker (SPEC F9, I3, I5, I10) : relit ce qui tourne, décide avec la
fonction pure de `centrade_core.engine.verification`, enregistre, alerte, met en pause.

Deux usages : juste avant d'envoyer ce qui augmente le risque (`gate`), et à chaque démarrage
observé puis à cadence fixe (`check`). Le worker ne connaît aucun moteur : la comparaison de
configuration vient de l'adaptateur (`config_drift`), complétée par `owned_drifts`.
Aucune commande qui réduit le risque n'attend quoi que ce soit d'ici (I4).
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

# Règle d'alerte et invariant de chaque écart constaté.
_RULE: dict[str, tuple[str, str | None]] = {
    MODE: ("mode_mismatch", "I3"),
    DRIFT: ("config_drift", None),
    FINGERPRINT: ("fingerprint_mismatch", "I10"),
}
REFUSED_RULE = "entries_refused"
_VERIFIABLE = ("exits_only", "running")  # états où un moteur tourne et peut être relu


@dataclass(frozen=True)
class Target:
    spec: InstanceSpec
    generated: EngineConfig
    recorded: str | None  # empreinte enregistrée au déploiement


def spec_for(
    inst: Instance, engine: Engine, version: StrategyVersion | None, adapter: EngineAdapter
) -> tuple[InstanceSpec, EngineConfig]:
    """Spécification et configuration générée, depuis le registre. Pure pour des lignes données.
    Sans version de stratégie (instances simulées de M1) : manifest par défaut, aucun code ;
    `check_source` de l'adaptateur décide au déploiement si un moteur l'accepte."""
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
        mode=inst.mode,  # validé par Pydantic : une valeur inconnue est refusée
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
    """Une seule alerte ouverte par règle et par cible. Rend son identifiant si elle est créée."""
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
    ) -> None:
        self._sessions = sessions
        self._adapters = adapters
        self._clock = clock
        self._call_timeout_s = call_timeout_s
        self._stale_after_s = stale_after_s
        self._every_s = every_s
        self._pause_deadline_s = pause_deadline_s
        self._note = note
        # Dernière vérification par instance : (état, mode) observés, heure, motifs.
        self._last: dict[UUID, tuple[tuple[str, str | None], datetime, tuple[Refusal, ...]]] = {}
        self.pause_requested = False  # une pause automatique attend son envoi

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
        """Au déploiement : enregistre le hash de la configuration générée et l'empreinte (I10),
        puis rend la spécification à remettre à l'adaptateur."""
        t = await self.target(instance_id)
        dep = t.spec.deployment
        assert dep is not None  # noqa: S101  # posé par spec_for
        checked = self._adapters[t.spec.engine].check_source(t.spec.manifest, dep.code)
        if not checked.ok:
            raise CommandRejected("code de stratégie refusé : " + " ; ".join(checked.errors))
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
        self._last.pop(instance_id, None)  # nouveau déploiement : nouvelle vérification
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
        """Relit, décide, enregistre. Rend (motifs, relecture complète)."""
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
        """Motifs de refus d'envoyer la commande. Rien n'est lu pour ce qui réduit le risque."""
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
        except Exception as exc:  # tout doute vaut refus (I5) ; rien n'est envoyé
            log.exception("verification_impossible", instance_id=str(ref.instance_id))
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
        """À chaque démarrage observé (premier relevé, changement d'état ou de mode), puis toutes
        les `every_s` secondes. Rend les derniers motifs connus ; None si rien ne tourne."""
        iid = ref.instance_id
        if status.state not in _VERIFIABLE:
            self._last.pop(iid, None)  # le prochain démarrage observé sera revérifié
            return None
        now, sig = self._clock(), (status.state, status.mode)
        last = self._last.get(iid)
        if last and last[0] == sig and abs((now - last[1]).total_seconds()) < self._every_s:
            return last[2]
        refusals, complete = await self._verify(ref, status, None)
        if complete:  # sinon : nouvelle tentative au tour suivant
            self._last[iid] = (sig, now, refusals)
        return refusals

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
        # Une alerte ne se résout que si le contrôle correspondant a réellement eu lieu.
        cleared = [c for c in (DRIFT, FINGERPRINT) if effective is not None and c not in codes]
        if status.mode is not None and MODE not in codes:
            cleared.append(MODE)
        rules = [_RULE[c][0] for c in cleared]
        if not refusals:  # la vérification passe de nouveau : le refus précédent est levé
            rules.append(REFUSED_RULE)
        now = self._clock()
        async with self._sessions.begin() as s:
            if effective is not None:  # la ligne d'instance d'abord, l'audit ensuite
                await s.execute(
                    update(Instance)
                    .where(Instance.id == instance_id)
                    .values(
                        effective_config=effective.values,
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
                "verification_f9_refus",
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
        """Entrées ouvertes alors que la vérification échoue : `pause_entries`, par le cycle
        normal des commandes (tracée, vérifiée, expirée). Une seule en attente à la fois."""
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
        self.pause_requested = True
        log.warning("pause_automatique", instance_id=str(instance_id), codes=codes)
