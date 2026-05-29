from sqlalchemy.ext.asyncio import AsyncSession

from app.incidents.model import Incident
from app.resources.model import Resource
from seed.base import get_or_none

RESOURCES = [
    {
        "name": "Caminhão-Pipa 01",
        "type": "vehicle",
        "status": "in_use",
        "quantity": 1,
        "location": "RPPN Elias Andrade",
    },
    {
        "name": "Caminhão-Pipa 02",
        "type": "vehicle",
        "status": "available",
        "quantity": 1,
        "location": "Base Quixadá",
    },
    {
        "name": "Drone DJI Matrice 300",
        "type": "drone",
        "status": "in_use",
        "quantity": 1,
        "location": "RPPN Elias Andrade",
    },
    {
        "name": "Drone DJI Mini 4 Pro",
        "type": "drone",
        "status": "available",
        "quantity": 1,
        "location": "Base Fortaleza",
    },
    {
        "name": "Veículo 4x4 Hilux",
        "type": "vehicle",
        "status": "in_use",
        "quantity": 1,
        "location": "APA Baturité",
    },
    {
        "name": "Brigada Voluntária CE-01",
        "type": "personnel",
        "status": "available",
        "quantity": 12,
        "location": "Base Crato",
    },
    {
        "name": "Kit Contenção Química",
        "type": "equipment",
        "status": "available",
        "quantity": 3,
        "location": "Base Fortaleza",
    },
    {
        "name": "Rádio Comunicador Motorola",
        "type": "equipment",
        "status": "in_use",
        "quantity": 8,
        "location": "Campo",
    },
]


async def seed_resources(db: AsyncSession) -> None:
    print("  -> Seeding resources...")

    incident_0041 = await get_or_none(db, Incident, code="IGN-CE-2026-0041")

    for res in RESOURCES:
        existing = await get_or_none(db, Resource, name=res["name"])
        if existing is not None:
            continue

        assigned_incident_id = None
        if res["status"] == "in_use" and res["location"] == "RPPN Elias Andrade" and incident_0041:
            assigned_incident_id = incident_0041.id

        resource = Resource(
            name=res["name"],
            type=res["type"],
            status=res["status"],
            quantity=res["quantity"],
            location=res["location"],
            assigned_incident_id=assigned_incident_id,
        )
        db.add(resource)

    await db.flush()
    print(f"  -> Resources OK ({len(RESOURCES)} entries checked)")
