from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import LoginRequest, TokenResponse
from app.auth.service import login_user
from app.core.audit import log_action
from app.database import get_db
from app.dependencies import get_current_user
from app.users.schemas import UserRead

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await login_user(db, body.email, body.password)
    await log_action(
        db,
        "user.login",
        "User",
        result["user_id"],
        actor_name=result["name"],
    )
    await db.commit()
    return result


@router.get("/me", response_model=UserRead)
async def me(current_user=Depends(get_current_user)):
    return current_user
