"""Official jurisdictions (IBGE Malha Municipal) — public, read-only."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import rate_limit
from app.database import get_db
from app.orbital import queries
from app.orbital.read_schemas import MunicipalityList

router = APIRouter(prefix="/api/v1/jurisdictions", tags=["jurisdictions"])

_GEOJSON_CACHE: dict[str, str] = {}
_GEOJSON_CACHE_MAX = 16


@router.get(
    "/municipalities",
    dependencies=[Depends(rate_limit("jurisdictions", limit=60, window_seconds=60))],
    responses={
        503: {"description": "Malha oficial ainda não importada"},
        422: {"description": "Filtro inválido"},
    },
)
async def list_municipalities(
    observed_from: datetime | None = Query(None, alias="from"),
    observed_to: datetime | None = Query(None, alias="to"),
    source: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> MunicipalityList:
    """The 184 official municipalities of Ceará with detection counts in the window."""
    try:
        f = queries.build_filters(
            observed_from=observed_from,
            observed_to=observed_to,
            source=source,
            satellite=None,
            jurisdiction=None,
            bbox=None,
        )
    except queries.FilterError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = await queries.list_municipalities(db, f)
    if result is None:
        raise HTTPException(status_code=503, detail="Malha oficial do IBGE não importada")
    return result


@router.get(
    "/geojson",
    dependencies=[Depends(rate_limit("jurisdictions-geojson", limit=30, window_seconds=60))],
    responses={
        200: {"content": {"application/geo+json": {}}, "description": "FeatureCollection"},
        503: {"description": "Malha oficial ainda não importada"},
    },
)
async def jurisdictions_geojson(
    request: Request,
    level: Literal["state", "municipality"] = Query("municipality"),
    tolerance: float = Query(
        0.0005,
        ge=0,
        le=0.01,
        description="Simplificação só para exibição, em graus (0 = geometria oficial completa)",
    ),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Official boundaries as GeoJSON (SRID 4326), with the IBGE dataset version."""
    dataset = await queries.current_dataset(db)
    if dataset is None:
        raise HTTPException(status_code=503, detail="Malha oficial do IBGE não importada")
    etag = f'"{dataset.content_sha256[:16]}-{level}-{tolerance:g}"'
    headers = {"ETag": etag, "Cache-Control": "public, max-age=3600"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    body = _GEOJSON_CACHE.get(etag)
    if body is None:
        # Measured: ~330 ms to simplify the 184 polygons; the mesh only changes
        # with a new IBGE dataset, whose hash is part of the key.
        body = await queries.jurisdictions_geojson(db, level, tolerance)
        if len(_GEOJSON_CACHE) >= _GEOJSON_CACHE_MAX:
            _GEOJSON_CACHE.clear()
        _GEOJSON_CACHE[etag] = body
    return Response(content=body, media_type="application/geo+json", headers=headers)
