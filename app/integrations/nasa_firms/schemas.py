from datetime import datetime
from typing import Literal

from pydantic import BaseModel

# Detecção por satélite indica anomalia térmica; não confirma incêndio.
THERMAL_ANOMALY_DISCLAIMER = (
    "Focos de calor são anomalias térmicas detectadas por satélite (NASA FIRMS, "
    "VIIRS NRT, latência típica de algumas horas). Não confirmam incêndio: "
    "exigem validação por operador humano."
)


class OrbitalAlert(BaseModel):
    id: str
    type: Literal["heat_spot", "burn_confirmed", "deforestation", "anomaly"]
    lat: float
    lng: float
    area_id: str | None
    confidence: int
    source: str
    detected_at: datetime
    fetched_at: datetime
    converted_to_incident_id: str | None = None
    raw_data: dict | None = None
    # True quando o item é fictício (modo demonstrativo explícito).
    is_demo: bool = False


class OrbitalAlertListResponse(BaseModel):
    items: list[OrbitalAlert]
    total: int
    # live: obtido da NASA nesta requisição · cached: obtido da NASA anteriormente
    # (ver fetched_at) · demo: dados fictícios · disabled_missing_api_key: chave
    # ausente, sem dados · unavailable: NASA indisponível ou resposta inválida.
    source_status: Literal["live", "cached", "demo", "disabled_missing_api_key", "unavailable"]
    since: str | None = None
    cached_at: str | None = None
    data_origin: Literal["nasa_firms", "demo", "none"] = "none"
    # Nenhum alerta é gravado em banco nesta versão (sem tabela orbital_alerts).
    persisted: bool = False
    fetched_at: str | None = None
    message: str | None = None
    disclaimer: str = THERMAL_ANOMALY_DISCLAIMER


class IngestResponse(BaseModel):
    # processed_not_persisted: dados obtidos e validados, mas NÃO gravados em banco.
    status: Literal[
        "ok",
        "partial",
        "processed_not_persisted",
        "disabled_missing_api_key",
        "unavailable",
        "error",
    ]
    message: str
    records_fetched: int = 0
    records_valid: int = 0
    # Registros efetivamente gravados em banco. Sempre 0 até existir persistência.
    records_inserted: int = 0
    records_skipped: int = 0
    persisted: bool = False


class ConvertToIncidentRequest(BaseModel):
    priority: Literal["alta", "media", "baixa"] = "media"
    notes: str = ""


class ConvertToIncidentResponse(BaseModel):
    incident_id: str
    orbital_alert_id: str
