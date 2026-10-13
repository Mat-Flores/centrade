"""Runner Docker, unitaires : client Docker doublé (le gabarit, les refus, l'admission)."""

import io
import tarfile
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from centrade_core.engine.contract import CommandRejected, EngineUnreachable
from centrade_worker.runner import (
    ENV_ALLOWED,
    LABEL_FINGERPRINT,
    LABEL_INSTANCE,
    LABEL_MODE,
    ContainerSpec,
    DockerRunner,
)
from docker.errors import APIError, ImageNotFound, NotFound

DIGEST = "sha256:" + "ab" * 32
GIB = 1024**3


class FakeContainer:
    def __init__(self, kwargs: dict[str, Any], status: str = "created") -> None:
        self.id = "c" * 12
        self.attrs: dict[str, Any] = {
            "State": {"Status": status, "StartedAt": "0001-01-01T00:00:00Z"},
            "Config": {"Labels": kwargs["labels"]},
            "HostConfig": {"Memory": kwargs["mem_limit"]},
        }
        self.calls: list[str] = []
        self.archives: list[tuple[str, bytes]] = []

    def reload(self) -> None: ...

    def put_archive(self, path: str, data: bytes) -> bool:
        self.archives.append((path, data))
        return True

    def start(self) -> None:
        self.calls.append("start")
        self.attrs["State"]["Status"] = "running"

    def stop(self, timeout: int) -> None:
        self.calls.append("stop")
        self.attrs["State"]["Status"] = "exited"

    def remove(self, v: bool) -> None:
        self.calls.append("remove")


class FakeClient:
    def __init__(self, mem_total: int | None = 8 * GIB) -> None:
        self.mem_total = mem_total
        self.by_name: dict[str, FakeContainer] = {}
        self.created: list[tuple[str, dict[str, Any]]] = []
        self.missing_image = False
        self.containers = self

    def info(self) -> dict[str, Any]:
        if self.mem_total is None:
            raise APIError("forbidden", response=None, explanation="proxy")
        return {"MemTotal": self.mem_total}

    def create(self, image: str, **kwargs: Any) -> FakeContainer:
        if self.missing_image:
            raise ImageNotFound("No such image")
        self.created.append((image, kwargs))
        c = FakeContainer(kwargs)
        self.by_name[kwargs["name"]] = c
        return c

    def get(self, name: str) -> FakeContainer:
        if name not in self.by_name:
            raise NotFound("absent")
        return self.by_name[name]

    def list(self, all: bool, filters: dict[str, str]) -> list[FakeContainer]:
        return list(self.by_name.values())


@pytest.fixture
def client() -> FakeClient:
    return FakeClient()


@pytest.fixture
def runner(client: FakeClient, tmp_path: Path) -> DockerRunner:
    return DockerRunner(runtime_dir=tmp_path, network="engines", client=client)


@pytest.fixture
def spec(tmp_path: Path) -> ContainerSpec:
    iid = uuid4()
    (tmp_path / str(iid)).mkdir()
    return ContainerSpec(
        instance_id=iid,
        image="freqtradeorg/freqtrade:2026.9",
        digest=DIGEST,
        command=("trade", "--config", "/run/centrade/config.json"),
        files_dir=tmp_path / str(iid),
        mode="paper",
        fingerprint="f" * 64,
        memory_bytes=GIB,
        nano_cpus=500_000_000,
        env={"TZ": "UTC"},
    )


async def make(runner: DockerRunner, client: FakeClient, spec: ContainerSpec) -> dict[str, Any]:
    await runner.create(spec)
    return client.created[-1][1]


async def test_gabarit_durcissement_complet(
    runner: DockerRunner, client: FakeClient, spec: ContainerSpec
) -> None:
    kw = await make(runner, client, spec)
    assert client.created[-1][0] == f"{spec.image}@{DIGEST}"
    assert kw["user"] == "1000:1000"
    assert kw["read_only"] is True
    assert kw["tmpfs"].keys() == {"/tmp"}  # noqa: S108
    assert kw["cap_drop"] == ["ALL"]
    assert kw["security_opt"] == ["no-new-privileges:true"]
    assert kw["privileged"] is False
    assert kw["mem_limit"] == GIB and kw["memswap_limit"] == GIB
    assert kw["nano_cpus"] == 500_000_000
    assert kw["pids_limit"] == 256
    assert kw["restart_policy"] == {"Name": "on-failure", "MaximumRetryCount": 3}
    assert kw["network_mode"] == "engines"
    assert "ports" not in kw and "publish_all_ports" not in kw
    assert kw["environment"] == {"TZ": "UTC"}
    assert kw["labels"] == {
        LABEL_INSTANCE: str(spec.instance_id),
        LABEL_FINGERPRINT: "f" * 64,
        LABEL_MODE: "paper",
    }


