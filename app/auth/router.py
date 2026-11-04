from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import ChangePasswordRequest, LoginRequest, TokenResponse
from app.auth.service import change_own_password, login_user
from app.core.audit import log_action
from app.core.rate_limit import rate_limit
from app.database import get_db
from app.dependencies import get_current_user
from app.users.schemas import UserRead

router = APIRouter(prefix="/api/v1/auth", tags=["autenticação"])


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit("auth-login", limit=10))],
    responses={
        401: {"description": "Credenciais inválidas (inclusive conta inexistente ou inativa)"},
        429: {"description": "Muitas tentativas"},
    },
)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Troca e-mail e senha por um token Bearer (JWT). Use-o no cabeçalho
    `Authorization: Bearer <token>`. Limite: 10 tentativas por minuto por IP."""
    result = await login_user(db, body.email, body.password)
    await log_action(
        db,
        "user.login",
        "User",
        str(result["user"].id),
        actor_name=result["user"].name,
        actor_id=result["user"].id,
    )
    await db.commit()
    return result


@router.get("/me", response_model=UserRead)
async def me(current_user=Depends(get_current_user)):
    """O usuário do token. Funciona mesmo com troca de senha obrigatória pendente."""
    return current_user


@router.post(
    "/change-password",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit("auth-change-password", limit=10))],
    responses={
        403: {"description": "Senha atual incorreta ou nova senha igual à atual"},
        422: {"description": "Nova senha fora da política"},
    },
)
async def change_password(
    body: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """O próprio usuário troca a senha (obrigatório depois de uma redefinição
    administrativa). Revoga as demais sessões e devolve um token novo."""
    result = await change_own_password(db, current_user, body.current_password, body.new_password)
    await log_action(
        db,
        "user.password_changed",
        "User",
        str(current_user.id),
        actor_name=current_user.name,
        actor_id=current_user.id,
    )
    await db.commit()
    return result
