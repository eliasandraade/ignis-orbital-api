import random
import string

from geoalchemy2 import WKTElement
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.incidents.model import Incident
from app.protected_areas.model import ProtectedArea
from app.reports.model import PublicReport
from seed.base import get_or_none

REPORTER_NAMES = [
    "João Silva",
    "Maria Santos",
    "Carlos Oliveira",
    "Ana Ferreira",
    "Pedro Costa",
    "Lucia Alves",
    "Roberto Lima",
    "Fernanda Souza",
    "Marcos Rodrigues",
    "Paula Mendes",
]

REPORTER_CONTACTS = [
    "joao.silva@email.com",
    "maria.santos@email.com",
    "carlos.oliveira@email.com",
    "ana.ferreira@email.com",
    "pedro.costa@email.com",
    "lucia.alves@email.com",
    "roberto.lima@email.com",
    "fernanda.souza@email.com",
    "marcos.rodrigues@email.com",
    "paula.mendes@email.com",
]

REPORTS_DATA = [
    {
        "type": "fire",
        "urgency": "critical",
        "description": "Incêndio de grandes proporções na Serra",
        "lat": -4.97,
        "lng": -39.01,
        "area_name": "RPPN Elias Andrade",
        "status": "converted",
    },
    {
        "type": "deforestation",
        "urgency": "high",
        "description": "Desmatamento ilegal detectado",
        "lat": -4.21,
        "lng": -38.93,
        "area_name": "APA da Serra de Baturité",
        "status": "validated",
    },
    {
        "type": "illegal_mining",
        "urgency": "high",
        "description": "Garimpo clandestino próximo ao rio",
        "lat": -7.24,
        "lng": -39.43,
        "area_name": "FLONA Araripe-Apodi",
        "status": "validated",
    },
    {
        "type": "pollution",
        "urgency": "medium",
        "description": "Descarte ilegal de resíduos",
        "lat": -3.70,
        "lng": -38.65,
        "area_name": "APA do Estuário do Rio Ceará",
        "status": "validated",
    },
    {
        "type": "fire",
        "urgency": "high",
        "description": "Fumaça vista na região norte do parque",
        "lat": -3.84,
        "lng": -40.90,
        "area_name": "Parque Nacional de Ubajara",
        "status": "pending",
    },
    {
        "type": "deforestation",
        "urgency": "medium",
        "description": "Área desmatada para pastagem",
        "lat": -3.79,
        "lng": -38.48,
        "area_name": "Parque Estadual do Cocó",
        "status": "pending",
    },
    {
        "type": "wildlife_traffic",
        "urgency": "high",
        "description": "Suspeita de tráfico de fauna silvestre",
        "lat": -3.54,
        "lng": -38.78,
        "area_name": "Estação Ecológica do Pecém",
        "status": "pending",
    },
    {
        "type": "illegal_mining",
        "urgency": "critical",
        "description": "Extração ilegal de areia no estuário",
        "lat": -3.71,
        "lng": -38.64,
        "area_name": "APA do Estuário do Rio Ceará",
        "status": "pending",
    },
    {
        "type": "fire",
        "urgency": "low",
        "description": "Queimada controlada fora dos limites",
        "lat": -7.33,
        "lng": -39.30,
        "area_name": "APA da Chapada do Araripe",
        "status": "discarded",
        "validation_notes": "Queima controlada autorizada pela prefeitura",
    },
    {
        "type": "pollution",
        "urgency": "low",
        "description": "Lixo jogado na estrada de acesso",
        "lat": -4.95,
        "lng": -39.00,
        "area_name": "RPPN Elias Andrade",
        "status": "discarded",
        "validation_notes": "Fora dos limites da área protegida",
    },
    {
        "type": "deforestation",
        "urgency": "high",
        "description": "Corte de árvores nativas observado",
        "lat": -4.22,
        "lng": -38.94,
        "area_name": "APA da Serra de Baturité",
        "status": "pending",
        "is_anonymous": True,
    },
    {
        "type": "fire",
        "urgency": "medium",
        "description": "Fogueira de camping próxima à vegetação",
        "lat": -7.25,
        "lng": -39.42,
        "area_name": "FLONA Araripe-Apodi",
        "status": "pending",
        "is_anonymous": True,
    },
]


def generate_protocol() -> str:
    chars = random.choices(string.ascii_uppercase + string.digits, k=4)
    return f"RP-20260529-{''.join(chars)}"


async def seed_reports(db: AsyncSession) -> None:
    print("  -> Seeding public reports...")

    incident_0041 = await get_or_none(db, Incident, code="IGN-CE-2026-0041")

    reporter_idx = 0
    added = 0
    for report_data in REPORTS_DATA:
        # Deduplication: skip if a report with the same type and description already exists
        result = await db.execute(
            select(PublicReport).where(
                PublicReport.type == report_data["type"],
                PublicReport.description == report_data["description"],
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            if not report_data.get("is_anonymous", False):
                reporter_idx += 1
            continue

        area = await get_or_none(db, ProtectedArea, name=report_data["area_name"])
        is_anonymous = report_data.get("is_anonymous", False)
        status = report_data["status"]
        validation_notes = report_data.get("validation_notes", None)

        # Generate a unique protocol
        protocol = generate_protocol()
        # Ensure uniqueness (very unlikely collision but be safe)
        while await get_or_none(db, PublicReport, protocol=protocol) is not None:
            protocol = generate_protocol()

        reporter_name = None
        contact = None
        if not is_anonymous:
            reporter_name = REPORTER_NAMES[reporter_idx % len(REPORTER_NAMES)]
            contact = REPORTER_CONTACTS[reporter_idx % len(REPORTER_CONTACTS)]
            reporter_idx += 1

        linked_incident_id = None
        if status == "converted" and incident_0041 is not None:
            linked_incident_id = incident_0041.id

        lat = report_data["lat"]
        lng = report_data["lng"]

        report = PublicReport(
            protocol=protocol,
            type=report_data["type"],
            description=report_data["description"],
            urgency=report_data["urgency"],
            status=status,
            reporter_name=reporter_name,
            contact=contact,
            is_anonymous=is_anonymous,
            latitude=lat,
            longitude=lng,
            location=WKTElement(f"POINT({lng} {lat})", srid=4326),
            protected_area_id=area.id if area else None,
            validation_notes=validation_notes,
            linked_incident_id=linked_incident_id,
            evidence_urls=[],
        )
        db.add(report)
        added += 1

    await db.flush()
    print(f"  -> Public reports OK ({added} entries added, {len(REPORTS_DATA) - added} skipped)")
