"""Fail-closed Clerk session-token verification for the Shopify API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

import jwt
from jwt import PyJWKClient
from jwt.types import Options


@dataclass(frozen=True)
class ClerkAuthSettings:
    issuer_url: str
    jwks_url: str
    authorized_parties: tuple[str, ...]
    audience: str | None = None

    @classmethod
    def from_env(cls) -> ClerkAuthSettings:
        issuer = os.environ.get("CLERK_ISSUER_URL", "").strip().rstrip("/")
        jwks = os.environ.get("CLERK_JWKS_URL", "").strip()
        parties = tuple(
            sorted(
                {
                    value.strip().rstrip("/")
                    for value in os.environ.get("CLERK_AUTHORIZED_PARTIES", "").split(",")
                    if value.strip()
                }
            )
        )
        missing = []
        if not issuer:
            missing.append("CLERK_ISSUER_URL")
        if not jwks:
            missing.append("CLERK_JWKS_URL")
        if not parties:
            missing.append("CLERK_AUTHORIZED_PARTIES")
        if missing:
            raise RuntimeError(f"missing required Clerk configuration: {', '.join(missing)}")
        if not issuer.startswith("https://") or not jwks.startswith("https://"):
            raise RuntimeError("Clerk issuer and JWKS URLs must use HTTPS")
        return cls(
            issuer_url=issuer,
            jwks_url=jwks,
            authorized_parties=parties,
            audience=os.environ.get("CLERK_AUDIENCE", "").strip() or None,
        )


@dataclass(frozen=True)
class VerifiedIdentity:
    issuer: str
    subject: str


class SigningKeyClient(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> Any: ...


class ClerkJWTVerifier:
    """Verify Clerk JWT signature and security-critical registered claims."""

    def __init__(
        self,
        settings: ClerkAuthSettings,
        *,
        signing_keys: SigningKeyClient | None = None,
    ) -> None:
        self.settings = settings
        self._signing_keys = signing_keys or PyJWKClient(
            settings.jwks_url,
            cache_keys=True,
            cache_jwk_set=True,
            lifespan=300,
            timeout=5,
        )

    def verify(self, token: str) -> VerifiedIdentity:
        if not token or len(token) > 16_384:
            raise ValueError("invalid authentication token")
        try:
            signing_key = self._signing_keys.get_signing_key_from_jwt(token).key
            options = Options(
                verify_aud=self.settings.audience is not None,
                require=["exp", "iat", "nbf", "iss", "sub"],
            )
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                issuer=self.settings.issuer_url,
                audience=self.settings.audience,
                options=options,
            )
        except jwt.PyJWTError as exc:
            raise ValueError("invalid or expired authentication token") from exc
        subject = claims.get("sub")
        authorized_party = claims.get("azp")
        if not isinstance(subject, str) or not subject.strip() or len(subject) > 255:
            raise ValueError("invalid authentication subject")
        if (
            not isinstance(authorized_party, str)
            or authorized_party.rstrip("/") not in self.settings.authorized_parties
        ):
            raise ValueError("authentication token has an unauthorized party")
        return VerifiedIdentity(self.settings.issuer_url, subject)
