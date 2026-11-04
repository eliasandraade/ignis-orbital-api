"""Sprint 1.1 — contracts and IBGE files, without a database."""

import json
import math
import shutil
import uuid
import zipfile
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.geo import ibge_import
from app.geo.ibge_import import (
    DatasetIntegrityError,
    load_manifest,
    read_layer,
    validate_features,
    verify_files,
)
from app.orbital.contracts import (
    CEARA_BBOX,
    DetectionSource,
    InvalidDetectionError,
    NormalizedDetection,
    ProviderResult,
    TimeWindow,
    compute_dedup_key,
)

T0 = datetime(2026, 9, 1, 15, 42, tzinfo=UTC)


def detection(**overrides) -> NormalizedDetection:
    values = {
        "source": DetectionSource.NASA_FIRMS,
        "product": "VIIRS_NOAA20_NRT",
        "satellite": "N20",
        "instrument": "VIIRS",
        "observed_at": T0,
        "latitude": -3.7319,
        "longitude": -38.5267,
        "confidence": "nominal",
        "frp_mw": 4.2,
        "brightness_k": 330.1,
        "daynight": "D",
        "raw": {"scan": "0.39"},
    }
    return NormalizedDetection(**{**values, **overrides})


# --- dedup key ---------------------------------------------------------------


def test_dedup_key_is_deterministic_and_a_uuid():
    assert detection().dedup_key == detection().dedup_key
    assert isinstance(detection().dedup_key, uuid.UUID)
    assert detection().dedup_key.version == 5


def test_dedup_key_ignores_timezone_representation_and_subseconds():
    fortaleza = timezone(timedelta(hours=-3))
    same_instant = T0.astimezone(fortaleza)
    assert detection(observed_at=same_instant).dedup_key == detection().dedup_key
    assert detection(observed_at=T0.replace(microsecond=999)).dedup_key == detection().dedup_key


def test_dedup_key_tolerates_reserialised_coordinates_only_below_11_m():
    assert detection(latitude=-3.73191).dedup_key == detection().dedup_key
    assert detection(latitude=-3.7329).dedup_key != detection().dedup_key


def test_dedup_key_negative_zero_is_zero():
    assert compute_dedup_key("NASA_FIRMS", "N20", T0, -0.00001, 0.0) == compute_dedup_key(
        "NASA_FIRMS", "N20", T0, 0.0, 0.0
    )


def test_dedup_key_ignores_product_but_not_satellite_or_source():
    base = detection().dedup_key
    assert detection(product="VIIRS_NOAA20_SP").dedup_key == base
    assert detection(satellite="N21").dedup_key != base
    assert detection(source=DetectionSource.INPE_QUEIMADAS).dedup_key != base
    assert detection(observed_at=T0 + timedelta(minutes=1)).dedup_key != base


# --- detection contract ------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"observed_at": datetime(2026, 9, 1, 15, 42)},  # naive
        {"latitude": 91.0},
        {"longitude": -180.5},
        {"latitude": math.nan},
        {"confidence": "medium"},
        {"daynight": "X"},
        {"frp_mw": -1.0},
        {"frp_mw": math.inf},
        {"brightness_k": 0.0},
        {"satellite": " "},
        {"product": "x" * 65},
        {"source": "NASA_FIRMS"},  # plain string, not the enum
    ],
)
def test_detection_contract_rejects_invalid_records(overrides):
    with pytest.raises(InvalidDetectionError):
        detection(**overrides)


def test_detection_contract_accepts_minimal_record():
    minimal = detection(confidence=None, frp_mw=None, brightness_k=None, daynight=None, raw={})
    assert minimal.raw == {}


def test_time_window_requires_aware_ordered_instants():
    with pytest.raises(ValueError):
        TimeWindow(start=datetime(2026, 1, 1), end=datetime(2026, 1, 2))
    with pytest.raises(ValueError):
        TimeWindow(start=T0, end=T0)
    window = TimeWindow.last(timedelta(days=1), now=T0)
    assert window.end - window.start == timedelta(days=1)


def test_provider_result_never_carries_data_on_failure():
    with pytest.raises(ValueError):
        ProviderResult(product="p", status="unavailable", detections=(detection(),))
    with pytest.raises(ValueError):
        ProviderResult(product="p", status="ok", rejected=-1)
    assert ProviderResult(product="p", status="disabled").detections == ()


def test_bbox_contains_the_official_extent_of_ceara():
    # Extent of CE_Municipios_2025 (IBGE): -41.4235, -7.8582, -37.2527, -2.7843.
    lon_min, lat_min, lon_max, lat_max = CEARA_BBOX
    assert lon_min < -41.4235 and lat_min < -7.8582 and lon_max > -37.2527 and lat_max > -2.7843


# --- official IBGE files -----------------------------------------------------


