from datetime import UTC, datetime, timedelta

from geoalchemy2 import WKTElement
from sqlalchemy.ext.asyncio import AsyncSession

from app.incidents.model import Incident, IncidentEvent
from app.protected_areas.model import ProtectedArea
from seed.base import get_or_none

INCIDENTS = [
    {
        "code": "IGN-CE-2026-0041",
        "title": "Queimada Crítica — RPPN Elias Andrade",
        "type": "fire",
        "severity": "critical",
        "status": "protocol_activated",
        "area_name": "RPPN Elias Andrade",
        "latitude": -4.9736,
        "longitude": -39.0156,
        "source": "satellite",
        "confidence": 0.95,
        "affected_hectares": 87.3,
        "wind_direction": "NE",
        "wind_speed": 18.5,
        "humidity": 28.0,
        "temperature": 36.5,
    },
    {
        "code": "IGN-CE-2026-0040",
        "title": "Desmatamento Ilegal — APA Baturité",
        "type": "deforestation",
        "severity": "high",
        "status": "monitoring",
        "area_name": "APA da Serra de Baturité",
        "latitude": -4.2174,
        "longitude": -38.9286,
        "source": "patrol",
        "confidence": 0.82,
        "affected_hectares": 12.5,
        "wind_direction": None,
        "wind_speed": None,
        "humidity": 65.0,
        "temperature": 29.0,
    },
    {
        "code": "IGN-CE-2026-0039",
        "title": "Foco de Calor — FLONA Araripe",
        "type": "fire",
        "severity": "medium",
        "status": "active",
        "area_name": "FLONA Araripe-Apodi",
        "latitude": -7.2475,
        "longitude": -39.4286,
        "source": "sensor",
        "confidence": 0.75,
        "affected_hectares": 3.2,
        "wind_direction": "SE",
        "wind_speed": 12.0,
        "humidity": 42.0,
        "temperature": 34.0,
    },
    {
        "code": "IGN-CE-2026-0038",
        "title": "Poluição Hídrica — APA Estuário",
        "type": "pollution",
        "severity": "high",
        "status": "monitoring",
        "area_name": "APA do Estuário do Rio Ceará",
        "latitude": -3.7047,
        "longitude": -38.6478,
        "source": "report",
        "confidence": 0.68,
        "affected_hectares": None,
        "wind_direction": None,
        "wind_speed": None,
        "humidity": 78.0,
        "temperature": 31.0,
    },
    {
        "code": "IGN-CE-2026-0037",
        "title": "Caça Ilegal — Parque Nacional Ubajara",
        "type": "other",
        "severity": "medium",
        "status": "resolved",
        "area_name": "Parque Nacional de Ubajara",
        "latitude": -3.8372,
        "longitude": -40.9019,
        "source": "patrol",
        "confidence": 0.90,
        "affected_hectares": None,
        "wind_direction": None,
        "wind_speed": None,
        "humidity": 70.0,
        "temperature": 27.0,
    },
]

EVENTS_0041 = [
    {
        "type": "detection",
        "actor_name": "Sistema INPE",
        "description": "Foco de calor detectado por satélite",
    },
    {
        "type": "validation",
        "actor_name": "Gestor SEMACE",
        "description": "Ocorrência validada e confirmada em campo",
    },
    {
        "type": "protocol_activated",
        "actor_name": "Gestor SEMACE",
        "description": "Protocolo de emergência ativado — brigadas mobilizadas",
    },
    {
        "type": "update",
        "actor_name": "Brigada Alfa",
        "description": "Equipe chegou ao local — 87ha comprometidos",
    },
]


async def seed_incidents(db: AsyncSession) -> None:
    print("  -> Seeding incidents...")
    now = datetime.now(UTC)

    for i, inc in enumerate(INCIDENTS):
        existing = await get_or_none(db, Incident, code=inc["code"])
        if existing is not None:
            continue

        area = await get_or_none(db, ProtectedArea, name=inc["area_name"])
        if area is None:
            area_name = inc["area_name"]
            code = inc["code"]
            print(f"  -> WARNING: area '{area_name}' not found, skipping incident {code}")
            continue

        lat = inc["latitude"]
        lng = inc["longitude"]
        incident = Incident(
            code=inc["code"],
            title=inc["title"],
            type=inc["type"],
            severity=inc["severity"],
            status=inc["status"],
            protected_area_id=area.id,
            latitude=lat,
            longitude=lng,
            location=WKTElement(f"POINT({lng} {lat})", srid=4326),
            source=inc["source"],
            confidence=inc["confidence"],
            affected_hectares=inc["affected_hectares"],
            wind_direction=inc["wind_direction"],
            wind_speed=inc["wind_speed"],
            humidity=inc["humidity"],
            temperature=inc["temperature"],
            detected_at=now - timedelta(hours=i * 6),
        )
        db.add(incident)

    await db.flush()

    # Adiciona eventos ao incidente principal
    incident_0041 = await get_or_none(db, Incident, code="IGN-CE-2026-0041")
    if incident_0041 is not None:
        for j, ev in enumerate(EVENTS_0041):
            event = IncidentEvent(
                incident_id=incident_0041.id,
                type=ev["type"],
                actor_name=ev["actor_name"],
                description=ev["description"],
                timestamp=now - timedelta(hours=12 - j * 3),
            )
            db.add(event)
        await db.flush()

    print(f"  -> Incidents OK ({len(INCIDENTS)} entries checked)")
