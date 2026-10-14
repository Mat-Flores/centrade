"""Authentication, 2FA and roles (SPEC §13).

Other domains import only from here: the roles `Viewer`, `Operator`, `Admin`, and
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
