# IGNIS — Inventário da API (FastAPI)

Revisão: branch `audit/ignis-sprint-0` (base `main` `3e22ecb`). O OpenAPI completo fica em `/openapi.json` (o FastAPI gera automaticamente).
Prefixo dos endpoints de domínio: `/api/v1`. Autenticação: `Authorization: Bearer <JWT HS256>` emitido por `POST /api/v1/auth/login`.
Hierarquia de papéis (`app/dependencies.py:14-20`): `publico(0) < campo(1) < gestor(2) < orgao(3) < admin(4)`. `require_role(X)` aceita X ou superior.
O papel é **relido do banco** a cada requisição; o claim `role` do token não é usado na autorização.

Legenda de estado:
- **Real**: persiste ou lê do PostgreSQL.
- **Externo**: proxy para provedor externo.
- **Regra fixa**: lógica determinística sem modelo.
- **Parcial**: funciona, mas com limitação relevante.

Em todos os endpoints de domínio, o banco de demonstração contém dados do **seed** (`seed/`). "Real" descreve o mecanismo, não a veracidade dos dados.

## Saúde

| Método | Rota | Auth | Estado | Observação |
|---|---|---|---|---|
| GET | `/health` | — | Real | Versão e ambiente |
| GET | `/ready` | — | Real | `SELECT 1`. Em falha: 503 `{"database":"unreachable"}`, sem detalhe do driver (Sprint 0) |

## Autenticação e usuários

| Método | Rota | Auth | Estado | Observação |
|---|---|---|---|---|
| POST | `/api/v1/auth/login` | — | Real | **Rate limit 10/min/IP** (Sprint 0). Audita sucesso; falha não é auditada (B-17) |
| GET | `/api/v1/auth/me` | qualquer autenticado | Real | |
| GET/POST | `/api/v1/admin/users` | admin | Real | Paginado. POST/PATCH (Sprint 0.1): senha de 12 a 72 bytes e fora da lista de senhas publicadas, `role` do enum, e-mail válido, sem campos extras |
| GET/PATCH/DELETE | `/api/v1/admin/users/{id}` | admin | Real | DELETE = desativação lógica (`is_active=false`) |
| GET | `/api/v1/admin/audit-logs` | admin | Real | Paginado |
| GET | `/api/v1/admin/stats` | orgao | Real | Sem consumidor na UI |

## Áreas protegidas

| Método | Rota | Auth | Estado | Observação |
|---|---|---|---|---|
| GET | `/api/v1/protected-areas` | — (público) | Real | Filtro `state`. Sem campo de risco (F-12) |
| GET | `/api/v1/protected-areas/{id}` | — | Real | Geometria em WKT |
| GET | `/api/v1/protected-areas/{id}/incidents` · `/reports` | gestor | Real | |
| POST/PATCH | `/api/v1/protected-areas[/{id}]` | orgao | Real | Auditado |
| DELETE | `/api/v1/protected-areas/{id}` | admin | Real | **Exclusão física** (B-20) |

## Denúncias públicas

| Método | Rota | Auth | Estado | Observação |
|---|---|---|---|---|
| POST | `/api/v1/reports` | — (público) | Real | **Validação reforçada e rate limit 10/min/IP** (Sprint 0). Gera protocolo `RP-YYYYMMDD-XXXX` |
| GET | `/api/v1/reports/lookup?protocol=` | — | Real | Schema sem dados pessoais. **Rate limit 30/min/IP** |
| GET | `/api/v1/reports[/{id}]` | gestor | Real | Inclui dados pessoais do denunciante |
| PATCH | `/api/v1/reports/{id}/status` · `/validate` · `/discard` | gestor | Real | Auditado |
| POST | `/api/v1/reports/{id}/convert-to-incident` | gestor | Real | Cria incidente; auditado; devolve o incidente criado |

## Incidentes e Sala de Crise

| Método | Rota | Auth | Estado | Observação |
|---|---|---|---|---|
| GET | `/api/v1/incidents` | gestor | Real | Filtros `type`, `severity`, `status`, `area_id`. **Sem isolamento por instituição** (B-07) |
| GET | `/api/v1/incidents/active/critical` | gestor | Real | |
| GET | `/api/v1/incidents/war-room` · `/api/v1/war-room` | gestor | Real | Resumo consolidado |
| GET | `/api/v1/war-room/{incident_id}` | gestor | Real | Sem consumidor na UI |
| GET | `/api/v1/incidents/{id}` | gestor | Real | |
| POST | `/api/v1/incidents` | gestor | Real | Sem tela de criação manual no frontend |
| PATCH | `/api/v1/incidents/{id}` | gestor | Real | |
| PATCH | `/api/v1/incidents/{id}/status` | gestor | Parcial | **Transições livres** (B-12) |
| POST | `/api/v1/incidents/{id}/activate-protocol` | gestor | Parcial | Só muda status, grava evento e auditoria. **Não notifica nenhum órgão externo** |
| GET | `/api/v1/incidents/{id}/timeline` | gestor | Real | |
| POST | `/api/v1/incidents/{id}/events` | gestor | Real | Não grava `audit_logs` (B-19) |

