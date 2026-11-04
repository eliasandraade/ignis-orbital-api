import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class IngestRequest(BaseModel):
    # Default: every provider (FIRMS reports 'disabled' runs without a key).
    sources: list[Literal["firms", "inpe"]] | None = None


class StartedRun(BaseModel):
    run_id: uuid.UUID | None
    source: str
    product: str
    # running: created now, processing in background · skipped_active: another
    # live process is already running this product (no run created).
    status: Literal["running", "skipped_active"]


class IngestAccepted(BaseModel):
    status: Literal["accepted", "nothing_started"]
    round_id: uuid.UUID
    message: str
    runs: list[StartedRun]


class IngestionRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: str
    product: str
    trigger: str
    triggered_by_user_id: uuid.UUID | None
    status: str
    started_at: datetime
    finished_at: datetime | None
    window_start: datetime | None
    window_end: datetime | None
    records_fetched: int
    records_valid: int
    records_rejected: int
    records_out_of_scope: int
    records_inserted: int
    records_duplicate: int
    error_code: str | None
    error_message: str | None
    params: dict
