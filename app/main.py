from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.admin.router import router as admin_stats_router
from app.audit.router import router as audit_router
from app.aurora.router import router as aurora_router
from app.auth.router import router as auth_router
from app.config import get_settings
from app.esg.router import router as esg_router
from app.evidence.router import router as evidence_router
from app.health.router import router as health_router
from app.incidents.router import router as incidents_router
from app.missions.router import router as missions_router
from app.protected_areas.router import router as protected_areas_router
from app.reports.router import router as reports_router
from app.resources.router import router as resources_router
from app.teams.router import router as teams_router
from app.users.router import router as users_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="IGNIS Orbital API",
        description=(
            "API REST para monitoramento ambiental, proteção de áreas naturais e "
            "gestão de incidentes ambientais. "
            "Projeto acadêmico FIAP — Global Solution 2026.\n\n"
            "**Autores:** Elias Sales de Freitas (RM561257) · João Vitor Bernardo (RM566427)"
        ),
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health/readiness — sem prefixo /api/v1 para compatibilidade com infra
    app.include_router(health_router)

    # Routers de domínio — Fases 4+
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(protected_areas_router)
    app.include_router(reports_router)
    app.include_router(incidents_router)
    app.include_router(teams_router)
    app.include_router(resources_router)
    app.include_router(missions_router)
    app.include_router(evidence_router)
    app.include_router(aurora_router)
    app.include_router(esg_router)
    app.include_router(audit_router)
    app.include_router(admin_stats_router)

    return app


app = create_app()
