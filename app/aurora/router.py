from fastapi import APIRouter, Depends

from app.aurora import engine as aurora_engine
from app.aurora.schemas import AnalyzeRequest, AnalyzeResponse, ChatRequest, ChatResponse
from app.core.enums import UserRole
from app.dependencies import require_role

router = APIRouter(prefix="/api/v1/aurora", tags=["aurora"])


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_incident(
    body: AnalyzeRequest,
    _current_user=Depends(require_role(UserRole.CAMPO)),
) -> AnalyzeResponse:
    """Rule-based risk analysis — no DB, no external AI calls."""
    return aurora_engine.analyze(body)


@router.post("/chat", response_model=ChatResponse)
async def chat_with_aurora(body: ChatRequest) -> ChatResponse:
    """Public rule-based chat endpoint — no auth, no DB, no external AI calls."""
    return aurora_engine.chat(body.message, body.context)
