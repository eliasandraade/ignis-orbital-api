from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def get_or_none(db: AsyncSession, model, **kwargs):
    """Retorna instância existente ou None."""
    result = await db.execute(select(model).filter_by(**kwargs))
    return result.scalar_one_or_none()
