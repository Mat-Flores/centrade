"""I2 : toute commande passe par la plateforme ; les interfaces natives du moteur sont fermées.
Côté configuration générée, puis côté réseau (Compose et gabarit du runner)."""

import json
import sys
from pathlib import Path
from typing import get_args
from uuid import uuid4

from centrade_core.engine.types import Mode
from hypothesis import given
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "adapters" / "freqtrade"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from centrade_freqtrade.config import config_file, render_config
from freqtrade_adapter.support import make_spec

modes = st.sampled_from(get_args(Mode))


@given(modes)
def test_i02_config_generee_desactive_interfaces_natives(mode: Mode) -> None:
    spec = make_spec(mode)
    values = render_config(spec).values
    doc = json.loads(config_file(spec))
    assert values["telegram.enabled"] == "false"
    assert values["webhook.allow_custom_messages"] == "false"
    assert values["webhook.enabled"] == "false"  # activé par le lot du récepteur, URL secrète
    assert doc["api_server"]["CORS_origins"] == []  # aucun navigateur (FreqUI)
    assert not {"username", "password", "jwt_secret_key", "ws_token"} & set(doc["api_server"])
    assert values["api_server.listen_port"] == "8080"


@given(modes)
def test_i02_entree_manuelle_forcee_desactivee(mode: Mode) -> None:
    values = render_config(make_spec(mode)).values
    assert values["force_entry_enable"] == "false"  # /forceenter refusé par le moteur
    assert values["position_adjustment_enable"] == "false"  # renfort sans hook fermé
    assert values["initial_state"] == "paused"


def test_i02_moteur_ne_joint_que_risk_et_recepteur(tmp_path: Path) -> None:
    """Le conteneur de moteur n'est que sur `engines` (interne), sans port publié ; ni la base,
    ni le bus, ni l'API, ni Docker n'y sont joignables. Membres de `engines` : le worker (récepteur
    d'événements) ; le Risk service s'y ajoute à M3."""
    import yaml
    from centrade_worker.runner import ContainerSpec, DockerRunner

    root = Path(__file__).resolve().parents[2] / "deploy" / "compose"
    services: dict[str, dict[str, object]] = {}
    networks: dict[str, dict[str, object]] = {}
    for name in ("core.yml", "engines.yml"):
        doc = yaml.safe_load((root / name).read_text(encoding="utf-8"))
        networks.update(doc["networks"])
        for svc, conf in doc["services"].items():
            merged = services.setdefault(svc, {})
            for k, v in conf.items():  # fusion à la manière de Compose pour `networks`
                merged[k] = (
                    sorted({*merged.get(k, []), *v}) if k == "networks" and k in merged else v
                )

    def members(net: str) -> set[str]:
        return {s for s, c in services.items() if net in c.get("networks", [])}

    assert networks["engines"]["internal"] is True and networks["docker"]["internal"] is True
    assert members("engines") == {"worker"}
    assert members("docker") == {"worker", "docker-socket-proxy"}
    assert not members("engines") & {"postgres", "redis", "api", "caddy", "web"}
    assert not any(
        "ports" in c for n, c in services.items() if n in members("engines") | members("docker")
    )

    # Gabarit : le moteur n'est que sur `centrade_engines` (projet `centrade` + réseau `engines`).
    iid = uuid4()
    (tmp_path / str(iid)).mkdir()
    spec = ContainerSpec(
        instance_id=iid,
        image="x/y:1",
        digest="sha256:" + "a" * 64,
        command=("run",),
        files_dir=tmp_path / str(iid),
        mode="paper",
        fingerprint="f" * 64,
        memory_bytes=1,
        nano_cpus=1,
    )
    kw = DockerRunner(runtime_dir=tmp_path, client=object())._template(spec)
    assert kw["network_mode"] == "centrade_engines"
    assert not {"ports", "publish_all_ports", "links", "extra_hosts", "dns"} & set(kw)
    assert kw["network_mode"] not in {f"centrade_{n}" for n in ("data", "app", "edge", "docker")}
