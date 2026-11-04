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
| GET | `/api/v1/orbital-alerts` | — | **PostGIS** (Sprint 1.3) | Focos persistidos com filtros `from`, `to`, `source`, `satellite`, `jurisdiction`, `bbox`, `page`, `size` ≤ 5000. **Rate limit 60/min/IP**. Nunca consulta NASA/INPE |
| GET | `/api/v1/orbital-alerts/sources` | — | PostGIS | Estado por fonte e produto: `live`, `stale`, `degraded`, `unavailable`, `disabled`, `never_ingested`; origem `live` ou `fixture` |
| GET | `/api/v1/orbital-alerts/stats` | — | PostGIS | Totais, municípios com focos, por fonte, satélite e dia, top 10 municípios (mesmos filtros) |
| GET | `/api/v1/orbital-alerts/{id}` | — | PostGIS | Um foco, com `raw` (linha original do provedor). 404 se não existe |
| GET | `/api/v1/jurisdictions/municipalities` | — | PostGIS | Os 184 municípios (IBGE 2025) com contagem de focos na janela; 503 se a malha não foi importada |
| GET | `/api/v1/jurisdictions/geojson` | — | PostGIS | `level=state` ou `municipality`; `tolerance` (0 a 0,01°, só para exibição); ETag e cache de 1 h |
| POST | `/api/v1/orbital-alerts/ingest` | **admin** | Real (Sprint 1.2) | **202** com as execuções criadas; processamento em segundo plano |
| GET | `/api/v1/orbital-alerts/ingestion-runs` | **admin** | Real (Sprint 1.2) | Últimas execuções (`limit` ≤ 100) |
| GET | `/api/v1/orbital-alerts/ingestion-runs/{run_id}` | **admin** | Real (Sprint 1.2) | Estado verificável de uma execução; 404 se não existe |

### Contrato `GET /api/v1/orbital-alerts` (Sprint 1.3)

Lê só `orbital_detections` e `ingestion_runs`. As definições estão em `app/orbital/read_schemas.py`.

**Cada item traz:**
- origem: `source`, `product`, `satellite`, `instrument`;
- horários: `observed_at` (satélite, UTC) e `ingested_at` (gravação no IGNIS);
- posição: `lat` e `lng` exatamente como gravados, e `jurisdiction` (código IBGE e nome);
- campos do sensor: `confidence` (classe VIIRS), `confidence_pct` (MODIS), `frp_mw`, `brightness_k` com `brightness_channel`, e `daynight`;
- identificadores: `provider_record_id` e `ingestion_run_id`;
- `persisted: true`.

**A página traz:**
- `total`, `page`, `size`, `pages`;
- `truncated`, quando há mais focos do que os devolvidos;
- `filters`, com a janela efetivamente aplicada (padrão: últimos 7 dias; máximo 92);
- `sources`, a situação de cada fonte (ver `/sources`);
- `data_origin: "postgis"` e `disclaimer`.

**Como ler `items` vazio:**
- com a fonte `live`, significa que não houve foco;
- com `disabled`, `unavailable` ou `never_ingested`, significa que não há dados para julgar.

O estado `cached` da Sprint 0 deixou de existir, porque não há mais cache de chamada externa. Os estados possíveis estão na tabela acima.

### Contrato `POST /api/v1/orbital-alerts/ingest` (Sprint 1.2)

Corpo opcional: `{"sources": ["firms", "inpe"]}`. Por padrão, as duas fontes.

| Campo | Significado |
|---|---|
| `status` | `accepted` quando ao menos uma execução foi criada; `nothing_started` quando todos os produtos já estão rodando em outro processo |
| `round_id` | Id da rodada. Também fica em `ingestion_runs.params.round_id` e no `entity_id` da auditoria |
| `runs[]` | `run_id`, `source`, `product`, `status` (`running` ou `skipped_active`). O `run_id` já existe em `ingestion_runs` quando a resposta chega |
| `message` | Diz que nenhum resultado é afirmado e aponta para a consulta do estado |

O resultado (`ok`, `partial`, `unavailable`, `disabled`, `error` e os contadores) só pode ser lido em `GET /ingestion-runs/{run_id}`. A ação é auditada como `orbital_ingest.requested`, com o `user_id` do solicitante. O contrato da Sprint 0 (`processed_not_persisted`, cache em memória) foi removido.
