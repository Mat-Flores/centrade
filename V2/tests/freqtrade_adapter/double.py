# ruff: noqa: E501
"""Double of Freqtrade's REST API (shapes recorded on tag 2026.9, ADR 0008), of its runner
and of the worker's runtime. Nothing leaves the process: an in-memory `requests` transport."""

from __future__ import annotations

import base64
import io
import json
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import requests
from centrade_core.engine.types import Deployment, InstanceSpec
from centrade_freqtrade import adapter as ft
from centrade_freqtrade import config as ftconfig
from centrade_worker.runner import RunnerContainer
from pydantic import SecretStr
from requests.adapters import HTTPAdapter

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
BASE = "http://engine.test"
STRATEGY_CODE = "from control_plane import ControlPlaneStrategy\n"


def _dump(body: Any) -> str:
    # Decimals come out as exact JSON numbers, like the text the engine writes.
    text = json.dumps(body, default=lambda d: f"__D:{d}__")
    return re.sub(r'"__D:([^"]+)__"', r"\1", text)


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


class FakeRuntime:
    """In-memory InstanceRuntime: keeps what the adapter wrote."""

    def __init__(self) -> None:
        self.issued: dict[UUID, dict[str, str]] = {}
        self.files: dict[UUID, dict[str, str]] = {}
        self.credentials_file: dict[UUID, dict[str, Any]] = {}
        self.cleaned: list[UUID] = []
        self._n = 0

    def container_user(self) -> str:
        return "1000:1000"

    async def issue_credentials(
        self, instance_id: UUID, names: tuple[str, ...]
    ) -> dict[str, SecretStr]:
        self._n += 1
        self.issued[instance_id] = {n: f"{n}-{self._n}-" + "x" * 40 for n in names}
        return {k: SecretStr(v) for k, v in self.issued[instance_id].items()}

    async def credentials(self, instance_id: UUID) -> dict[str, SecretStr]:
        if instance_id not in self.issued:
            raise LookupError
        return {k: SecretStr(v) for k, v in self.issued[instance_id].items()}

    async def write_files(self, instance_id: UUID, files: Any, credentials: Any) -> Path:
        self.files.setdefault(instance_id, {}).update(files)
        self.credentials_file[instance_id] = dict(credentials)
        return Path(f"/run/centrade/{instance_id}")

    async def cleanup(self, instance_id: UUID) -> None:
        self.credentials_file.pop(instance_id, None)
        self.cleaned.append(instance_id)


class FakeRunner:
    def __init__(self, server: FakeFreqtrade) -> None:
        self.server = server
        self.created: dict[UUID, Any] = {}
        self.status: dict[UUID, str] = {}
        self.log: list[str] = []

    async def create(self, spec: Any) -> None:
        self.log.append("create")
        self.created[spec.instance_id] = spec
        self.status[spec.instance_id] = "created"

    async def start(self, instance_id: UUID) -> None:
        self.log.append("start")
        if self.status[instance_id] != "running":
            self.server.boot()  # new process: re-reads `initial_state`
        self.status[instance_id] = "running"

    async def stop(self, instance_id: UUID, timeout_s: int = 30) -> None:
        self.log.append("stop")
        self.status[instance_id] = "exited"

    async def inspect(self, instance_id: UUID) -> RunnerContainer | None:
        spec = self.created.get(instance_id)
        if spec is None:
            return None
        return RunnerContainer(
            container_id="c1",
            instance_id=instance_id,
            status=self.status[instance_id],
            started_at="t",
            fingerprint=spec.fingerprint,
            mode=spec.mode,
        )


def _order(
    n: int, side: str, price: str, amount: str, *, open_: bool, status: str
) -> dict[str, Any]:
    return {
        "pair": "BTC/USDT", "order_id": f"dry_run_{side}_{n}", "status": status,
        "amount": Decimal(amount), "safe_price": Decimal(price), "ft_order_side": side,
        "is_open": open_, "order_timestamp": int(NOW.timestamp() * 1000) + n * 1000,
        "order_filled_timestamp": None if open_ else int(NOW.timestamp() * 1000) + n * 1000,
    }  # fmt: skip


