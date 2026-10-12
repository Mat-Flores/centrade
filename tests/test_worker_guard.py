"""Vérification de F9 côté worker : branches de refus et réactions (SPEC F9, I5, §13)."""

from datetime import timedelta
from typing import Any

from centrade_core.engine.contract import EngineUnreachable
from centrade_core.engine.types import InstanceRef
from centrade_worker.testing import World
from test_worker_parallele import request, status_of
from worker_support import alerts, commands, instance, spy


def failing_read(w: World, exc: Exception) -> tuple[list[int], Any]:
    """`effective_config` lève `exc` ; rend le compteur d'appels et de quoi rétablir."""
    real, reads = w.fake.effective_config, [0]

    async def effective_config(ref: InstanceRef) -> Any:
        reads[0] += 1
        raise exc

    w.fake.effective_config = effective_config  # type: ignore[method-assign]

    def restore() -> None:
        w.fake.effective_config = real  # type: ignore[method-assign]

    return reads, restore


async def test_exception_dans_la_verification_refuse_la_reprise_sans_rien_envoyer(
    migrated_url: str, redis_url: str
) -> None:
    async with World(migrated_url, redis_url) as w:
        ref = await w.new_instance()
        await w.fake.pause_entries(ref)
        await w.worker.run_once()
        calls = spy(w.fake)
        failing_read(w, RuntimeError("relecture cassée"))

        resume = await request(w, ref, "resume_entries")
        await w.worker.run_once()

        (cmd,) = await commands(w, ref.instance_id, "resume_entries")
        assert cmd.id == resume and cmd.status == "failed"
        assert cmd.result is not None
        assert [r["code"] for r in cmd.result["reasons"]] == ["error"]
        assert "RuntimeError" in cmd.result["reason"]
        assert calls == []  # rien n'est parti vers le moteur
        assert (await w.fake.status(ref)).state == "exits_only"
        (alert,) = await alerts(w, ref.instance_id, "entries_refused")
        assert (alert.status, alert.invariant) == ("open", "I5")


async def test_relecture_en_echec_n_est_pas_retenue_comme_verification_faite(
    migrated_url: str, redis_url: str
) -> None:
    async with World(migrated_url, redis_url) as w:
        ref = await w.new_instance()
        await w.worker.run_once()
        w.clock.advance(31)  # la cadence est échue
        reads, restore = failing_read(w, EngineUnreachable("muet"))

        await w.worker.run_once()
        assert reads == [1]
        await w.worker.run_once()  # sans attendre la cadence : retentée dès le tour suivant
        assert reads == [2]

        restore()
        real = w.fake.effective_config

        async def counted(r: InstanceRef) -> Any:
            reads[0] += 1
            return await real(r)

        w.fake.effective_config = counted  # type: ignore[method-assign,assignment]
        await w.worker.run_once()
        await w.worker.run_once()
        assert reads == [3]  # réussie : retenue jusqu'à la prochaine cadence
        assert (await instance(w, ref.instance_id)).effective_config_at == w.clock.now


async def test_relecture_impossible_sur_un_moteur_en_marche_alerte_et_pause_en_60_s(
    migrated_url: str, redis_url: str
) -> None:
    async with World(migrated_url, redis_url) as w:
        ref = await w.new_instance()
        await w.worker.run_once()  # dernière relecture réussie
        read_at = w.clock.now
        calls = spy(w.fake)
        _, restore = failing_read(w, EngineUnreachable("configuration illisible"))

        detected_at = None
        for _ in range(20):
            w.clock.advance(5)
            await w.worker.run_once()
            if await alerts(w, ref.instance_id, "config_unreadable"):
                detected_at = w.clock.now
                break
            assert calls == []  # avant le délai : ni alerte ni pause

        assert detected_at is not None and detected_at - read_at == timedelta(seconds=60)
        (alert,) = await alerts(w, ref.instance_id, "config_unreadable")
        assert (alert.severity, alert.status) == ("critical", "open")
        assert calls == ["pause_entries"]  # partie d'office, dans le même tour
        (pause,) = await commands(w, ref.instance_id, "pause_entries")
        assert pause.actor == "system:worker"
        assert (await w.fake.status(ref)).state == "exits_only"

        w.clock.advance(5)
        await w.worker.run_once()  # toujours illisible, en sorties seules : rien de plus
        assert len(await alerts(w, ref.instance_id, "config_unreadable")) == 1
        assert calls == ["pause_entries"]
        assert await status_of(w, pause.id) == "verified"

        restore()
        await w.worker.run_once()
        assert (await alerts(w, ref.instance_id, "config_unreadable"))[0].status == "resolved"


async def test_etat_halted_observe_alerte_et_retour_en_sorties_seules(
    migrated_url: str, redis_url: str
) -> None:
    async with World(migrated_url, redis_url) as w:
        ref = await w.new_instance()
        await w.worker.run_once()
        calls = spy(w.fake)
        w.fake._insts[ref.instance_id].state = "halted"  # jamais demandé par la plateforme

        await w.worker.run_once()
        await w.worker.run_once()  # une alerte et une commande par épisode, pas une par tour

        (alert,) = await alerts(w, ref.instance_id, "engine_halted")
        assert (alert.severity, alert.status) == ("critical", "open")
        (back,) = await commands(w, ref.instance_id, "pause_entries")
        assert back.actor == "system:worker" and back.dispatched_at is not None
        assert calls == ["pause_entries"]  # appel du contrat qui ramène en sorties seules

        w.fake._insts[ref.instance_id].state = "exits_only"
        await w.worker.run_once()
        assert (await alerts(w, ref.instance_id, "engine_halted"))[0].status == "resolved"
        assert await status_of(w, back.id) == "verified"
