"""Clientes de Search aislados por petición, con la identidad del usuario."""

from collections.abc import Iterator
from contextlib import contextmanager

import httpx
from azure.core.exceptions import AzureError, ClientAuthenticationError
from azure.identity import OnBehalfOfCredential
from azure.search.documents import SearchClient

from app.core.config import Settings
from app.core.exceptions import ApplicationError
from app.integrations.azure_openai_chat import (
    AZURE_AI_SCOPE,
    AzureOpenAIChatClient,
)
from app.integrations.azure_search import AzureSearchAdapter
from app.integrations.azure_text_search import AzureTextSearchAdapter
from app.rag.contracts import TextChunkStore, TextCompletionClient, VectorStore

SEARCH_SCOPE = "https://search.azure.com/.default"


@contextmanager
def open_user_credential(
    settings: Settings, assertion: str, *, scope: str = SEARCH_SCOPE
) -> Iterator[OnBehalfOfCredential]:
    if not settings.entra_configured or not assertion:
        raise ApplicationError(
            "Se requiere autenticación delegada para acceder al recurso Azure.",
            status_code=503,
            code="authentication_not_configured",
        )
    assert settings.entra_api_client_secret is not None
    with OnBehalfOfCredential(
        tenant_id=str(settings.entra_tenant_id),
        client_id=str(settings.entra_api_client_id),
        client_secret=settings.entra_api_client_secret.get_secret_value(),
        user_assertion=assertion,
    ) as credential:
        try:
            credential.get_token(scope)
        except ClientAuthenticationError:
            raise ApplicationError(
                "Entra ID no autorizó el acceso delegado al recurso Azure. Revisa "
                "el consentimiento de la aplicación o vuelve a iniciar sesión.",
                status_code=403,
                code="delegated_authentication_failed",
            ) from None
        except AzureError:
            raise ApplicationError(
                "No se pudo contactar con Entra ID para acceder al recurso Azure.",
                status_code=503,
                code="identity_provider_unavailable",
            ) from None
        yield credential


@contextmanager
def open_user_chat_client(
    settings: Settings, *, user_assertion: str
) -> Iterator[TextCompletionClient | None]:
    if settings.azure_openai_chat_deployment is None:
        yield None
        return
    assert settings.azure_openai_endpoint is not None
    with (
        open_user_credential(
            settings, user_assertion, scope=AZURE_AI_SCOPE
        ) as credential,
        httpx.Client(timeout=settings.rag_generation_timeout_seconds) as http_client,
    ):
        yield AzureOpenAIChatClient(
            endpoint=str(settings.azure_openai_endpoint),
            deployment=settings.azure_openai_chat_deployment,
            credential=credential,
            http_client=http_client,
        )


@contextmanager
def open_vector_store(
    settings: Settings, *, user_assertion: str
) -> Iterator[VectorStore | None]:
    if settings.azure_search_index_name is None:
        yield None
        return

    assert settings.azure_search_endpoint is not None
    assert settings.azure_search_vector_dimensions is not None

    with (
        open_user_credential(settings, user_assertion) as credential,
        SearchClient(
            endpoint=str(settings.azure_search_endpoint),
            index_name=settings.azure_search_index_name,
            credential=credential,
        ) as client,
    ):
        yield AzureSearchAdapter(
            client, vector_dimensions=settings.azure_search_vector_dimensions
        )


@contextmanager
def open_text_store(
    settings: Settings, *, user_assertion: str
) -> Iterator[TextChunkStore | None]:
    if settings.azure_search_text_index_name is None:
        yield None
        return
    assert settings.azure_search_endpoint is not None
    with (
        open_user_credential(settings, user_assertion) as credential,
        SearchClient(
            endpoint=str(settings.azure_search_endpoint),
            index_name=settings.azure_search_text_index_name,
            credential=credential,
        ) as client,
    ):
        yield AzureTextSearchAdapter(client)
