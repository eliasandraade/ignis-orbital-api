"""Administrative user management with the protections the cockpit relies on.

Every mutation:
- runs inside one transaction that locks the target row (and, when the admin
  set can shrink, every admin row) — concurrent requests serialise;
- checks `expected_version` (optimistic locking: 409 when someone else
  changed the user since it was read);
- bumps `session_version` when the change must end the user's open sessions
  (role, deactivation, password reset);
- writes one audit entry with actor, target, action, reason and result.
Sensitive actions also require the acting administrator's own password
(step-up), verified here, never only in the browser.
"""

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_action
from app.core.enums import UserRole
from app.core.exceptions import ConflictException, ForbiddenException, NotFoundException
from app.core.pagination import Page
from app.core.security import hash_password, verify_password
from app.users.model import User
from app.users.schemas import (
    AdminPasswordReset,
    AdminRoleChange,
    AdminStatusChange,
    AdminUserCreate,
    AdminUserProfileUpdate,
    UserAdminRead,
)

# Audit actions referenced in several places (step-up failure and outcome).
ACTION_ROLE_CHANGE = "user.role_change"
ACTION_PASSWORD_RESET = "user.password_reset"

ADMIN = UserRole.ADMIN.value
# Transaction-scoped advisory lock taken by every change that can shrink the set
# of administrators (role, status). Serialises them: two admins demoting each
# other at the same time cannot deadlock nor both succeed.
_ADMIN_SET_LOCK = 0x1601_A7A1


def _demo_emails() -> frozenset[str]:
    # Accounts created by the demonstration seed never count as legitimate admins.
    from seed.demo_users import DEMO_EMAILS

    return DEMO_EMAILS


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def list_users(
    db: AsyncSession,
    *,
    page: int,
    size: int,
    q: str | None,
    role: UserRole | None,
    active: bool | None,
) -> Page[UserAdminRead]:
    conditions = []
    if q:
        pattern = f"%{q.strip().lower()}%"
        conditions.append(
            or_(func.lower(User.name).like(pattern), func.lower(User.email).like(pattern))
        )
    if role is not None:
        conditions.append(User.role == role.value)
    if active is not None:
        conditions.append(User.is_active == active)
    total = await db.scalar(select(func.count()).select_from(User).where(*conditions))
    rows = (
        await db.scalars(
            select(User)
            .where(*conditions)
            .order_by(User.created_at.desc(), User.id)
            .offset((page - 1) * size)
            .limit(size)
        )
    ).all()
    return Page.create(
        items=[UserAdminRead.model_validate(u) for u in rows],
        total=total or 0,
        page=page,
        size=size,
    )


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundException("Usuário")
    return user


async def _lock_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await db.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user is None:
        raise NotFoundException("Usuário")
    return user


async def _serialize_admin_changes(db: AsyncSession, actor: User) -> None:
    """Takes the admin-set lock, then re-reads the acting admin: a request that
    waited on the lock must not act with a role or status it lost meanwhile."""
    await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _ADMIN_SET_LOCK})
    await db.refresh(actor)
    if not actor.is_active or actor.role != ADMIN:
        raise ForbiddenException("Sua conta perdeu a permissão de administrador")


def _check_version(user: User, expected: int) -> None:
    if user.row_version != expected:
        raise ConflictException(
            "Este usuário foi alterado por outra sessão. Recarregue os dados e tente de novo."
        )


async def _email_taken(db: AsyncSession, email: str, exclude: uuid.UUID | None = None) -> bool:
    query = select(User.id).where(func.lower(User.email) == email.lower())
    if exclude is not None:
        query = query.where(User.id != exclude)
    return (await db.scalar(query)) is not None


async def _check_team(db: AsyncSession, team_id: uuid.UUID | None) -> None:
    if team_id is None:
        return
    from app.teams.model import FieldTeam

    if await db.get(FieldTeam, team_id) is None:
        raise HTTPException(status_code=422, detail="Equipe inexistente")


async def _step_up(db: AsyncSession, actor: User, password: str, action: str, target: User) -> None:
    """The acting admin re-enters their own password. A failure is audited and
    committed before the 403, so it survives the request's rollback."""
    if verify_password(password, actor.password_hash):
        return
    await log_action(
        db,
        f"{action}.denied",
        "User",
        str(target.id),
        actor_name=actor.name,
        actor_id=actor.id,
        metadata={"result": "denied", "cause": "step_up_failed"},
    )
    await db.commit()
    raise ForbiddenException("Senha de confirmação incorreta")


async def _legitimate_admins_after(db: AsyncSession, target: User, *, removed: bool) -> int:
    """Active non-demo admins once `target` stops being one (rows locked)."""
    admins = (
        await db.scalars(
            select(User)
            .where(User.role == ADMIN, User.is_active.is_(True))
            .order_by(User.id)
            .with_for_update()
        )
    ).all()
    demo = _demo_emails()
    remaining = [a for a in admins if a.email.lower() not in demo]
    if removed:
        remaining = [a for a in remaining if a.id != target.id]
    return len(remaining)


async def _deny(db: AsyncSession, actor: User, target: User, action: str, cause: str, message: str):
    await log_action(
        db,
        f"{action}.denied",
        "User",
        str(target.id),
        actor_name=actor.name,
        actor_id=actor.id,
        metadata={"result": "denied", "cause": cause},
    )
    await db.commit()
    raise ConflictException(message)


def _touch(user: User, *, revoke_sessions: bool) -> None:
    user.row_version += 1
    user.updated_at = _now_naive()
    if revoke_sessions:
        user.session_version += 1


