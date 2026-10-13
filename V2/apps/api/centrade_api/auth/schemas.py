"""Schémas des routes d'authentification.

Mot de passe et code sont des `SecretStr` : ils n'apparaissent jamais dans un log.
"""

from uuid import UUID

from pydantic import BaseModel, Field, SecretStr


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=1024)  # borne le coût d'argon2


class TotpIn(BaseModel):
    code: SecretStr = Field(min_length=1, max_length=64)  # 6 chiffres, ou code de récupération


class LoginOut(BaseModel):
    totp_required: bool


class Me(BaseModel):
    id: UUID
    email: str
    role: str
