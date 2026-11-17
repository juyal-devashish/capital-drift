"""
Authentication and role-based access control.

The demo uses static bearer tokens from settings so the system runs without an identity provider.
The rest of the code only depends on :class:`User` and :func:`require_roles`, so swapping in
OIDC/JWT validation means changing :func:`get_current_user` alone.
"""

from dataclasses import dataclass
from enum import StrEnum

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings


class Role(StrEnum):
    BOARD_MEMBER = "board_member"  # reads the board, the queue and the forecast; decides nothing
    PROPERTY_MANAGER = "property_manager"  # works the review queue and records decisions
    ADMIN = "admin"  # everything a property manager can do, plus a full rerun of the queue


@dataclass(frozen=True)
class User:
    """Authenticated caller."""

    username: str
    role: Role


# Permission groups used by the routers, kept here so the access policy reads in one place.
CAPITAL_READ_ROLES = (Role.BOARD_MEMBER, Role.PROPERTY_MANAGER, Role.ADMIN)
CAPITAL_DECIDE_ROLES = (Role.PROPERTY_MANAGER, Role.ADMIN)
CAPITAL_ADMIN_ROLES = (Role.ADMIN,)

_bearer = HTTPBearer(auto_error=False)


def _token_table() -> dict[str, User]:
    """Parse ``CD_AUTH_TOKENS`` ("token:user:role,...") into a lookup table."""
    table: dict[str, User] = {}
    for entry in get_settings().auth_tokens.split(","):
        entry = entry.strip()
        if not entry:
            continue
        token, username, role = entry.split(":")
        table[token] = User(username=username, role=Role(role))
    return table


def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> User:
    """Resolve the bearer token to a user, or fail with 401."""
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    user = _token_table().get(creds.credentials)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    return user


def require_roles(*roles: Role):
    """Dependency factory: allow the request only if the caller has one of ``roles``."""

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Role '{user.role}' may not do this")
        return user

    return checker