def test_manifest_describes_the_official_2025_mesh():
    manifest = load_manifest()
    assert manifest.raw["source"] == "IBGE"
    assert manifest.raw["version"] == "2025"
    assert manifest.raw["reference_date"] == "2025-04-30"
    assert manifest.raw["source_crs"] == "EPSG:4674"
    for entry in manifest.files:
        assert entry["url"].startswith("https://geoftp.ibge.gov.br/")
        assert len(entry["sha256"]) == 64
    verify_files(manifest)  # the versioned files are the published ones


def test_layers_hold_184_municipalities_of_ceara():
    manifest = load_manifest()
    state = read_layer(manifest, "state", "CD_UF", "NM_UF")
    municipalities = read_layer(manifest, "municipalities", "CD_MUN", "NM_MUN")
    validate_features(manifest, state, municipalities)
    assert [s.name for s in state] == ["Ceará"]
    assert len(municipalities) == 184
    names = {m.ibge_code: m.name for m in municipalities}
    assert names["2304400"] == "Fortaleza"
    assert names["2307304"] == "Juazeiro do Norte"
    assert names["2312809"] == "Senador Sá"
    # The published attributes are kept as they are.
    assert {"CD_MUN", "NM_MUN", "SIGLA_UF", "AREA_KM2", "CD_RGI"} <= set(
        municipalities[0].attributes
    )


@pytest.fixture
def municipalities_and_state():
    manifest = load_manifest()
    return (
        manifest,
        read_layer(manifest, "state", "CD_UF", "NM_UF"),
        read_layer(manifest, "municipalities", "CD_MUN", "NM_MUN"),
    )


def test_validation_refuses_missing_municipality(municipalities_and_state):
    manifest, state, municipalities = municipalities_and_state
    with pytest.raises(DatasetIntegrityError, match="183 municípios"):
        validate_features(manifest, state, municipalities[:-1])


def test_validation_refuses_duplicate_or_foreign_codes(municipalities_and_state):
    manifest, state, municipalities = municipalities_and_state
    duplicated = [*municipalities[:-1], municipalities[0]]
    with pytest.raises(DatasetIntegrityError, match="repetidos"):
        validate_features(manifest, state, duplicated)
    foreign = [*municipalities[:-1], replace(municipalities[-1], ibge_code="2211001")]
    with pytest.raises(DatasetIntegrityError, match="fora da UF"):
        validate_features(manifest, state, foreign)
    wrong_uf = [
        *municipalities[:-1],
        replace(municipalities[-1], attributes={**municipalities[-1].attributes, "SIGLA_UF": "PI"}),
    ]
    with pytest.raises(DatasetIntegrityError, match="SIGLA_UF"):
        validate_features(manifest, state, wrong_uf)
    with pytest.raises(DatasetIntegrityError, match="UF deveria"):
        validate_features(manifest, [], municipalities)


@pytest.fixture
def dataset_copy(tmp_path):
    target = tmp_path / "malha"
    shutil.copytree(ibge_import.DEFAULT_DATASET_DIR, target)
    return target


def test_tampered_file_is_refused(dataset_copy):
    archive = dataset_copy / "CE_UF_2025.zip"
    payload = bytearray(archive.read_bytes())
    payload[-1] ^= 0xFF
    archive.write_bytes(bytes(payload))
    with pytest.raises(DatasetIntegrityError, match="SHA-256"):
        verify_files(load_manifest(dataset_copy))


def test_unexpected_crs_is_refused(dataset_copy):
    archive = dataset_copy / "CE_UF_2025.zip"
    with zipfile.ZipFile(archive) as source:
        members = {name: source.read(name) for name in source.namelist()}
    members["CE_UF_2025.prj"] = b'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984"]]'
    with zipfile.ZipFile(archive, "w") as rebuilt:
        for name, data in members.items():
            rebuilt.writestr(name, data)
    manifest = load_manifest(dataset_copy)
    with pytest.raises(DatasetIntegrityError, match="SIRGAS 2000"):
        read_layer(manifest, "state", "CD_UF", "NM_UF")


def test_manifest_hash_identifies_the_file_set(dataset_copy):
    original = load_manifest().content_sha256
    path = dataset_copy / "MANIFEST.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["files"][0]["sha256"] = "0" * 64
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_manifest(dataset_copy).content_sha256 != original
    with pytest.raises(DatasetIntegrityError):
        load_manifest(dataset_copy).file("nonexistent")


def test_cli_verify_files_reports_tampering(dataset_copy, capsys):
    from seed import jurisdictions

    assert jurisdictions.main(["--verify-files", "--dataset-dir", str(dataset_copy)]) == 0
    (dataset_copy / "CE_Municipios_2025.zip").write_bytes(b"not the IBGE file")
    assert jurisdictions.main(["--verify-files", "--dataset-dir", str(dataset_copy)]) == 2
    assert "Recusado" in capsys.readouterr().err
