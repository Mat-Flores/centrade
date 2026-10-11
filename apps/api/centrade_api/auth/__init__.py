"""Authentification, 2FA et rôles (SPEC §13).

Les autres lots n'importent que d'ici : `current_user`, `require_role`, `require_recent_totp`.
"""

from centrade_api.auth.deps import (
    Principal,
    Role,
    current_user,
    require_recent_totp,
    require_role,
    require_same_origin,
)
from centrade_api.auth.routes import router

__all__ = [
    "Principal",
    "Role",
    "current_user",
    "require_recent_totp",
    "require_role",
    "require_same_origin",
    "router",
]
