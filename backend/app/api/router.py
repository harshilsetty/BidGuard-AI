from fastapi import APIRouter
from app.api.v1.health import router as health_router
from app.api.v1.auth import router as auth_router
from app.api.v1.tenders import router as tenders_router
from app.api.v1.bidders import router as bidders_router
from app.api.v1.evaluations import router as evaluations_router
from app.api.v1.mock_sources import router as mock_sources_router
from app.api.v1.statutory import router as statutory_router
from app.api.v1.verification_intelligence import router as verification_intelligence_router
from app.api.v1.audit import router as audit_router
from app.api.v1.organizations import router as organizations_router

api_router = APIRouter()

# Mount API v1 routes
api_router.include_router(health_router, prefix="/v1")
api_router.include_router(auth_router, prefix="/v1")
api_router.include_router(organizations_router, prefix="/v1")
api_router.include_router(audit_router, prefix="/v1")
api_router.include_router(tenders_router, prefix="/v1")
api_router.include_router(bidders_router, prefix="/v1")
api_router.include_router(evaluations_router, prefix="/v1")
api_router.include_router(mock_sources_router, prefix="/v1")
api_router.include_router(statutory_router, prefix="/v1")
api_router.include_router(verification_intelligence_router, prefix="/v1")
