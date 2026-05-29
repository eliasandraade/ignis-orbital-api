from pydantic import BaseModel


class AnalyzeRequest(BaseModel):
    incident_severity: str | None = None
    incident_type: str | None = None
    area_hectares: float | None = None
    wind_speed: float | None = None
    humidity: float | None = None


class AnalyzeResponse(BaseModel):
    risk_level: str
    recommended_actions: list[str]
    estimated_spread_km2: float | None
    priority_score: int
    alerts: list[str]


class ChatRequest(BaseModel):
    message: str
    context: dict | None = None


class ChatResponse(BaseModel):
    response: str
    confidence: float
    suggested_actions: list[str]
