"""Schemas of the authentication routes.

Password and code are `SecretStr`: they never appear in a log.
"""

from uuid import UUID

from pydantic import BaseModel, Field, SecretStr


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=1024)  # bounds the cost of argon2


class TotpIn(BaseModel):
    code: SecretStr = Field(min_length=1, max_length=64)  # 6 digits, or recovery code


class LoginOut(BaseModel):
    totp_required: bool


class Me(BaseModel):
    id: UUID
    email: str
    role: str
