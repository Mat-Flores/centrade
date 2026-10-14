"""Deployment fingerprint (I10): what makes an instance's behaviour, mode aside.

Paper and live of the same version have the same fingerprint: mode-specific fields
(dry-run, trades database, credentials, bot name) are not inputs to it.
"""

from collections.abc import Collection, Mapping
from typing import Any

from centrade_core.audit import fingerprint


def config_hash(config: Mapping[str, Any], *, exclude: Collection[str] = ()) -> str:
    """Hash of the generated configuration (canonical JSON), without mode-specific keys."""
    return fingerprint({k: v for k, v in config.items() if k not in exclude})


def deployment_fingerprint(
    *,
    code_hash: str,
    params: Mapping[str, Any],
    exits: Mapping[str, Any],
    image: str,
    digest: str,
    config_hash: str,
) -> str:
    return fingerprint(
        {
            "code_hash": code_hash,
            "params": params,
            "exits": exits,
            "image": image,
            "digest": digest,
            "config_hash": config_hash,
        }
    )
