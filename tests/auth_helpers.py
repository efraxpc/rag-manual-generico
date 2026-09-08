from app.core.auth import AuthenticatedUser
from app.core.config import Settings

TENANT = "11111111-1111-4111-8111-111111111111"
API_CLIENT = "22222222-2222-4222-8222-222222222222"
FRONTEND_CLIENT = "33333333-3333-4333-8333-333333333333"
USER_ID = "44444444-4444-4444-8444-444444444444"
OTHER_USER_ID = "55555555-5555-4555-8555-555555555555"


def authenticated_user() -> AuthenticatedUser:
    return AuthenticatedUser(TENANT, USER_ID, "test-user-assertion")


def entra_settings(**overrides: object) -> Settings:
    return Settings(
        _env_file=None,
        **{
            "azure_search_endpoint": "https://example.search.windows.net",
            "azure_search_text_index_name": "text-chunks",
            "azure_search_index_name": "vector-chunks",
            "azure_search_vector_dimensions": 3,
            "entra_tenant_id": TENANT,
            "entra_api_client_id": API_CLIENT,
            "entra_api_client_secret": "test-api-secret",
            "entra_frontend_client_id": FRONTEND_CLIENT,
            **overrides,
        },
    )
