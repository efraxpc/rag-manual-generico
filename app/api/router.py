from fastapi import APIRouter

from app.api.v1.endpoints import documents, health, queries

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(documents.router, tags=["documents"])
api_router.include_router(queries.router, tags=["queries"])
