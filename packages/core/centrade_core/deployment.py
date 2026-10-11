"""Empreinte de déploiement (I10) : ce qui fait le comportement d'une instance, hors mode.

Paper et live d'une même version ont la même empreinte : les champs propres au mode
(dry-run, base de trades, identifiants, nom du bot) n'en sont pas des entrées.
"""

from collections.abc import Collection, Mapping
from typing import Any

from centrade_core.audit import fingerprint


def config_hash(config: Mapping[str, Any], *, exclude: Collection[str] = ()) -> str:
    """Hash de la configuration générée (JSON canonique), sans les clés propres au mode."""
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
