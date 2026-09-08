"""Valida tokens delegados para nuestra API antes de intercambiarlos por OBO."""

from dataclasses import dataclass, field
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient, PyJWKClientConnectionError, PyJWTError

from app.core.config import Settings
from app.core.exceptions import ApplicationError

API_SCOPE = "access_as_user"
bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    tenant_id: str
    object_id: str
    assertion: str = field(repr=False)


def authentication_required() -> ApplicationError:
    return ApplicationError(
        "Inicia sesión con Microsoft para continuar.",
        status_code=401,
        code="authentication_required",
        headers={"WWW-Authenticate": "Bearer"},
    )


class EntraTokenVerifier:
    def __init__(self, settings: Settings) -> None:
        self._tenant = str(settings.entra_tenant_id)
        self._audience = str(settings.entra_api_client_id)
        self._frontend = str(settings.entra_frontend_client_id)
        self._issuer = f"https://login.microsoftonline.com/{self._tenant}/v2.0"
        # Solo se comparten claves públicas, nunca tokens ni credenciales de usuarios.
        self._keys = PyJWKClient(
            f"https://login.microsoftonline.com/{self._tenant}/discovery/v2.0/keys",
            timeout=5,
        )

    def verify(self, token: str) -> AuthenticatedUser:
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
                raise authentication_required()
            signing_key = self._keys.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                leeway=30,
                options={
                    "require": ["exp", "iat", "nbf", "iss", "aud", "tid", "oid", "ver"],
                    "strict_aud": True,
                },
            )
            if claims["tid"] != self._tenant or claims["ver"] != "2.0":
                raise authentication_required()
            object_id = str(UUID(claims["oid"]))
        except PyJWKClientConnectionError:
            raise ApplicationError(
                "No se pudo verificar el inicio de sesión. Inténtalo de nuevo.",
                status_code=503,
                code="identity_provider_unavailable",
            ) from None
        except (PyJWTError, ValueError, TypeError, AttributeError):
            raise authentication_required() from None
        scopes = claims.get("scp")
        if (
            not isinstance(scopes, str)
            or API_SCOPE not in scopes.split()
            or claims.get("azp") != self._frontend
        ):
            raise ApplicationError(
                "El token no autoriza a esta aplicación a actuar en tu nombre.",
                status_code=403,
                code="insufficient_delegated_permission",
            )
        return AuthenticatedUser(self._tenant, object_id, token)


def require_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> AuthenticatedUser:
    if credentials is None:
        raise authentication_required()
    verifier = request.app.state.token_verifier
    if verifier is None:
        raise ApplicationError(
            "El inicio de sesión del backend no está configurado.",
            status_code=503,
            code="authentication_not_configured",
        )
    return verifier.verify(credentials.credentials)
