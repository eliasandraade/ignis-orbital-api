from geoalchemy2 import WKTElement
from sqlalchemy.ext.asyncio import AsyncSession

from app.protected_areas.model import ProtectedArea
from seed.base import get_or_none

AREAS = [
    {
        "name": "RPPN Elias Andrade",
        "category": "RPPN",
        "municipality": "Quixadá",
        "state": "CE",
        "organ": "SEMACE",
        "area_ha": 1250.5,
        "center_lat": -4.9736,
        "center_lng": -39.0156,
        "source": "base demonstrativa acadêmica",
        "data_quality": "estimated",
        "confidence": 0.7,
        "geometry_wkt": "MULTIPOLYGON(((-39.06 -5.02, -38.97 -5.02, -38.97 -4.93, -39.06 -4.93, -39.06 -5.02)))",  # noqa: E501
        "buffer_wkt": "MULTIPOLYGON(((-39.07 -5.03, -38.96 -5.03, -38.96 -4.92, -39.07 -4.92, -39.07 -5.03)))",  # noqa: E501
    },
    {
        "name": "APA da Serra de Baturité",
        "category": "APA",
        "municipality": "Guaramiranga",
        "state": "CE",
        "organ": "SEMACE",
        "area_ha": 32690.0,
        "center_lat": -4.2174,
        "center_lng": -38.9286,
        "source": "base demonstrativa acadêmica",
        "data_quality": "estimated",
        "confidence": 0.7,
        "geometry_wkt": "MULTIPOLYGON(((-39.05 -4.38, -38.80 -4.38, -38.80 -4.05, -39.05 -4.05, -39.05 -4.38)))",  # noqa: E501
        "buffer_wkt": "MULTIPOLYGON(((-39.07 -4.40, -38.78 -4.40, -38.78 -4.03, -39.07 -4.03, -39.07 -4.40)))",  # noqa: E501
    },
    {
        "name": "Parque Estadual do Cocó",
        "category": "PE",
        "municipality": "Fortaleza",
        "state": "CE",
        "organ": "SEMACE",
        "area_ha": 1155.0,
        "center_lat": -3.7836,
        "center_lng": -38.4847,
        "source": "base demonstrativa acadêmica",
        "data_quality": "estimated",
        "confidence": 0.7,
        "geometry_wkt": "MULTIPOLYGON(((-38.52 -3.81, -38.45 -3.81, -38.45 -3.76, -38.52 -3.76, -38.52 -3.81)))",  # noqa: E501
        "buffer_wkt": "MULTIPOLYGON(((-38.53 -3.82, -38.44 -3.82, -38.44 -3.75, -38.53 -3.75, -38.53 -3.82)))",  # noqa: E501
    },
    {
        "name": "Estação Ecológica do Pecém",
        "category": "ESEC",
        "municipality": "São Gonçalo do Amarante",
        "state": "CE",
        "organ": "ICMBio",
        "area_ha": 746.0,
        "center_lat": -3.5381,
        "center_lng": -38.7847,
        "source": "base demonstrativa acadêmica",
        "data_quality": "estimated",
        "confidence": 0.7,
        "geometry_wkt": "MULTIPOLYGON(((-38.82 -3.56, -38.75 -3.56, -38.75 -3.52, -38.82 -3.52, -38.82 -3.56)))",  # noqa: E501
        "buffer_wkt": "MULTIPOLYGON(((-38.83 -3.57, -38.74 -3.57, -38.74 -3.51, -38.83 -3.51, -38.83 -3.57)))",  # noqa: E501
    },
    {
        "name": "FLONA Araripe-Apodi",
        "category": "FLONA",
        "municipality": "Crato",
        "state": "CE",
        "organ": "ICMBio",
        "area_ha": 38262.0,
        "center_lat": -7.2475,
        "center_lng": -39.4286,
        "source": "base demonstrativa acadêmica",
        "data_quality": "estimated",
        "confidence": 0.7,
        "geometry_wkt": "MULTIPOLYGON(((-39.70 -7.40, -39.15 -7.40, -39.15 -7.10, -39.70 -7.10, -39.70 -7.40)))",  # noqa: E501
        "buffer_wkt": "MULTIPOLYGON(((-39.72 -7.42, -39.13 -7.42, -39.13 -7.08, -39.72 -7.08, -39.72 -7.42)))",  # noqa: E501
    },
    {
        "name": "Parque Nacional de Ubajara",
        "category": "PARNA",
        "municipality": "Ubajara",
        "state": "CE",
        "organ": "ICMBio",
        "area_ha": 6288.0,
        "center_lat": -3.8372,
        "center_lng": -40.9019,
        "source": "base demonstrativa acadêmica",
        "data_quality": "estimated",
        "confidence": 0.7,
        "geometry_wkt": "MULTIPOLYGON(((-40.95 -3.87, -40.86 -3.87, -40.86 -3.81, -40.95 -3.81, -40.95 -3.87)))",  # noqa: E501
        "buffer_wkt": "MULTIPOLYGON(((-40.97 -3.89, -40.84 -3.89, -40.84 -3.79, -40.97 -3.79, -40.97 -3.89)))",  # noqa: E501
    },
    {
        "name": "APA da Chapada do Araripe",
        "category": "APA",
        "municipality": "Barbalha",
        "state": "CE",
        "organ": "ICMBio",
        "area_ha": 1066860.0,
        "center_lat": -7.3286,
        "center_lng": -39.3047,
        "source": "base demonstrativa acadêmica",
        "data_quality": "estimated",
        "confidence": 0.7,
        "geometry_wkt": "MULTIPOLYGON(((-40.50 -7.60, -38.10 -7.60, -38.10 -7.05, -40.50 -7.05, -40.50 -7.60)))",  # noqa: E501
        "buffer_wkt": "MULTIPOLYGON(((-40.52 -7.62, -38.08 -7.62, -38.08 -7.03, -40.52 -7.03, -40.52 -7.62)))",  # noqa: E501
    },
    {
        "name": "APA do Estuário do Rio Ceará",
        "category": "APA",
        "municipality": "Caucaia",
        "state": "CE",
        "organ": "SEMACE",
        "area_ha": 2380.0,
        "center_lat": -3.7047,
        "center_lng": -38.6478,
        "source": "base demonstrativa acadêmica",
        "data_quality": "estimated",
        "confidence": 0.7,
        "geometry_wkt": "MULTIPOLYGON(((-38.72 -3.73, -38.58 -3.73, -38.58 -3.68, -38.72 -3.68, -38.72 -3.73)))",  # noqa: E501
        "buffer_wkt": "MULTIPOLYGON(((-38.73 -3.74, -38.57 -3.74, -38.57 -3.67, -38.73 -3.67, -38.73 -3.74)))",  # noqa: E501
    },
]


async def seed_areas(db: AsyncSession) -> None:
    print("  -> Seeding protected areas...")
    for item in AREAS:
        existing = await get_or_none(db, ProtectedArea, name=item["name"])
        if existing is None:
            area = ProtectedArea(
                name=item["name"],
                category=item["category"],
                municipality=item["municipality"],
                state=item["state"],
                organ=item["organ"],
                area_ha=item["area_ha"],
                center_lat=item["center_lat"],
                center_lng=item["center_lng"],
                source=item["source"],
                data_quality=item["data_quality"],
                confidence=item["confidence"],
                geometry=WKTElement(item["geometry_wkt"], srid=4326),
                buffer_zone=WKTElement(item["buffer_wkt"], srid=4326),
            )
            db.add(area)
    await db.flush()
    print(f"  -> Protected areas OK ({len(AREAS)} entries checked)")
