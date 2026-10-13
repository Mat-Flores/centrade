"""Authentification, 2FA et rôles (SPEC §13).

Les autres domaines n'importent que d'ici : les rôles `Viewer`, `Operator`, `Admin`, et
`current_user`, `require_role`, `require_recent_totp`.
"""

from centrade_api.auth.deps import (
    Admin,
    Operator,
    Principal,
    Role,
    Viewer,
    current_user,
    require_recent_totp,
    require_role,
    require_same_origin,
)
from centrade_api.auth.routes import router

__all__ = [
    "Admin",
    "Operator",
    "Principal",
    "Role",
    "Viewer",
    "current_user",
    "require_recent_totp",
    "require_role",
    "require_same_origin",
    "router",
]