async def test_dossier_du_moteur_cree_au_nom_de_l_utilisateur_du_conteneur(
    runner: DockerRunner, client: FakeClient, spec: ContainerSpec
) -> None:
    await runner.create(replace(spec, user="10001:10002"))
    path, data = client.by_name[f"centrade-engine-{spec.instance_id}"].archives[0]
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        (entry,) = tar.getmembers()
    assert path == "/data" and entry.name == "engine" and entry.isdir()
    assert (entry.uid, entry.gid, entry.mode) == (10001, 10002, 0o700)


async def test_gabarit_deux_montages_seulement(
    runner: DockerRunner, client: FakeClient, spec: ContainerSpec
) -> None:
    mounts = (await make(runner, client, spec))["mounts"]
    assert len(mounts) == 2
    data, files = mounts
    assert data["Type"] == "volume" and data["ReadOnly"] is False
    assert data["Source"] == f"centrade-data-{spec.instance_id}"
    assert files["Type"] == "bind" and files["ReadOnly"] is True
    assert files["Source"] == str(spec.files_dir) and files["Target"] == "/run/centrade"


@pytest.mark.parametrize("name", ["API_KEY", "FREQTRADE__EXCHANGE__SECRET", "PATH", ""])
async def test_variable_hors_liste_blanche_refusee(
    runner: DockerRunner, spec: ContainerSpec, name: str
) -> None:
    assert name not in ENV_ALLOWED
    with pytest.raises(CommandRejected, match="variables"):
        await runner.create(replace(spec, env={name: "TEST-SECRET-DO-NOT-USE"}))


@pytest.mark.parametrize(
    "where", ["/", "/var/run/docker.sock", "/etc", "autre-instance", "traversee"]
)
async def test_montage_hors_des_deux_autorises_refuse(
    runner: DockerRunner, client: FakeClient, spec: ContainerSpec, tmp_path: Path, where: str
) -> None:
    other = tmp_path / "autre"
    other.mkdir()
    paths = {
        "autre-instance": other,
        "traversee": tmp_path / str(spec.instance_id) / ".." / "autre",
    }
    with pytest.raises(CommandRejected, match="sous-dossier"):
        await runner.create(replace(spec, files_dir=paths.get(where, Path(where))))
    assert client.created == []


async def test_sous_dossier_absent_refuse(runner: DockerRunner, spec: ContainerSpec) -> None:
    spec.files_dir.rmdir()  # Docker créerait un dossier root : on refuse
    with pytest.raises(CommandRejected):
        await runner.create(spec)


@pytest.mark.parametrize("digest", ["", "latest", "sha256:abc", "sha256:" + "AB" * 32])
async def test_digest_mal_forme_refuse(
    runner: DockerRunner, spec: ContainerSpec, digest: str
) -> None:
    with pytest.raises(CommandRejected):
        await runner.create(replace(spec, digest=digest))


@pytest.mark.parametrize("image", ["", "x@sha256:" + "a" * 64, "UPPER/x", "-x"])
async def test_image_mal_formee_refusee(
    runner: DockerRunner, spec: ContainerSpec, image: str
) -> None:
    with pytest.raises(CommandRejected):
        await runner.create(replace(spec, image=image))


async def test_digest_different_refuse_sans_telechargement(
    runner: DockerRunner, client: FakeClient, spec: ContainerSpec
) -> None:
    client.missing_image = True  # le démon ne retrouve pas ce digest localement
    with pytest.raises(CommandRejected, match="aucun téléchargement"):
        await runner.create(spec)


@pytest.mark.parametrize("user", ["root", "0:0", "0:1000", "1000:0", "1000", "ftuser:ftuser", ""])
async def test_utilisateur_ou_groupe_root_ou_nom_refuse(
    runner: DockerRunner, spec: ContainerSpec, user: str
) -> None:
    with pytest.raises(CommandRejected, match="utilisateur"):
        await runner.create(replace(spec, user=user))


@pytest.mark.parametrize("field", ["memory_bytes", "nano_cpus"])
async def test_plafond_nul_refuse(runner: DockerRunner, spec: ContainerSpec, field: str) -> None:
    with pytest.raises(CommandRejected, match="plafonds"):
        over: dict[str, Any] = {field: 0}
        await runner.create(replace(spec, **over))


