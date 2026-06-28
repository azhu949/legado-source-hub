"""总路由注册。"""

from fastapi import APIRouter

from app.api.admin_auth import router as auth_router
from app.api.admin_cache import router as cache_router
from app.api.admin_health import router as health_router
from app.api.admin_logs import router as logs_router
from app.api.admin_rules import router as rules_router
from app.api.admin_sources import router as sources_router
from app.api.public import router as public_router

api_router = APIRouter()
api_router.include_router(public_router)
api_router.include_router(auth_router)
api_router.include_router(sources_router)
api_router.include_router(rules_router)
api_router.include_router(health_router)
api_router.include_router(logs_router)
api_router.include_router(cache_router)