class FakeFreqtrade(HTTPAdapter):
    """In-memory server. `step()` advances an engine that chains entry, fill, exit."""

    def __init__(self, clock: Clock) -> None:
        super().__init__()
        self.clock = clock
        self.calls: list[tuple[str, str]] = []
        self.queries: list[dict[str, list[str]]] = []
        self.unreachable = False
        self.auth_source: Callable[[], tuple[str, str] | None] = lambda: None
        self.cfg: dict[str, Any] = {}
        self.pairs: list[str] = []
        self.state = "paused"
        self.initial_state = "paused"
        self.trades: list[dict[str, Any]] = []
        self._ids = 0
        self._tick = 0
        self.exit_reason = "roi"
        # Targeted failures: (method, path) -> (code, body), or None for a dropped connection.
        self.fail: dict[tuple[str, str], tuple[int, Any] | None] = {}
        self.override: dict[str, Any] = {}  # GET path -> body returned as is (malformed)
        self.raw_body: bytes | None = None  # raw body for any response
        self.delay_s = 0.0

    def load(self, spec: InstanceSpec) -> None:
        doc = json.loads(ftconfig.config_file(spec))
        self.pairs = doc["exchange"]["pair_whitelist"]
        self.cfg = {
            "version": "2026.9", "dry_run": doc["dry_run"], "trading_mode": "spot",
            "stake_currency": doc["stake_currency"], "stake_amount": str(doc["stake_amount"]),
            "available_capital": doc["available_capital"], "max_open_trades": float(doc["max_open_trades"]),
            "minimal_roi": doc["minimal_roi"], "stoploss": doc["stoploss"],
            "trailing_stop": doc["trailing_stop"], "trailing_stop_positive": doc.get("trailing_stop_positive"),
            "trailing_stop_positive_offset": doc["trailing_stop_positive_offset"],
            "trailing_only_offset_is_reached": doc["trailing_only_offset_is_reached"],
            "order_types": doc["order_types"], "bot_name": doc["bot_name"],
            "exchange": doc["exchange"]["name"], "strategy": doc["strategy"],
            "force_entry_enable": doc["force_entry_enable"],
            "position_adjustment_enable": doc["position_adjustment_enable"],
            "unfilledtimeout": doc["unfilledtimeout"],
            "entry_pricing": doc["entry_pricing"], "exit_pricing": doc["exit_pricing"],
            "runmode": "dry_run" if doc["dry_run"] else "live",
        }  # fmt: skip
        self.initial_state = doc["initial_state"]
        self.boot()

    def boot(self) -> None:
        self.state = self.initial_state

    # --- test driving ---------------------------------------------------------------
    def step(self) -> None:
        self._tick += 1
        if self.state == "stopped":
            return
        for t in self.open_trades():
            entry = next(
                (o for o in t["orders"] if o["ft_order_side"] == "buy" and o["is_open"]), None
            )
            if entry is not None:
                entry.update(is_open=False, status="closed")
                t["nr_of_successful_entries"] = 1
                t["amount"] = entry["amount"]
                t["open_fill_timestamp"] = t["open_timestamp"]
                t["stop_loss_abs"] = Decimal("95.5")
                return
            if self._tick % 3 == 0 and not any(o["is_open"] for o in t["orders"]):
                self.close_trade(t, self.exit_reason)
                return
        if self.state == "running" and len(self.open_trades()) < self.cfg["max_open_trades"]:
            self.open_entry()

    def open_trades(self) -> list[dict[str, Any]]:
        return [t for t in self.trades if t["is_open"]]

    def open_entry(self) -> dict[str, Any]:
        self._ids += 1
        ts = int(self.clock().timestamp() * 1000)
        t: dict[str, Any] = {
            "trade_id": self._ids, "pair": "BTC/USDT", "quote_currency": "USDT", "is_open": True,
            "amount": Decimal(0), "open_rate": Decimal("100.5"), "open_timestamp": ts,
            "open_fill_timestamp": None, "nr_of_successful_entries": 0, "stop_loss_abs": None,
            "enter_tag": None, "orders": [_order(self._ids, "buy", "100.5", "0.5", open_=True, status="open")],
        }  # fmt: skip
        self.trades.append(t)
        return t

    def open_exit_order(self, t: dict[str, Any]) -> None:
        t["orders"].append(
            _order(t["trade_id"] + 100, "sell", "101", "0.5", open_=True, status="open")
        )

    def close_trade(self, t: dict[str, Any], reason: str) -> None:
        for o in t["orders"]:
            if o["is_open"]:
                o.update(is_open=False, status="canceled")
        t["orders"].append(
            _order(t["trade_id"] + 200, "sell", "101", "0.5", open_=False, status="closed")
        )
        ts = int(self.clock().timestamp() * 1000)
        t.update(
            is_open=False, close_rate=Decimal("101"), close_timestamp=ts, exit_reason=reason,
            close_profit_abs=Decimal("0.25"), realized_profit=Decimal("0.25"),
            fee_open_cost=Decimal("0.05"), fee_close_cost=Decimal("0.05"),
        )  # fmt: skip

    # --- transport ----------------------------------------------------------------------
    def session(self) -> requests.Session:
        s = requests.Session()
        s.mount("http://", self)
        return s

    def send(
        self, request: requests.PreparedRequest, *args: Any, **kwargs: Any
    ) -> requests.Response:
        if self.unreachable:
            raise requests.ConnectionError("injoignable")
        url = urlsplit(request.url or "")
        path = url.path.removeprefix("/api/v1/")
        self.calls.append((str(request.method), path))
        self.queries.append(parse_qs(url.query))
        time.sleep(self.delay_s)
        key = (str(request.method), path)
        if key in self.fail:
            failure = self.fail[key]
            if failure is None:
                raise requests.ConnectionError("coupée")
            code, body = failure
        else:
            code, body = self._route(str(request.method), path, parse_qs(url.query), request)
        resp = requests.Response()
        resp.status_code = code
        # Streamed body, like a real response: the client reads it in chunks, bounded.
        resp.raw = io.BytesIO(_dump(body).encode() if self.raw_body is None else self.raw_body)
        resp.url = request.url or ""
        resp.request = request
        return resp

    def _route(
        self, method: str, path: str, query: dict[str, list[str]], request: requests.PreparedRequest
    ) -> tuple[int, Any]:
        want = self.auth_source()
        got = str(request.headers.get("Authorization", ""))
        if want and got != "Basic " + base64.b64encode(":".join(want).encode()).decode():
            return 401, {"detail": "Unauthorized"}
        body = json.loads(str(request.body)) if request.body else {}
        if method == "GET":
            return 200, self.override[path] if path in self.override else self._get(path, query)
        if method == "POST" and path in ("pause", "start", "stop"):
            self.state = {"pause": "paused", "start": "running", "stop": "stopped"}[path]
            if path == "start" and self.state == "running":
                pass
            return 200, {"status": "ok"}
        if method == "POST" and path == "forceexit":
            if self.state == "stopped":
                return 502, {"detail": "trader is not running"}
            for t in self.open_trades():
                if body["tradeid"] in ("all", str(t["trade_id"])):
                    self.close_trade(t, "force_exit")
            return 200, {"result": "ok"}
        if method == "DELETE" and path.startswith("trades/") and path.endswith("/open-order"):
            tid = int(path.split("/")[1])
            for t in self.open_trades():
                if t["trade_id"] == tid:
                    for o in t["orders"]:
                        if o["is_open"]:
                            o.update(is_open=False, status="canceled")
                    return 200, {"result": "ok"}
            return 502, {"detail": "Invalid trade_id."}
        return 404, {"detail": "Not Found"}

    def _get(self, path: str, query: dict[str, list[str]]) -> Any:
        if path == "show_config":
            return {**self.cfg, "state": self.state}
        if path == "whitelist":
            return {
                "whitelist": self.pairs,
                "length": len(self.pairs),
                "method": ["StaticPairList"],
            }
        if path == "health":
            return {"last_process_ts": int(self.clock().timestamp())}
        if path == "balance":
            return {
                "currencies": [
                    {"currency": "USDT", "free": Decimal("150.0"), "balance": Decimal("150.0")}
                ]
            }
        if path == "status":
            return self.open_trades()
        if path == "trades":
            done = [t for t in self.trades if not t["is_open"]]
            limit = int(query.get("limit", ["500"])[0])
            offset = int(query.get("offset", ["0"])[0])
            assert query.get("order_by_id") == ["false"]  # sorted by descending close date
            done.sort(key=lambda t: (-t["close_timestamp"], -t["trade_id"]))
            page = done[offset : offset + limit]
            return {
                "trades": page,
                "trades_count": len(page),
                "offset": offset,
                "total_trades": len(done),
            }
        return {}


