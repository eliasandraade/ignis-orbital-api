from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.esg.model import ESGReport
from app.protected_areas.model import ProtectedArea
from seed.base import get_or_none

ESG = {
    "area_name": "RPPN Elias Andrade",
    "period_start": datetime(2026, 1, 1, tzinfo=UTC),
    "period_end": datetime(2026, 5, 29, tzinfo=UTC),
    "monitored_area_ha": 1250.5,
    "incidents_resolved": 12,
    "average_response_minutes": 47.3,
    "heat_spots_detected": 23,
    "vegetation_loss_estimated_ha": 87.3,
    "prevented_impact_estimate": "Ação rápida evitou expansão estimada em 320ha adicionais",
    "ods": {
        "ods_2": False,
        "ods_8": False,
        "ods_9": True,
        "ods_11": True,
        "ods_13": True,
        "ods_15": True,
    },
}


async def seed_esg(db: AsyncSession) -> None:
    print("  -> Seeding ESG reports...")

    area = await get_or_none(db, ProtectedArea, name=ESG["area_name"])

    report = ESGReport(
        protected_area_id=area.id if area else None,
        period_start=ESG["period_start"],
        period_end=ESG["period_end"],
        monitored_area_ha=ESG["monitored_area_ha"],
        incidents_resolved=ESG["incidents_resolved"],
        average_response_minutes=ESG["average_response_minutes"],
        heat_spots_detected=ESG["heat_spots_detected"],
        vegetation_loss_estimated_ha=ESG["vegetation_loss_estimated_ha"],
        prevented_impact_estimate=ESG["prevented_impact_estimate"],
        ods=ESG["ods"],
    )
    db.add(report)
    await db.flush()
    print("  -> ESG reports OK (1 entry added)")
