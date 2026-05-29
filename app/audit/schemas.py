import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID | None
    actor_name: str
    action: str
    entity_type: str
    entity_id: str
    metadata_json: dict | None
    created_at: datetime
