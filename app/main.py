import re
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
from app.geo.router import router as jurisdictions_router
from app.health.router import router as health_router
from app.incidents.router import router as incidents_router
from app.integrations.environment_router import router as environment_router
from app.integrations.geocoding_router import router as geocoding_router
from app.integrations.orbital_alerts_router import router as orbital_alerts_router
from app.missions.router import router as missions_router
from app.protected_areas.router import router as protected_areas_router
from app.reports.router import router as reports_router
from app.resources.router import router as resources_router
from app.teams.router import router as teams_router
from app.users.router import router as users_router
from app.war_room.router import router as war_room_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


DESCRIPTION = """
API do **IGNIS Orbital**, plataforma de monitoramento de focos de calor e apoio à
gestão de ocorrências ambientais, desenvolvida pela **Andrade Systems**.

**Autenticação.** `POST /api/v1/auth/login` devolve um token JWT; envie-o em
`Authorization: Bearer <token>`. O token é invalidado quando o administrador altera
o papel, desativa a conta ou redefine a senha. Contas com troca de senha pendente só
acessam `/auth/me` e `/auth/change-password`.

**Permissões.** Papéis hierárquicos verificados no servidor em cada endpoint:
`campo` < `gestor` < `orgao` < `admin`. Operações administrativas ficam sob
`/api/v1/admin` e exigem `admin`.

**Paginação.** Listagens aceitam `page` (a partir de 1) e `size` (máximo 100) e
devolvem `items`, `total`, `page`, `size` e `pages`.

**Datas.** Instantes em UTC (ISO 8601). A interface converte para o fuso de Fortaleza.

**Erros.** `401` sem autenticação ou sessão revogada; `403` papel insuficiente;
`404` recurso inexistente; `409` conflito de versão ou regra de proteção;
`422` dados inválidos; `429` limite de requisições.
"""

OPENAPI_TAGS = [
    {"name": "autenticação", "description": "Login, sessão atual e troca da própria senha."},
    {
        "name": "administração: painel",
        "description": "Cockpit: estado, fontes, execuções, "
        "permissões, configuração e especificação da API. Somente administrador.",
    },
    {
        "name": "administração: usuários",
        "description": "Gestão de contas com confirmação, "
        "motivo, controle de concorrência e auditoria. Somente administrador.",
    },
    {"name": "administração: auditoria", "description": "Trilha de auditoria e exportação CSV."},
    {
        "name": "focos de calor",
        "description": "Focos de calor por satélite (INPE, NASA FIRMS), "
        "agregados por município e estado das fontes.",
    },
    {"name": "jurisdições (IBGE)", "description": "Malha municipal oficial do IBGE."},
    {"name": "denúncias", "description": "Denúncias do portal público e triagem."},
    {"name": "incidentes", "description": "Ocorrências ambientais e seu ciclo de vida."},
    {"name": "missões", "description": "Missões de campo vinculadas a incidentes."},
    {"name": "equipes", "description": "Equipes de campo."},
    {"name": "recursos", "description": "Recursos operacionais."},
    {"name": "evidências", "description": "Evidências anexadas a incidentes."},
    {"name": "áreas protegidas", "description": "Áreas protegidas cadastradas."},
    {"name": "sala de crise", "description": "Visão consolidada para a sala de crise."},
    {"name": "meteorologia", "description": "Condições meteorológicas (Open-Meteo)."},
    {"name": "geocodificação", "description": "Geocodificação (OpenStreetMap Nominatim)."},
    {"name": "relatórios ESG", "description": "Experimental: fora da navegação operacional."},
    {
        "name": "assistente (experimental)",
        "description": "Experimental: fora da navegação operacional.",
    },
    {"name": "saúde do serviço", "description": "Liveness e readiness para a plataforma."},
]


def create_app() -> FastAPI:
    # In staging/production the public spec and its UIs are not mounted at all
    # (404): administrators read it through /api/v1/admin/openapi.json.
    public_docs = settings.docs_public
    app = FastAPI(
        title="IGNIS Orbital API",
        summary="Monitoramento de focos de calor e gestão de ocorrências ambientais.",
        description=DESCRIPTION,
        version=settings.app_version,
        contact={"name": "Andrade Systems", "url": "https://github.com/eliasandraade"},
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
        docs_url="/docs" if public_docs else None,
        redoc_url="/redoc" if public_docs else None,
        openapi_url="/openapi.json" if public_docs else None,
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
    app.include_router(war_room_router)

    # External integrations — Fase 1: Open-Meteo, NASA FIRMS, OSM/Nominatim
    app.include_router(environment_router)
    app.include_router(orbital_alerts_router)
    app.include_router(jurisdictions_router)
    app.include_router(geocoding_router)

    _summaries_from_docstrings(app)
    return app


def _summaries_from_docstrings(app: FastAPI) -> None:
    """OpenAPI summary = first sentence of the route docstring (pt-BR), instead
    of the function name FastAPI would title-case ("Get Stats")."""
    from app.core.permissions import _api_routes

    for route in _api_routes(app.routes):
        if route.summary or not route.description:
            continue
        paragraph = " ".join(route.description.strip().split("\n\n")[0].split())
        sentence = re.split(r"(?<=[.;])\s", paragraph, maxsplit=1)[0].rstrip(".;")
        if sentence:
            route.summary = sentence if len(sentence) <= 100 else sentence[:97].rstrip() + "…"


app = create_app()
