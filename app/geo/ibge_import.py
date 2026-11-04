"""Import the official IBGE municipal mesh (Malha Municipal Digital) of a state.

Reproducible: the published zip files are versioned in data/reference/ibge/
together with a MANIFEST.json (URL, SHA-256, version, reference date); nothing
is downloaded at import time and a file whose hash differs is refused.

Idempotent: rows are keyed by IBGE code and only rewritten when something
actually changed, so a second run reports every row as unchanged.

Auditable: the dataset row keeps the provenance, each jurisdiction keeps the
published attributes untouched, and every execution writes an audit_logs entry.

Fail-closed: a wrong count, a code outside the state, an invalid geometry or an
unexpected CRS aborts the whole transaction; nothing is "fixed" silently.
"""

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

import shapefile
from shapely.geometry import MultiPolygon, Polygon, shape
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

IMPORTER_VERSION = "1"
DATA_ROOT = Path(__file__).resolve().parents[2] / "data" / "reference" / "ibge"
DEFAULT_DATASET_DIR = DATA_ROOT / "malha_municipal_2025"
SIRGAS_2000_PRJ_MARKERS = ("GCS_SIRGAS_2000", "D_SIRGAS_2000")
_LOCK_KEY = "ignis:jurisdictions:import"


class DatasetIntegrityError(ValueError):
    """The files on disk are not the ones the manifest describes."""


@dataclass(frozen=True, slots=True)
class Feature:
    ibge_code: str
    name: str
    area_km2: Decimal
    wkb_hex: str
    attributes: dict


@dataclass(frozen=True, slots=True)
class Manifest:
    path: Path
    raw: dict

    @property
    def files(self) -> list[dict]:
        return self.raw["files"]

    def file(self, role: str) -> dict:
        matches = [f for f in self.files if f["role"] == role]
        if len(matches) != 1:
            raise DatasetIntegrityError(f"manifesto sem arquivo único com papel {role!r}")
        return matches[0]

    @property
    def content_sha256(self) -> str:
        joined = "\n".join(sorted(f"{f['name']}:{f['sha256']}" for f in self.files))
        return hashlib.sha256(joined.encode()).hexdigest()


@dataclass(slots=True)
class ImportReport:
    dataset_id: str = ""
    dataset_created: bool = False
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    municipalities: int = 0
    not_in_dataset: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "dataset_id": self.dataset_id,
            "dataset_created": self.dataset_created,
            "inserted": self.inserted,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "municipalities": self.municipalities,
            "not_in_dataset": self.not_in_dataset,
        }


def load_manifest(dataset_dir: Path = DEFAULT_DATASET_DIR) -> Manifest:
    path = dataset_dir / "MANIFEST.json"
    return Manifest(path=path, raw=json.loads(path.read_text(encoding="utf-8")))


def verify_files(manifest: Manifest) -> None:
    for entry in manifest.files:
        payload = (manifest.path.parent / entry["name"]).read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if digest != entry["sha256"] or len(payload) != entry["bytes"]:
            raise DatasetIntegrityError(
                f"{entry['name']}: SHA-256 {digest} ({len(payload)} bytes) difere do manifesto"
            )


def _as_multipolygon(geometry) -> MultiPolygon:
    if isinstance(geometry, Polygon):
        return MultiPolygon([geometry])
    if isinstance(geometry, MultiPolygon):
        return geometry
    raise DatasetIntegrityError(f"geometria inesperada: {geometry.geom_type}")


