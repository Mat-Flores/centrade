"""I2: every command goes through the platform; the engine's native interfaces are closed.
Generated configuration side, then network side (Compose and runner template)."""

import json
from pathlib import Path
from typing import Any, get_args
from uuid import uuid4

from centrade_core.engine.types import Mode
from centrade_freqtrade.config import config_file, render_config
from freqtrade_adapter.support import make_spec
from hypothesis import given
from hypothesis import strategies as st

modes = st.sampled_from(get_args(Mode))


@given(modes)
def test_i02_generated_config_disables_native_interfaces(mode: Mode) -> None:
    spec = make_spec(mode)
    values = render_config(spec).values
    doc = json.loads(config_file(spec))
    assert values["telegram.enabled"] == "false"
    assert values["webhook.allow_custom_messages"] == "false"
    assert values["webhook.enabled"] == "false"  # enabled by the receiver batch, secret URL
    assert doc["api_server"]["CORS_origins"] == []  # no browser (FreqUI)
    assert not {"username", "password", "jwt_secret_key", "ws_token"} & set(doc["api_server"])
    assert values["api_server.listen_port"] == "8080"


@given(modes)
def test_i02_manual_entry_is_forced_off(mode: Mode) -> None:
    values = render_config(make_spec(mode)).values
    assert values["force_entry_enable"] == "false"  # /forceenter refused by the engine
    assert values["position_adjustment_enable"] == "false"  # reinforcement without a closed hook
    assert values["initial_state"] == "paused"


def test_i02_engine_reaches_only_risk_and_receiver(tmp_path: Path) -> None:
    """The engine container is only on `engines` (internal), with no published port; the database,
    the bus, the API and Docker are all unreachable from it. Members of `engines`: the worker (event
    receiver); the Risk service joins it at M3."""
    import yaml  # type: ignore[import-untyped]
    from centrade_worker.runner import ContainerSpec, DockerRunner

    root = Path(__file__).resolve().parents[2] / "deploy" / "compose"
    services: dict[str, dict[str, Any]] = {}
    networks: dict[str, dict[str, Any]] = {}
    for name in ("core.yml", "engines.yml"):
        doc = yaml.safe_load((root / name).read_text(encoding="utf-8"))
        networks.update(doc["networks"])
        for svc, conf in doc["services"].items():
            merged = services.setdefault(svc, {})
            for k, v in conf.items():  # Compose-style merge for `networks`
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

    # Template: the engine is only on `centrade_engines` (project `centrade` + network `engines`).
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
