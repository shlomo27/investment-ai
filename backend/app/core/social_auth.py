"""Verifying Sign in with Apple / Google ID tokens.

The app hands the server the ID token the provider issued on the device. The
token is a JWT signed with the provider's private key; it is trusted only
after checking, here on the server:

  signature  against the provider's published keys (JWKS)
  iss        the provider itself issued it
  aud        it was issued for THIS app — the check that stops a token
             minted for any other app from being replayed to sign in here
  exp        it has not expired

Nothing the client says about the user (name, email) is taken on trust
except where the provider does not put it in the token: Apple sends the
user's name only once, to the device, never in the token.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx
from jose import jwt
from jose.exceptions import JWTError

from app.core.config import settings

_PROVIDERS = {
    "google": {
        "jwks": "https://www.googleapis.com/oauth2/v3/certs",
        "issuers": ("https://accounts.google.com", "accounts.google.com"),
    },
    "apple": {
        "jwks": "https://appleid.apple.com/auth/keys",
        "issuers": ("https://appleid.apple.com",),
    },
}

#: provider -> (fetched_at, keys). Both providers rotate keys rarely and
#: publish new ones before using them; an unknown kid triggers one refetch.
_jwks_cache: Dict[str, tuple[float, List[Dict[str, Any]]]] = {}
_JWKS_TTL = 6 * 3600


class SocialTokenError(Exception):
    """The token is not acceptable. The message is safe to log, not to show."""


@dataclass
class SocialIdentity:
    provider: str
    sub: str
    email: Optional[str]
    email_verified: bool
    name: Optional[str]


def _audiences(provider: str) -> List[str]:
    raw = settings.GOOGLE_CLIENT_IDS if provider == "google" else settings.APPLE_CLIENT_IDS
    return [a.strip() for a in (raw or "").split(",") if a.strip()]


async def _keys(provider: str, refresh: bool = False) -> List[Dict[str, Any]]:
    cached = _jwks_cache.get(provider)
    if cached and not refresh and time.time() - cached[0] < _JWKS_TTL:
        return cached[1]
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(_PROVIDERS[provider]["jwks"])
        resp.raise_for_status()
        keys = resp.json().get("keys", [])
    _jwks_cache[provider] = (time.time(), keys)
    return keys


async def verify_id_token(provider: str, id_token: str) -> SocialIdentity:
    if provider not in _PROVIDERS:
        raise SocialTokenError(f"unknown provider {provider!r}")
    audiences = _audiences(provider)
    if not audiences:
        raise SocialTokenError(f"{provider} sign-in is not configured on the server")

    try:
        header = jwt.get_unverified_header(id_token)
    except JWTError as exc:
        raise SocialTokenError(f"malformed token: {exc}")
    kid = header.get("kid")

    key = next((k for k in await _keys(provider) if k.get("kid") == kid), None)
    if key is None:
        key = next((k for k in await _keys(provider, refresh=True) if k.get("kid") == kid), None)
    if key is None:
        raise SocialTokenError("token signed with an unknown key")

    try:
        # aud is checked below against a LIST (web, iOS and Android client
        # IDs are different audiences); python-jose takes only one.
        claims = jwt.decode(
            id_token, key, algorithms=["RS256"],
            options={"verify_aud": False, "verify_at_hash": False},
        )
    except JWTError as exc:
        raise SocialTokenError(f"invalid token: {exc}")

    if claims.get("iss") not in _PROVIDERS[provider]["issuers"]:
        raise SocialTokenError(f"wrong issuer {claims.get('iss')!r}")
    aud = claims.get("aud")
    aud_list = aud if isinstance(aud, list) else [aud]
    if not any(a in audiences for a in aud_list):
        raise SocialTokenError(f"token issued for another app ({aud!r})")
    sub = claims.get("sub")
    if not sub:
        raise SocialTokenError("token has no subject")

    # Apple sends email_verified as the string "true"; Google as a bool.
    verified = str(claims.get("email_verified", "")).lower() == "true"
    return SocialIdentity(
        provider=provider,
        sub=str(sub),
        email=(claims.get("email") or None),
        email_verified=verified,
        name=claims.get("name"),
    )