def read_layer(manifest: Manifest, role: str, code_field: str, name_field: str) -> list[Feature]:
    entry = manifest.file(role)
    layer = entry["layer"]
    with zipfile.ZipFile(manifest.path.parent / entry["name"]) as archive:
        prj = archive.read(f"{layer}.prj").decode("ascii", "replace")
        if not all(marker in prj for marker in SIRGAS_2000_PRJ_MARKERS):
            raise DatasetIntegrityError(f"{layer}: CRS diferente de SIRGAS 2000: {prj!r}")
        encoding = archive.read(f"{layer}.cpg").decode("ascii").strip()
        reader = shapefile.Reader(
            shp=io.BytesIO(archive.read(f"{layer}.shp")),
            shx=io.BytesIO(archive.read(f"{layer}.shx")),
            dbf=io.BytesIO(archive.read(f"{layer}.dbf")),
            encoding=encoding,
        )
        features = []
        for record in reader.iterShapeRecords():
            attributes = record.record.as_dict()
            geometry = _as_multipolygon(shape(record.shape.__geo_interface__))
            code = str(attributes[code_field])
            if not geometry.is_valid or geometry.is_empty:
                raise DatasetIntegrityError(f"{layer} {code}: geometria inválida no arquivo")
            features.append(
                Feature(
                    ibge_code=code,
                    name=str(attributes[name_field]).strip(),
                    area_km2=Decimal(str(attributes["AREA_KM2"])),
                    wkb_hex=geometry.wkb_hex,
                    attributes={k: _json_safe(v) for k, v in attributes.items()},
                )
            )
    return features


