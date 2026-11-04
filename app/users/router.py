"""Administrative user management (/api/v1/admin/users). Administrators only.

Role, status and password have dedicated actions with confirmation by the
administrator's own password, a mandatory reason and audit. There is no
physical deletion: an account is deactivated.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.schemas import AuditLogRead
from app.audit.service import list_logs
from app.core.enums import UserRole
from app.core.pagination import Page
from app.core.rate_limit import rate_limit
from app.database import get_db
from app.dependencies import require_role
from app.users import admin_service
from app.users.schemas import (
    AdminPasswordReset,
    AdminRoleChange,
    AdminStatusChange,
    AdminUserCreate,
    AdminUserProfileUpdate,
    UserAdminRead,
)

router = APIRouter(prefix="/api/v1/admin/users", tags=["administração: usuários"])

_ADMIN = Depends(require_role(UserRole.ADMIN))
# Each sensitive action verifies a password (bcrypt): bounded per IP.
_SENSITIVE = [Depends(rate_limit("admin-sensitive", limit=20))]
_COMMON = {
    401: {"description": "Sem token, token inválido ou sessão revogada"},
    403: {"description": "Papel insuficiente, troca de senha pendente ou confirmação incorreta"},
    404: {"description": "Usuário não encontrado"},
}
_GUARDED = {
    **_COMMON,
    409: {"description": "Versão desatualizada, ação sobre si mesmo ou último administrador"},
    422: {"description": "Dados inválidos (motivo, senha fora da política, equipe inexistente)"},
}


@router.get("", response_model=Page[UserAdminRead], responses=_COMMON)
async def list_users(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, max_length=100, description="Busca em nome e e-mail"),
    role: UserRole | None = Query(None),
    status: Literal["active", "inactive"] | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=_ADMIN,
):
    """Lista paginada, mais recentes primeiro."""
    active = None if status is None else status == "active"
    return await admin_service.list_users(db, page=page, size=size, q=q, role=role, active=active)


@router.post("", response_model=UserAdminRead, status_code=201, responses=_GUARDED)
async def create_user(
    body: AdminUserCreate, db: AsyncSession = Depends(get_db), current_user=_ADMIN
):
    """Cria a conta com uma senha provisória. Nenhuma senha é enviada por e-mail:
    o administrador a comunica por canal próprio e a troca é exigida no 1º login."""
    user = await admin_service.create_user(db, current_user, body)
    await db.commit()
    return user


@router.get("/{user_id}", response_model=UserAdminRead, responses=_COMMON)
async def get_user(user_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user=_ADMIN):
    """Detalhe de um usuário (sem senha nem hash)."""
    return await admin_service.get_user(db, user_id)


@router.patch("/{user_id}", response_model=UserAdminRead, responses=_GUARDED)
async def update_profile(
    user_id: uuid.UUID,
    body: AdminUserProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=_ADMIN,
):
    """Nome, e-mail e equipe. Papel, situação e senha usam as ações dedicadas."""
    user = await admin_service.update_profile(db, current_user, user_id, body)
    await db.commit()
    return user


@router.post(
    "/{user_id}/role", response_model=UserAdminRead, responses=_GUARDED, dependencies=_SENSITIVE
)
async def change_role(
    user_id: uuid.UUID,
    body: AdminRoleChange,
    db: AsyncSession = Depends(get_db),
    current_user=_ADMIN,
):
    """Altera o papel. Exige a senha do administrador e um motivo; encerra as
    sessões do usuário; nunca rebaixa o último administrador nem a si mesmo."""
    user = await admin_service.change_role(db, current_user, user_id, body)
    await db.commit()
    return user


@router.post(
    "/{user_id}/deactivate",
    response_model=UserAdminRead,
    responses=_GUARDED,
    dependencies=_SENSITIVE,
)
async def deactivate(
    user_id: uuid.UUID,
    body: AdminStatusChange,
    db: AsyncSession = Depends(get_db),
    current_user=_ADMIN,
):
    """Desativa (sem exclusão física) e encerra as sessões. Bloqueado para a própria
    conta e para o último administrador ativo."""
    user = await admin_service.set_active(db, current_user, user_id, body, active=False)
    await db.commit()
    return user


@router.post(
    "/{user_id}/activate", response_model=UserAdminRead, responses=_GUARDED, dependencies=_SENSITIVE
)
async def activate(
    user_id: uuid.UUID,
    body: AdminStatusChange,
    db: AsyncSession = Depends(get_db),
    current_user=_ADMIN,
):
    """Reativa a conta. Exige a senha do administrador e um motivo."""
    user = await admin_service.set_active(db, current_user, user_id, body, active=True)
    await db.commit()
    return user


@router.post(
    "/{user_id}/reset-password",
    response_model=UserAdminRead,
    responses=_GUARDED,
    dependencies=_SENSITIVE,
)
async def reset_password(
    user_id: uuid.UUID,
    body: AdminPasswordReset,
    db: AsyncSession = Depends(get_db),
    current_user=_ADMIN,
):
    """Define uma senha provisória (troca obrigatória no próximo login) e encerra as
    sessões. A senha não é devolvida nem registrada."""
    user = await admin_service.reset_password(db, current_user, user_id, body)
    await db.commit()
    return user


@router.get("/{user_id}/audit", response_model=Page[AuditLogRead], responses=_COMMON)
async def user_history(
    user_id: uuid.UUID,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user=_ADMIN,
):
    """Eventos em que o usuário foi alvo ou ator."""
    await admin_service.get_user(db, user_id)
    return await list_logs(db=db, page=page, size=size, involving_user=user_id)
