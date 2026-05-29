"""Aurora IA — rule-based environmental intelligence engine.

100% deterministic Python logic. No LLM calls, no external AI APIs.
"""

from app.aurora.schemas import AnalyzeRequest, AnalyzeResponse, ChatResponse

# ---------------------------------------------------------------------------
# Action templates by incident type
# ---------------------------------------------------------------------------

_TYPE_ACTIONS: dict[str, list[str]] = {
    "fire": [
        "Estabelecer perímetro de segurança de 500m",
        "Acionar brigada de incêndio",
        "Monitorar direção do vento",
    ],
    "deforestation": [
        "Registrar coordenadas GPS da área afetada",
        "Documentar extensão do desmatamento",
        "Acionar fiscalização ambiental",
    ],
    "flood": [
        "Avaliar rotas de evacuação",
        "Monitorar nível das águas a cada 2h",
        "Alertar comunidades ribeirinhas",
    ],
    "illegal_mining": [
        "Isolar área de garimpo ilegal",
        "Coletar amostras de água",
        "Registrar evidências fotográficas",
    ],
    "pollution": [
        "Identificar fonte contaminante",
        "Coletar amostras para análise",
        "Alertar órgão ambiental",
    ],
    "other": [
        "Documentar ocorrência com fotos e GPS",
        "Acionar equipe de vistoria",
        "Registrar no sistema",
    ],
}

# ---------------------------------------------------------------------------
# Chat keyword rules (checked in order, first match wins)
# ---------------------------------------------------------------------------

_KEYWORD_RESPONSES: list[tuple[list[str], dict]] = [
    (
        ["incêndio", "fogo", "queimada", "fire"],
        {
            "response": (
                "Para incêndios florestais, ative imediatamente o protocolo de resposta."
                " Estabeleça perímetro de segurança, acione brigadas e monitore o vento."
            ),
            "confidence": 0.92,
            "suggested_actions": [
                "Verificar equipes disponíveis",
                "Consultar mapa de áreas de risco",
                "Iniciar registro de incidente",
            ],
        },
    ),
    (
        ["desmatamento", "deforestation"],
        {
            "response": (
                "Desmatamento ilegal deve ser registrado com coordenadas GPS precisas. "
                "Documente a extensão, acione fiscalização e registre evidências fotográficas."
            ),
            "confidence": 0.89,
            "suggested_actions": [
                "Registrar ocorrência no sistema",
                "Acionar fiscalização",
                "Documentar com evidências",
            ],
        },
    ),
    (
        ["missão", "mission", "equipe", "time"],
        {
            "response": (
                "Para gestão de missões, consulte o painel de equipes disponíveis. "
                "Cada missão deve ter objetivo claro e equipe designada com recursos adequados."
            ),
            "confidence": 0.85,
            "suggested_actions": [
                "Verificar disponibilidade de equipes",
                "Criar nova missão",
                "Consultar recursos disponíveis",
            ],
        },
    ),
    (
        ["relatório", "report", "ocorrência"],
        {
            "response": (
                "Relatórios podem ser submetidos anonimamente pelo portal público. "
                "Inclua localização precisa, tipo de ocorrência e fotos quando possível."
            ),
            "confidence": 0.88,
            "suggested_actions": [
                "Submeter novo relatório",
                "Consultar status de relatório existente",
            ],
        },
    ),
    (
        ["risco", "risk", "perigo", "alerta"],
        {
            "response": (
                "A análise de risco considera severidade, tipo de incidente, condições climáticas "
                "e extensão da área. Use o endpoint /analyze para uma avaliação detalhada."
            ),
            "confidence": 0.82,
            "suggested_actions": [
                "Realizar análise de risco",
                "Consultar mapa de incidentes ativos",
            ],
        },
    ),
    (
        ["área protegida", "reserva", "parque", "apa", "parna"],
        {
            "response": (
                "As áreas protegidas monitoradas incluem APAs, PARNAs, RESEXs e outras categorias. "
                "Consulte o catálogo completo no endpoint /protected-areas."
            ),
            "confidence": 0.87,
            "suggested_actions": [
                "Consultar áreas protegidas",
                "Ver incidentes na área",
            ],
        },
    ),
]