async def create_user(db: AsyncSession, actor: User, body: AdminUserCreate) -> User:
    if await _email_taken(db, body.email):
        raise ConflictException("Já existe um usuário com este e-mail")
    await _check_team(db, body.team_id)
    user = User(
        name=body.name.strip(),
        email=body.email.lower(),
        password_hash=hash_password(body.temporary_password),
        role=body.role.value,
        team_id=body.team_id,
        is_active=True,
        must_change_password=True,
        session_version=0,
        row_version=1,
    )
    db.add(user)
    await db.flush()
    await log_action(
        db,
        "user.created",
        "User",
        str(user.id),
        actor_name=actor.name,
        actor_id=actor.id,
        metadata={"result": "success", "role": user.role, "reason": body.reason},
    )
    return user


async def update_profile(
    db: AsyncSession, actor: User, user_id: uuid.UUID, body: AdminUserProfileUpdate
) -> User:
    user = await _lock_user(db, user_id)
    _check_version(user, body.expected_version)
    changes: dict[str, dict] = {}
    if body.name is not None and body.name.strip() != user.name:
        changes["name"] = {"from": user.name, "to": body.name.strip()}
        user.name = body.name.strip()
    if body.email is not None and body.email.lower() != user.email.lower():
        if await _email_taken(db, body.email, exclude=user.id):
            raise ConflictException("Já existe um usuário com este e-mail")
        changes["email"] = {"from": user.email, "to": body.email.lower()}
        user.email = body.email.lower()
    if "team_id" in body.model_fields_set and body.team_id != user.team_id:
        await _check_team(db, body.team_id)
        changes["team_id"] = {
            "from": str(user.team_id) if user.team_id else None,
            "to": str(body.team_id) if body.team_id else None,
        }
        user.team_id = body.team_id
    if not changes:
        return user
    _touch(user, revoke_sessions=False)
    await db.flush()
    await log_action(
        db,
        "user.profile_updated",
        "User",
        str(user.id),
        actor_name=actor.name,
        actor_id=actor.id,
        metadata={"result": "success", "changes": changes},
    )
    return user


async def change_role(
    db: AsyncSession, actor: User, user_id: uuid.UUID, body: AdminRoleChange
) -> User:
    await _serialize_admin_changes(db, actor)
    user = await _lock_user(db, user_id)
    _check_version(user, body.expected_version)
    await _step_up(db, actor, body.confirm_password, ACTION_ROLE_CHANGE, user)
    new_role = body.role.value
    if new_role == user.role:
        return user
    if user.id == actor.id:
        await _deny(
            db,
            actor,
            user,
            ACTION_ROLE_CHANGE,
            "self",
            "Você não pode alterar o próprio papel. Peça a outro administrador.",
        )
    if (
        user.role == ADMIN
        and user.is_active
        and (await _legitimate_admins_after(db, user, removed=True) == 0)
    ):
        await _deny(
            db,
            actor,
            user,
            ACTION_ROLE_CHANGE,
            "last_admin",
            "Este é o último administrador ativo: promova outro antes de rebaixá-lo.",
        )
    previous = user.role
    user.role = new_role
    _touch(user, revoke_sessions=True)
    await db.flush()
    await log_action(
        db,
        "user.role_changed",
        "User",
        str(user.id),
        actor_name=actor.name,
        actor_id=actor.id,
        metadata={"result": "success", "from": previous, "to": new_role, "reason": body.reason},
    )
    return user


async def set_active(
    db: AsyncSession, actor: User, user_id: uuid.UUID, body: AdminStatusChange, *, active: bool
) -> User:
    action = "user.activate" if active else "user.deactivate"
    await _serialize_admin_changes(db, actor)
    user = await _lock_user(db, user_id)
    _check_version(user, body.expected_version)
    await _step_up(db, actor, body.confirm_password, action, user)
    if user.is_active == active:
        return user
    if not active:
        if user.id == actor.id:
            await _deny(db, actor, user, action, "self", "Você não pode desativar a própria conta.")
        if user.role == ADMIN and await _legitimate_admins_after(db, user, removed=True) == 0:
            await _deny(
                db,
                actor,
                user,
                action,
                "last_admin",
                "Este é o último administrador ativo: ative ou promova outro antes.",
            )
    user.is_active = active
    # Deactivation ends open sessions; reactivation starts from a clean slate too.
    _touch(user, revoke_sessions=True)
    await db.flush()
    await log_action(
        db,
        "user.activated" if active else "user.deactivated",
        "User",
        str(user.id),
        actor_name=actor.name,
        actor_id=actor.id,
        metadata={"result": "success", "reason": body.reason},
    )
    return user


async def reset_password(
    db: AsyncSession, actor: User, user_id: uuid.UUID, body: AdminPasswordReset
) -> User:
    user = await _lock_user(db, user_id)
    _check_version(user, body.expected_version)
    await _step_up(db, actor, body.confirm_password, ACTION_PASSWORD_RESET, user)
    if user.id == actor.id:
        await _deny(
            db,
            actor,
            user,
            ACTION_PASSWORD_RESET,
            "self",
            'Para a própria senha, use "Trocar senha" no seu perfil.',
        )
    user.password_hash = hash_password(body.temporary_password)
    user.must_change_password = True
    _touch(user, revoke_sessions=True)
    await db.flush()
    await log_action(
        db,
        ACTION_PASSWORD_RESET,
        "User",
        str(user.id),
        actor_name=actor.name,
        actor_id=actor.id,
        metadata={"result": "success", "reason": body.reason},
    )
    return user