def _json_safe(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def validate_features(manifest: Manifest, state: list[Feature], municipalities: list[Feature]):
    expected = manifest.raw["state"]
    if len(state) != 1 or state[0].ibge_code != expected["ibge_code"]:
        raise DatasetIntegrityError(f"camada da UF deveria ter só o código {expected['ibge_code']}")
    codes = [m.ibge_code for m in municipalities]
    if len(codes) != expected["expected_municipalities"]:
        raise DatasetIntegrityError(
            f"{len(codes)} municípios no arquivo; esperado {expected['expected_municipalities']}"
        )
    if len(set(codes)) != len(codes):
        raise DatasetIntegrityError("códigos IBGE de município repetidos")
    foreign = [c for c in codes if len(c) != 7 or not c.startswith(expected["ibge_code"])]
    if foreign:
        raise DatasetIntegrityError(f"códigos fora da UF {expected['ibge_code']}: {foreign}")
    wrong_uf = [
        m.ibge_code
        for m in municipalities
        if m.attributes.get("SIGLA_UF") != expected["abbreviation"]
    ]
    if wrong_uf:
        raise DatasetIntegrityError(f"municípios com SIGLA_UF diferente: {wrong_uf}")


_UPSERT = text(
    """
INSERT INTO jurisdictions (
    level, ibge_code, name, state_ibge_code, state_abbreviation, parent_id,
    official_area_km2, geom, dataset_id, source_attributes
)
VALUES (
    :level, :ibge_code, :name, :state_ibge_code, :state_abbreviation, CAST(:parent_id AS uuid),
    :area, ST_Multi(ST_Transform(ST_SetSRID(ST_GeomFromWKB(decode(:wkb, 'hex')), 4674), 4326)),
    CAST(:dataset_id AS uuid), CAST(:attributes AS jsonb)
)
ON CONFLICT (ibge_code) DO UPDATE SET
    level = EXCLUDED.level,
    name = EXCLUDED.name,
    state_ibge_code = EXCLUDED.state_ibge_code,
    state_abbreviation = EXCLUDED.state_abbreviation,
    parent_id = EXCLUDED.parent_id,
    official_area_km2 = EXCLUDED.official_area_km2,
    geom = EXCLUDED.geom,
    dataset_id = EXCLUDED.dataset_id,
    source_attributes = EXCLUDED.source_attributes,
    updated_at = now()
WHERE (jurisdictions.level, jurisdictions.name, jurisdictions.parent_id,
       jurisdictions.official_area_km2, jurisdictions.dataset_id,
       jurisdictions.source_attributes)
      IS DISTINCT FROM
      (EXCLUDED.level, EXCLUDED.name, EXCLUDED.parent_id,
       EXCLUDED.official_area_km2, EXCLUDED.dataset_id, EXCLUDED.source_attributes)
   OR NOT ST_OrderingEquals(jurisdictions.geom, EXCLUDED.geom)
RETURNING id, (xmax = 0) AS inserted
"""
)


async def _upsert(session: AsyncSession, report: ImportReport, **values) -> str | None:
    row = (await session.execute(_UPSERT, values)).one_or_none()
    if row is None:
        report.unchanged += 1
        return None
    if row.inserted:
        report.inserted += 1
    else:
        report.updated += 1
    return str(row.id)


async def import_state(
    session: AsyncSession, dataset_dir: Path = DEFAULT_DATASET_DIR
) -> ImportReport:
    """Import one state and its municipalities inside the caller's transaction.

    Concurrent executions serialise on a transaction-scoped advisory lock;
    the second one finds everything in place and changes nothing.
    """
    manifest = load_manifest(dataset_dir)
    verify_files(manifest)
    state = read_layer(manifest, "state", "CD_UF", "NM_UF")
    municipalities = read_layer(manifest, "municipalities", "CD_MUN", "NM_MUN")
    validate_features(manifest, state, municipalities)

    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": _LOCK_KEY}
    )
    report = ImportReport(municipalities=len(municipalities))
    raw = manifest.raw
    dataset = (
        await session.execute(
            text(
                """
INSERT INTO reference_datasets (
    id, source, product, version, reference_date, source_crs, content_sha256,
    files, feature_count, license_note, importer_version
)
VALUES (gen_random_uuid(), :source, :product, :version, :reference_date, :source_crs,
        :sha, CAST(:files AS jsonb), :feature_count, :license_note, :importer_version)
ON CONFLICT (content_sha256) DO NOTHING
RETURNING id
"""
            ),
            {
                "source": raw["source"],
                "product": raw["product"],
                "version": raw["version"],
                "reference_date": date.fromisoformat(raw["reference_date"]),
                "source_crs": raw["source_crs"],
                "sha": manifest.content_sha256,
                "files": json.dumps(raw["files"]),
                "feature_count": len(state) + len(municipalities),
                "license_note": raw["license_note"],
                "importer_version": IMPORTER_VERSION,
            },
        )
    ).scalar_one_or_none()
    report.dataset_created = dataset is not None
    report.dataset_id = str(
        dataset
        or await session.scalar(
            text("SELECT id FROM reference_datasets WHERE content_sha256 = :sha"),
            {"sha": manifest.content_sha256},
        )
    )

    uf = raw["state"]
    common = {
        "state_ibge_code": uf["ibge_code"],
        "state_abbreviation": uf["abbreviation"],
        "dataset_id": report.dataset_id,
    }
    state_feature = state[0]
    await _upsert(
        session,
        report,
        level="state",
        ibge_code=state_feature.ibge_code,
        name=state_feature.name,
        parent_id=None,
        area=state_feature.area_km2,
        wkb=state_feature.wkb_hex,
        attributes=json.dumps(state_feature.attributes, sort_keys=True),
        **common,
    )
    state_id = str(
        await session.scalar(
            text("SELECT id FROM jurisdictions WHERE ibge_code = :code"),
            {"code": state_feature.ibge_code},
        )
    )
    for feature in municipalities:
        await _upsert(
            session,
            report,
            level="municipality",
            ibge_code=feature.ibge_code,
            name=feature.name,
            parent_id=state_id,
            area=feature.area_km2,
            wkb=feature.wkb_hex,
            attributes=json.dumps(feature.attributes, sort_keys=True),
            **common,
        )

    # Municipalities that disappeared from a newer mesh are reported, never
    # deleted: detections reference them (ON DELETE RESTRICT).
    known = {m.ibge_code for m in municipalities}
    stored = (
        await session.scalars(
            text(
                "SELECT ibge_code FROM jurisdictions"
                " WHERE level = 'municipality' AND state_ibge_code = :uf"
            ),
            {"uf": uf["ibge_code"]},
        )
    ).all()
    report.not_in_dataset = sorted(set(stored) - known)

    from app.core.audit import log_action

    await log_action(
        session,
        "jurisdictions.imported",
        "ReferenceDataset",
        report.dataset_id,
        actor_name="ops:seed.jurisdictions",
        metadata={
            "source": raw["source"],
            "product": raw["product"],
            "version": raw["version"],
            "reference_date": raw["reference_date"],
            "content_sha256": manifest.content_sha256,
            "importer_version": IMPORTER_VERSION,
            **report.as_dict(),
        },
    )
    await session.flush()
    return report
