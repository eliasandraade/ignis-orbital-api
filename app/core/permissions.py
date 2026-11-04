"""Static RBAC, described from the code itself.

Authorization is enforced by `require_role(minimum)` (hierarchical levels) and
`get_current_user` on each route. `endpoint_matrix` reads those dependencies
from the mounted routes, so the matrix shown in the admin cockpit cannot
drift from what the API actually enforces.
"""

from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.core.enums import UserRole
from app.dependencies import ROLE_LEVELS, get_current_user

# Access levels that are not a role (labels shown in the cockpit matrix).
PUBLIC = "público"
AUTHENTICATED = "autenticado"

ROLE_LABELS: dict[str, str] = {
    UserRole.PUBLICO: "Público (cadastrado)",
    UserRole.CAMPO: "Equipe de campo",
    UserRole.GESTOR: "Gestor",
    UserRole.ORGAO: "Órgão / analista",
    UserRole.ADMIN: "Administrador",
}

ROLE_DESCRIPTIONS: dict[str, str] = {
    UserRole.PUBLICO: "Conta sem acesso operacional. O portal público não exige conta.",
    UserRole.CAMPO: "Operação de campo e Sala de Crise; sem painel de gestão.",
    UserRole.GESTOR: "Painel, mapa orbital, denúncias, incidentes, equipes e recursos.",
    UserRole.ORGAO: "Tudo do gestor, mais estatísticas institucionais.",
    UserRole.ADMIN: "Tudo, mais usuários, auditoria, fontes, execuções e documentação da API.",
}


@dataclass(frozen=True, slots=True)
class EndpointRule:
    method: str
    path: str
    tag: str
    summary: str
    access: str  # PUBLIC, AUTHENTICATED or a role value (minimum level)


def _minimum_role(route: APIRoute) -> str:
    return _minimum_role_from(route.dependant)


def _minimum_role_from(dependant) -> str:
    """Walks the dependency tree: the strictest require_role wins."""
    access = PUBLIC
    for dependency in dependant.dependencies:
        call = dependency.call
        closure = getattr(call, "__closure__", None) or ()
        if getattr(call, "__qualname__", "").startswith("require_role.") and closure:
            level = next(
                (c.cell_contents for c in closure if isinstance(c.cell_contents, int)), None
            )
            if level is not None:
                return next(r for r, lvl in ROLE_LEVELS.items() if lvl == level).value
        if call is get_current_user:
            access = AUTHENTICATED
        deeper = _minimum_role_from(dependency)
        if deeper not in (PUBLIC, AUTHENTICATED):
            return deeper
        if deeper == AUTHENTICATED:
            access = AUTHENTICATED
    return access


def _api_routes(routes) -> Iterator[APIRoute]:
    """Flattens included routers. FastAPI >= 0.16x wraps each include_router in
    an object holding `original_router`; older versions copy the routes. The
    routers are included without extra prefix or dependencies (app/main.py), so
    the original routes carry the effective path and guards. A test checks that
    every operation of the OpenAPI document appears in the matrix."""
    for route in routes:
        original = getattr(route, "original_router", None)
        if original is not None:
            yield from _api_routes(original.routes)
        elif isinstance(route, APIRoute):
            yield route


def endpoint_matrix(app: FastAPI) -> list[EndpointRule]:
    rules = []
    for route in _api_routes(app.routes):
        if not route.include_in_schema:
            continue
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            rules.append(
                EndpointRule(
                    method=method,
                    path=route.path,
                    tag=(route.tags or ["outros"])[0],
                    summary=route.summary or route.name.replace("_", " "),
                    access=_minimum_role(route),
                )
            )
    return sorted(rules, key=lambda r: (r.tag, r.path, r.method))


def allowed(access: str, role: str) -> bool:
    if access == PUBLIC:
        return True
    if access == AUTHENTICATED:
        return True
    return ROLE_LEVELS[UserRole(role)] >= ROLE_LEVELS[UserRole(access)]