def deployment(**over: Any) -> Deployment:
    base: dict[str, Any] = {
        "fingerprint": "f" * 64, "config_hash": "c" * 64, "code": STRATEGY_CODE,
        "image": "freqtradeorg/freqtrade:2026.9", "digest": "sha256:" + "a" * 64,
        "engine_version": "2026.9",
    }  # fmt: skip
    return Deployment(**{**base, **over})


class Rig:
    """Adapter + doubles, assembled as in the worker."""

    def __init__(self) -> None:
        self.clock = Clock()
        self.server = FakeFreqtrade(self.clock)
        self.runner = FakeRunner(self.server)
        self.runtime = FakeRuntime()
        self.server.auth_source = self._auth
        self.adapter = self.new_adapter()

    def _auth(self) -> tuple[str, str] | None:
        last = next(reversed(self.runtime.issued.values()), None)
        return None if last is None else (last["username"], last["password"])

    def new_adapter(self) -> ft.FreqtradeAdapter:
        return ft.FreqtradeAdapter(
            self.runner, self.runtime, clock=self.clock, http=self.server.session,
            address=lambda _iid: BASE,
        )  # fmt: skip

    def prepare(self, spec: InstanceSpec) -> InstanceSpec:
        spec = spec.model_copy(
            update={
                "engine": ft.ENGINE,
                "params": {"pairs": ["crypto:binance:BTC/USDT"]},
                "deployment": deployment(),
            }
        )
        self.server.load(spec)
        return spec


Factory = Callable[[], Rig]