async def test_admission_refusee_au_dela_de_la_memoire(
    runner: DockerRunner, client: FakeClient, spec: ContainerSpec, tmp_path: Path
) -> None:
    client.mem_total = 2 * GIB
    await runner.create(spec)  # 1 Gio sur 2
    iid = uuid4()
    (tmp_path / str(iid)).mkdir()
    await runner.create(replace(spec, instance_id=iid, files_dir=tmp_path / str(iid)))  # 2 sur 2
    iid3 = uuid4()
    (tmp_path / str(iid3)).mkdir()
    with pytest.raises(CommandRejected, match="insuffisante"):
        await runner.create(replace(spec, instance_id=iid3, files_dir=tmp_path / str(iid3)))
    assert len(client.created) == 2


async def test_admission_ignore_les_conteneurs_arretes(
    runner: DockerRunner, client: FakeClient, spec: ContainerSpec, tmp_path: Path
) -> None:
    client.mem_total = GIB
    await runner.create(spec)
    await runner.start(spec.instance_id)
    await runner.stop(spec.instance_id)
    iid = uuid4()
    (tmp_path / str(iid)).mkdir()
    await runner.create(replace(spec, instance_id=iid, files_dir=tmp_path / str(iid)))


async def test_admission_refusee_si_memoire_illisible(
    client: FakeClient, spec: ContainerSpec, tmp_path: Path
) -> None:
    client.mem_total = None
    with pytest.raises(CommandRejected, match="illisible"):
        await DockerRunner(runtime_dir=tmp_path, client=client).create(spec)


async def test_admission_utilise_le_parametre_si_info_interdit(
    client: FakeClient, spec: ContainerSpec, tmp_path: Path
) -> None:
    client.mem_total = None
    ok = DockerRunner(runtime_dir=tmp_path, host_memory_mb=2048, client=client)
    await ok.create(spec)
    small = DockerRunner(runtime_dir=tmp_path, host_memory_mb=512, client=FakeClient(None))
    with pytest.raises(CommandRejected, match="insuffisante"):
        await small.create(spec)


async def test_start_et_stop_idempotents(
    runner: DockerRunner, client: FakeClient, spec: ContainerSpec
) -> None:
    await runner.create(spec)
    first = await runner.start(spec.instance_id)
    again = await runner.start(spec.instance_id)
    assert first.status == again.status == "running"
    await runner.stop(spec.instance_id)
    await runner.stop(spec.instance_id)
    await runner.stop(uuid4())  # absent : pas d'erreur


async def test_start_conteneur_absent_refuse(runner: DockerRunner) -> None:
    with pytest.raises(CommandRejected):
        await runner.start(uuid4())


async def test_adopt_rend_les_conteneurs_en_marche_sans_les_toucher(
    runner: DockerRunner, client: FakeClient, spec: ContainerSpec
) -> None:
    await runner.create(spec)
    assert await runner.adopt() == []  # créé, pas en marche
    await runner.start(spec.instance_id)
    c = client.by_name[f"centrade-engine-{spec.instance_id}"]
    c.calls.clear()
    (found,) = await runner.adopt()
    assert found.instance_id == spec.instance_id and found.mode == "paper"
    assert c.calls == []  # ni start, ni stop, ni remove


async def test_remove_seulement_sur_demande(
    runner: DockerRunner, client: FakeClient, spec: ContainerSpec
) -> None:
    await runner.create(spec)
    await runner.adopt()
    await runner.list()
    c = client.by_name[f"centrade-engine-{spec.instance_id}"]
    assert "remove" not in c.calls
    await runner.remove(spec.instance_id)
    assert c.calls == ["remove"]
    await runner.remove(uuid4())  # absent : pas d'erreur


async def test_erreurs_docker_traduites(
    runner: DockerRunner,
    client: FakeClient,
    spec: ContainerSpec,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Resp:
        def __init__(self, code: int) -> None:
            self.status_code = code
            self.reason = "x"
            self.url = "http://proxy"
            self.content = b""

    def boom(code: int) -> Any:
        def f(*a: Any, **k: Any) -> None:
            raise APIError("x", response=Resp(code))  # type: ignore[arg-type]  # doublure de réponse

        return f

    monkeypatch.setattr(client, "create", boom(403))
    with pytest.raises(CommandRejected):
        await runner.create(spec)
    monkeypatch.setattr(client, "create", boom(500))
    with pytest.raises(EngineUnreachable):
        await runner.create(spec)


def test_socket_brut_refuse(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="socket proxy"):
        DockerRunner("unix:///var/run/docker.sock", runtime_dir=tmp_path)
    with pytest.raises(ValueError):
        DockerRunner("", runtime_dir=tmp_path)
