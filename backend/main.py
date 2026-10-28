import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles


BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent
FRONTEND_DIR = PROJECT_DIR / "frontend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.interfaces.api_claims import router as claims_router
from app.interfaces.api_auth import router as auth_router
from app.interfaces.api_copilot import router as copilot_router
from app.interfaces.api_feedback import router as feedback_router
from app.interfaces.api_rules import router as rules_router
from app.interfaces.api_stats import router as stats_router
from app.interfaces.api_audit import router as audit_router
from app.interfaces.api_disputes import router as disputes_router
from app.interfaces.api_rs_portal import router as rs_portal_router
from app.interfaces.api_facilities import router as facilities_router
from app.infrastructure.database import Base, engine
from app.infrastructure import security_models as _security_models
from app.infrastructure import orm_models as _orm_models
from scripts.additive_migration import migrate_additive_schema


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    migrate_additive_schema(engine)
    yield


app = FastAPI(
    title="KlaimGuard AI - Enterprise Audit API",
    description="Casemix JKN Fraud Detection Engine based on Kemenkes & BPJS Regulations",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=False, 
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def handle_unexpected_exception(
    _request: Request, exc: Exception
) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"error": True, "message": str(exc), "status_code": 500},
    )


@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


app.include_router(claims_router)
app.include_router(auth_router)
app.include_router(rules_router)
app.include_router(feedback_router)
app.include_router(stats_router)
app.include_router(audit_router)
app.include_router(copilot_router)
app.include_router(disputes_router)
app.include_router(rs_portal_router)
app.include_router(facilities_router)
app.mount(
    "/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend"
)