## Operações

| Método | Rota | Auth | Estado | Observação |
|---|---|---|---|---|
| GET | `/api/v1/teams[/{id}]` | gestor | Real | Resposta `Page{items,total,page,size,pages}` |
| POST | `/api/v1/teams` | admin | Real | |
| PATCH | `/api/v1/teams/{id}` | gestor | Real | `status ∈ available, mobilized, standby, returning, unavailable`. **Não aciona equipes reais** |
| GET/POST/PATCH | `/api/v1/resources[/{id}]` | gestor (POST: admin) | Real | `Page` |
| GET/POST/PATCH | `/api/v1/missions[/{id}]`, `PATCH …/status` | gestor | Real | `Page`. Sem uso real na UI de campo |
| GET/POST | `/api/v1/evidence[/{id}]` | campo | Real | `Page`. Guarda só a URL; não há upload de arquivo |
| GET/POST | `/api/v1/esg[/{id}]` | orgao | Real | Relatórios ESG |

## AURORA (assistente)

| Método | Rota | Auth | Estado | Observação |
|---|---|---|---|---|
| POST | `/api/v1/aurora/analyze` | campo | Regra fixa | Sem consumidor na UI |
| POST | `/api/v1/aurora/chat` | — (público) | Regra fixa | **Rate limit 30/min/IP**. Não usa modelo de linguagem |

## Integrações externas

| Método | Rota | Auth | Estado | Observação |
|---|---|---|---|---|
| GET | `/api/v1/environment/weather-risk?lat&lng` | — | Externo (Open-Meteo) | `source_status ∈ live, cached, unavailable`; cache 60 min por processo. **Rate limit 60/min/IP** |
| GET | `/api/v1/geocoding/reverse?lat&lng` | — | Externo (Nominatim) | Cache por grade de cerca de 111 m. **Rate limit 30/min/IP**. Sem consumidor na UI |
| GET | `/api/v1/orbital-alerts` | — | Externo (NASA FIRMS) | Contrato abaixo. **Rate limit 60/min/IP** |
| POST | `/api/v1/orbital-alerts/ingest` | **admin** (Sprint 0) | Parcial | Atualiza o cache; **não persiste** |

### Contrato `GET /api/v1/orbital-alerts` (Sprint 0)

```jsonc
{
  "items": [ /* OrbitalAlert */ ],
  "total": 0,
  "source_status": "live | cached | demo | disabled_missing_api_key | unavailable",
  "data_origin": "nasa_firms | demo | none",   // novo
  "persisted": false,                           // novo — sempre false nesta versão
  "fetched_at": "ISO-8601 | null",              // novo — quando a NASA foi consultada
  "cached_at": "ISO-8601 | null",               // preenchido quando source_status=cached
  "message": "string | null",                   // novo — motivo legível
  "disclaimer": "anomalia térmica ≠ incêndio confirmado",  // novo
  "since": null
}
```

| `source_status` | `items` | Significado |
|---|---|---|
| `live` | dados NASA | Consultado na NASA nesta requisição |
| `cached` | dados NASA | Consultado antes (`cached_at`/`fetched_at`), dentro do TTL |
| `demo` | fictícios, `is_demo=true` | Só com `ORBITAL_ALERTS_DEMO_MODE=true` |
| `disabled_missing_api_key` | `[]` | `NASA_FIRMS_MAP_KEY` ausente |
| `unavailable` | `[]` | Falha de rede/HTTP ou corpo não-CSV; backoff de 5 min |

`OrbitalAlert` ganhou `is_demo: bool`. O `id` agora é determinístico (UUIDv5 de lat, lng, data, hora e satélite).

### Contrato `POST /api/v1/orbital-alerts/ingest` (Sprint 0)

| `status` | Quando | `records_inserted` |
|---|---|---|
| `processed_not_persisted` | NASA respondeu; focos validados e mantidos em cache | **0** (o número real vai em `records_valid`) |
| `disabled_missing_api_key` | Sem chave | 0 |
| `unavailable` | Falha da NASA | 0 |

Campos novos: `records_valid` e `persisted` (sempre `false`). Toda chamada grava `orbital_alerts.ingest_triggered` em `audit_logs`.

**Compatibilidade.** Os campos novos são aditivos. Os valores novos de enum são `demo` e `processed_not_persisted`. O frontend da Sprint 0 os trata. Consumidores antigos que só verificavam `disabled_missing_api_key` passam a ver lista vazia em vez dos 3 itens demo, que é o comportamento correto.

## Erros

- Formato padrão do FastAPI: `{"detail": "<mensagem>"}`. Em 422, `detail` é uma lista de objetos de validação.
- 401 inclui `WWW-Authenticate: Bearer`. 429 inclui `Retry-After`.
- Proposta da Fase 4: padronizar o formato de erro com `code` (alinhado ao OrkenGov, ver ORKENGOV-INTEGRATION §6).