_DEFAULT_RESPONSE: dict = {
    "response": (
        "Sou Aurora, assistente de inteligência ambiental do IGNIS Orbital. "
        "Posso ajudar com análise de incidentes, gestão de missões, relatórios de ocorrências "
        "e monitoramento de áreas protegidas. Como posso ajudar?"
    ),
    "confidence": 0.5,
    "suggested_actions": [
        "Analisar incidente",
        "Submeter relatório",
        "Consultar áreas protegidas",
    ],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze(payload: AnalyzeRequest) -> AnalyzeResponse:
    """Return rule-based environmental risk analysis. No external calls."""
    severity = (payload.incident_severity or "").lower()
    inc_type = (payload.incident_type or "").lower()
    wind = payload.wind_speed
    humidity = payload.humidity
    area = payload.area_hectares

    # --- risk_level ---
    fire_critical_conditions = (
        inc_type == "fire"
        and wind is not None
        and wind > 50
        and humidity is not None
        and humidity < 30
    )
    if severity == "critical" or fire_critical_conditions:
        risk_level = "critical"
    elif severity == "high" or (inc_type == "fire" and wind is not None and wind > 30):
        risk_level = "high"
    elif severity == "medium" or inc_type in ("deforestation", "illegal_mining"):
        risk_level = "medium"
    else:
        risk_level = "low"

    # --- priority_score ---
    base_scores = {"critical": 90, "high": 70, "medium": 45, "low": 20}
    score = base_scores.get(severity, 20)
    if wind is not None and wind > 40:
        score += 10
    if humidity is not None and humidity < 30:
        score += 5
    if area is not None and area > 500:
        score += 5
    priority_score = min(score, 100)

    # --- estimated_spread_km2 ---
    estimated_spread_km2: float | None = None
    if inc_type == "fire" and wind is not None:
        base = (area / 100) if area is not None else 1.0
        humidity_factor = (1 - humidity / 100) if humidity is not None else 1.0
        spread = base * (wind / 20) * humidity_factor
        estimated_spread_km2 = round(spread, 2)

    # --- recommended_actions ---
    actions: list[str] = list(_TYPE_ACTIONS.get(inc_type, _TYPE_ACTIONS["other"]))
    if risk_level == "critical":
        actions.append("Acionar protocolo de emergência máxima")
    if wind is not None and wind > 40 and inc_type == "fire":
        actions.append("Risco de propagação rápida — reforçar equipes")

    # --- alerts ---
    alerts: list[str] = []
    if humidity is not None and humidity < 30 and inc_type == "fire":
        alerts.append("Umidade crítica: risco elevado de propagação")
    if wind is not None and wind > 60:
        alerts.append("Vento forte: propagação rápida possível")
    if area is not None and area > 1000:
        alerts.append("Área extensa: mobilizar múltiplas equipes")

    return AnalyzeResponse(
        risk_level=risk_level,
        recommended_actions=actions,
        estimated_spread_km2=estimated_spread_km2,
        priority_score=priority_score,
        alerts=alerts,
    )


def chat(message: str, context: dict | None = None) -> ChatResponse:  # noqa: ARG001
    """Return rule-based chat response via keyword matching. No external calls."""
    lower_msg = message.lower()

    for keywords, data in _KEYWORD_RESPONSES:
        if any(kw in lower_msg for kw in keywords):
            return ChatResponse(
                response=data["response"],
                confidence=data["confidence"],
                suggested_actions=data["suggested_actions"],
            )

    return ChatResponse(
        response=_DEFAULT_RESPONSE["response"],
        confidence=_DEFAULT_RESPONSE["confidence"],
        suggested_actions=_DEFAULT_RESPONSE["suggested_actions"],
    )
