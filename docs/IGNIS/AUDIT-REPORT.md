# IGNIS — Relatório de Auditoria (Sprint 0)

Data: 03/11/2026 · Escopo: `ignis-orbital-api` (main `3e22ecb` + PR #2 aberto `e3817ac`), `ignis-fire-watch` (master `e56d02f`; main `02df1fb`), `orkengov` (main `1e07f56`, somente leitura).
Método: leitura de código, execução de testes, banco PostGIS isolado (container descartável), API e frontend locais, e verificação somente leitura das URLs públicas.

## 1. Veredito

O IGNIS é um **protótipo acadêmico bem estruturado**, mas **não é um sistema operacional**:

- Não existe nenhuma fonte de dados operacional persistida. Os incidentes, equipes, recursos, missões e áreas da API vêm do **seed demonstrativo**. O frontend em modo padrão (`VITE_USE_API=false`) mostra apenas mocks.
- As únicas integrações reais são **Open-Meteo** (clima) e **NASA FIRMS** (anomalias térmicas). Ambas são consultadas sob demanda, sem persistência, e o FIRMS exige chave.
- Antes desta sprint, a interface **apresentava dados demonstrativos como reais** e **confirmava operações que não aconteceram**. A integração FIRMS **informava gravações inexistentes** e podia rotular dados fictícios como `live`.
- Não há modelo de **instituição/organização**: qualquer usuário `gestor` vê e altera todos os incidentes. Isso bloqueia uso multi-institucional (Bombeiros, Defesa Civil, municípios).
- A API de produção documentada (`ignis-api-production.up.railway.app`) responde **404 "Application not found"** do Railway. Os frontends na Vercel estão no ar.

A Sprint 0 corrigiu os P0 de **honestidade de dados, falsas confirmações, FIRMS e segurança básica**. Os itens arquiteturais (multi-tenancy, persistência geoespacial, mapa operacional) foram planejados para as Fases 1–4.

## 2. Achados transversais e de processo

| ID | Grav. | Achado | Evidência | Estado |
|---|---|---|---|---|
| X-01 | P1 | No frontend, a branch padrão `main` é o snapshot Lovable de 06/2025. Todo o desenvolvimento e os PRs #1–#3 foram para `master`. Divergência: `main` tem 13 commits que `master` não tem, e `master` tem 42 que `main` não tem. | `gh pr list` (base `master`); `git rev-list --left-right --count origin/main...origin/master` | Pendente (decisão do proprietário: tornar `master` padrão ou alinhar `main`) |
| X-02 | P1 | Nenhum dos repositórios IGNIS tem CI (`.github/workflows` ausente). Testes e lint nunca rodam automaticamente. | `ls .github/workflows` vazio nos dois repos | Pendente (PHASE-1 P0-01) |
| X-03 | P1 | A API de produção documentada responde 404 (Railway "Application not found"). O estado do deploy é desconhecido. | `curl https://ignis-api-production.up.railway.app/health` → 404 (03/11/2026) | Pendente (decisão do proprietário) |
| X-04 | P1 | O frontend não tinha typecheck no pipeline: `vite build` passava com 6 erros de tipo, e `npm run lint` quebrava com TypeError (eslint 9.39 × typescript-eslint 8.11). | baseline em SPRINT-0-DELIVERY §2 | **Corrigido** (`7c7f26f`) |
| X-05 | P1 | O PR #2 do backend (`feature/real-orbital-apis`, aberto) repete os defeitos do FIRMS, como mostram os trechos abaixo. | `orbital_alerts_service.py:102-116,167`; `orbital_alerts_router.py:27`; `nasa_firms/service.py:197` | Pendente: **não mergear como está**. Rebasear o cliente INPE sobre o contrato da Sprint 0 (PHASE-1 P0-03) |

Trechos do PR #2 citados em X-05:

- **Fallback demo com origem NASA:** quando nenhum provedor retorna focos, inclusive num dia sem incêndios, o PR exibe `_DEMO_ALERTS` com fonte NASA.
- **Contagem falsa:** `records_inserted` soma registros que nunca foram gravados.
- **Ingestão aberta:** o endpoint de ingestão não exige autenticação.
- **Exposição de erro:** o PR repassa `str(exc)` na resposta.

## 3. Backend (`ignis-orbital-api`)

| ID | Grav. | Achado | Evidência (revisão `3e22ecb`) | Estado |
|---|---|---|---|---|
| B-01 | P0 | `GET /orbital-alerts` sempre devolvia os 3 alertas demo. Com `NASA_FIRMS_MAP_KEY` definida, o status virava `live`, e dados fictícios apareciam como reais. | `app/integrations/nasa_firms/service.py:111-126` | **Corrigido** (`ca9a0d4`) |
| B-02 | P0 | A ingestão parseava o CSV em memória e devolvia `records_inserted = len(alerts)` sem gravar nada. | `service.py:158-169` (a mensagem admitia "Persistência … será ativada") | **Corrigido**: `records_inserted=0`, `status=processed_not_persisted`, `persisted=false` |
| B-03 | P0 | `POST /orbital-alerts/ingest` aceitava chamadas sem autenticação: qualquer pessoa podia consumir a cota da NASA. | `orbital_alerts_router.py:24-35` | **Corrigido**: `require_role(ADMIN)` e auditoria |
| B-04 | P0 | A mensagem de erro da ingestão incluía `str(exc)` do httpx. A URL do FIRMS embute a MAP_KEY (`/area/csv/{key}/…`), então um 4xx/5xx expunha a credencial. | `service.py:152-156`; `client.py:51` | **Corrigido**: só o tipo da exceção; teste garante a ausência da chave |
| B-05 | P0 | O `entrypoint.sh` executava o seed demonstrativo a **cada boot, inclusive em produção**. O seed cria `admin@ignis-orbital.com` com a senha `admin@123` (publicada no repo) e outros 3 usuários. | `scripts/entrypoint.sh:23-24`; `seed/seed_users.py:7-32` | **Corrigido para novos boots**. **Pendente:** bancos já semeados mantêm os usuários (ação do proprietário, ver SECURITY-REVIEW R-01) |
| B-06 | P0 | Com `APP_ENV=production`, a API aceitava o `JWT_SECRET_KEY` padrão `dev-secret-change-in-production`, o que permite forjar tokens de admin. | `app/config.py:22` | **Corrigido**: boot falha com segredo padrão ou com menos de 32 caracteres |
| B-07 | P0 (arq.) | Não existe entidade de organização/instituição. Qualquer `gestor` lista e altera incidentes, denúncias e equipes de todos, sem isolamento entre instituições. | `app/users/model.py` (sem `organization_id`); `incidents/service.py:27-68` | Pendente: Fase 4 (bloqueia uso multi-institucional) |
| B-08 | P1 | `/ready` devolvia `str(exc)` do driver (host, usuário, DSN). | `app/health/router.py:27-31` | **Corrigido** |
| B-09 | P1 | `POST /reports` (público) aceitava texto ilimitado, lat/lng fora da faixa, URLs de evidência arbitrárias (`javascript:`) e campos extras. Denúncia anônima ainda gravava nome e contato. | `app/reports/schemas.py:73-83` | **Corrigido** |
| B-10 | P1 | Não havia rate limiting em login, denúncia pública, AURORA chat, geocoding (proxy para Nominatim) nem orbital-alerts. | — | **Mitigado**: limitador em memória por processo. Pendente: limitador compartilhado/edge |
| B-11 | P1 | `CORS_ORIGINS` no formato separado por vírgulas, documentado no `.env.example`, derrubava o boot com `SettingsError`. | reproduzido localmente; `app/config.py:34-56` | **Corrigido** (`6b45a9d`) |
| B-12 | P1 | A transição de status de incidente é livre: `resolved → active`, qualquer → `protocol_activated`. Não há máquina de estados nem regra por papel. | `app/incidents/service.py:151-176` | Pendente (PHASE-1 P1-07) |
| B-13 | P1 | Drift de schema: 15 colunas são `timestamptz` no banco, mas os modelos declaram `DateTime()` ingênuo, e o código grava UTC sem tz (`replace(tzinfo=None)`). | `alembic check` no PostGIS isolado (SPRINT-0-DELIVERY §3.3) | Pendente (PHASE-1 P1-06) |
| B-14 | P1 | Alertas orbitais não são persistidos, não há agendador de ingestão e o cache é em memória por worker (2 workers = 2 caches). | `app/integrations/_cache.py`; `scripts/entrypoint.sh:29` | Pendente: Fase 1 (núcleo do backlog) |
| B-15 | P1 | O portal público consome `GET /incidents`, que exige GESTOR. Sem login a lista fica vazia, e não existe endpoint público sanitizado. | `incidents/router.py:25-34`; `PublicDashboardPage.tsx:69` | Pendente (PHASE-1 P1-04) |
| B-16 | P1 | O seed usa domínios institucionais reais (`semace.ce.gov.br`, `defesacivil.ce.gov.br`, `ibama.gov.br`) para usuários fictícios. | `seed/seed_users.py:14-30` | Pendente: trocar por `*.example` (quebra logins demo de bancos existentes) |
| B-17 | P2 | Login sem custo constante: usuário inexistente não executa bcrypt (enumeração por tempo). Falhas de login não são auditadas. | `app/auth/service.py:13-17` | Pendente |
| B-18 | P2 | `/docs`, `/redoc` e `/openapi.json` ficam públicos em produção. | `app/main.py:41-44` | Pendente (decisão: manter para integradores ou proteger) |
| B-19 | P2 | `POST /incidents/{id}/events` não grava `audit_logs` (só a timeline). O log de auditoria é mutável e não registra IP nem user agent. | `incidents/router.py:158-169`; `core/audit.py` | Pendente |
| B-20 | P2 | Exclusão física de área protegida (`db.delete`). O admin pode desativar o próprio usuário, sem proteção de "último admin". | `protected_areas/service.py:114-119`; `users/service.py:59` | Pendente |
| B-21 | P2 | JWT de 480 min sem refresh nem revogação (só `is_active`). O papel é relido do banco a cada requisição, o que é positivo. | `config.py:24`; `dependencies.py:25-60` | Pendente |

## 4. Frontend (`ignis-fire-watch`, master)

Inventário completo e matriz de rastreabilidade: [FRONTEND-INVENTORY.md](https://github.com/eliasandraade/ignis-fire-watch/blob/audit/ignis-sprint-0/docs/IGNIS/FRONTEND-INVENTORY.md).

| ID | Grav. | Achado | Evidência (`e56d02f`) | Estado |
|---|---|---|---|---|
| F-01 | P0 | Em modo API, **qualquer falha** (rede, 401, 403, 422) caía silenciosamente para mock. Um incidente crítico fictício (`IGN-CE-2026-0041`) aparecia como "INCIDENTE CRÍTICO ATIVO". | `hooks/useIncidents.ts:32,46-56` | **Corrigido** (`0a5fa0e`): sem mock em modo API, com faixa global de integridade |
| F-02 | P0 | "Reforçar Protocolo" mostrava "✓ Protocolo Ativado" mesmo com erro da API. | `pages/gestor/WarRoomPage.tsx:68-80,413` | **Corrigido** (`3c0c59f`) |
| F-03 | P0 | Botão "Validar" da tabela de denúncias: só toast, mesmo em modo API. | `components/gestor/ReportTable.tsx:81-92` | **Corrigido** |
| F-04 | P0 | Checklist de protocolo vinha com "Notificação de autoridades (SEMACE, IBAMA, Defesa Civil)" concluída por "Sistema IGNIS". Não existe integração alguma. | `data/operations.ts:16-24` | **Corrigido** |
| F-05 | P0 | Operação de campo: "Cheguei ao Local" e "Enviar Relatório" eram só estado local, com "✓ Relatório Enviado". | `pages/gestor/FieldOperationPage.tsx:23-27,99-166` | **Corrigido**: simulação rotulada (demo) ou desabilitado (API) |
| F-06 | P0 | Denúncia do cidadão: em modo mock o protocolo era gerado no navegador e a tela mostrava "Recebida". Protocolo inexistente também mostrava "Recebida". | `pages/public/RegisterReportPage.tsx:107-122`; `ReportStatusPage.tsx:70` | **Corrigido**: "SIMULAÇÃO — NÃO enviada", "protocolo não encontrado", aviso 193/199 |
| F-07 | P0 | Alertas FIRMS: o fallback exibia 3 focos falsos com fonte `NASA_FIRMS_VIIRS` e culpava "chave ausente" por qualquer erro. | `hooks/useOrbitalAlerts.ts:6-64` | **Corrigido** |
| F-08 | P0 | `/select-profile` dava UI de **admin** sem login, mesmo com `VITE_USE_API=true`. O logout não apagava o token. 401 virava dado demo. | `router/index.tsx:52`; `GestorSidebar.tsx:19-22`; `services/api/client.ts:26-35` | **Corrigido** (`042915a`) |
| F-09 | P1 | Contratos quebrados: teams/resources/missions/evidence esperavam array, mas o backend devolve `Page`, então ficavam sempre em mock. Mobilização enviava `mobilizado` (422). 5 de 10 tipos de denúncia eram inválidos (422). | `teamsService.ts:24`; `MobilizationPage.tsx:30`; `reportAdapter.ts:9-14` | **Corrigido**, com teste de contrato |
| F-10 | P1 | Indicadores inventados: "8 áreas", "18 min", "Nível de alerta: Crítico", "OSM ativo", "API real ativa", score climático 35 quando indisponível, telemetria 28 °C/50 %/10 km/h NE. Rótulos "API ao vivo"/"Dados em tempo real". | ver FRONTEND-INVENTORY §5 | **Corrigido** |
| F-11 | P1 | Mapa: a cartografia é real (Leaflet + OSM, EPSG:3857), mas o foco do incêndio é desenhado no **centro da área protegida**, as equipes ficam em posições inventadas (`centro + idx·0,01°`) e os alertas FIRMS não são plotados. | `OrbitalMapPage.tsx:107-129`; `WarRoomPage.tsx:425-430` | Pendente (Fase 1, PHASE-1 P0-07/P1-01) |
| F-12 | P1 | Risco por área fixado em `low` para toda área vinda da API; o ranking de risco não tem significado. | `services/adapters/protectedAreaAdapter.ts:73` | Mitigado (aviso na tela). Pendente: cálculo no backend (Fase 2) |
| F-13 | P1 | O JWT fica em `localStorage`, sem CSP (`vercel.json` só tem rewrite). | `services/api/authService.ts:15-18` | **Parcial**: CSP estrita no nginx do serviço `web` do Railway (`infra/railway-only`). O token continua em `localStorage` (SECURITY-REVIEW R-07) |
| F-14 | P1 | Vulnerabilidades npm: 12 em runtime (5 altas). | `npm audit --omit=dev` | **Mitigado** (`021dbda`): restam 3 (zod alta, react-router moderada), que exigem upgrade major |
| F-15 | P2 | A AURORA é rule-based com texto fixo e "confiança" fixa por severidade (91/75/65/55 %). | `services/adapters/incidentAdapter.ts:22-43` | Rotulado como demonstrativo. Pendente: Fase 2 |
| F-16 | P2 | Não existem no código: rotas de evacuação, abrigos, envio de comunicação à população, contato com equipes, redirecionamento de viaturas, criação manual de incidente, exportação de relatório. | busca negativa (FRONTEND-INVENTORY §7) | Registrado. **Nenhuma ação de evacuação/mobilização institucional deve ser habilitada sem integração e autorização oficiais** |

## 5. NASA FIRMS — verificação dos 4 problemas conhecidos

| Problema anterior | Existia em `main`? | Correção |
|---|---|---|
| Listagem retornava alertas demonstrativos | Sim (`service.py:120-126`) | Sem chave: lista vazia (`disabled_missing_api_key`). Demo só com `ORBITAL_ALERTS_DEMO_MODE=true`, `source_status=demo` e `is_demo=true` |
| API key ⇒ `source_status="live"` sem dados reais | Sim (`service.py:117-118`) | `live`/`cached` só com dados efetivamente obtidos da NASA, com `fetched_at` real |
| Ingestão não persistia | Sim (`service.py:158-169`) | Continua sem persistir (Fase 1), mas declara isso: `persisted=false` e `status=processed_not_persisted` |
| `records_inserted` sugeria gravação | Sim | `records_inserted=0` sempre. O número real vai em `records_valid` |

Defeitos extras encontrados e corrigidos:

- vazamento da MAP_KEY na mensagem de erro;
- ingestão sem autenticação;
- resposta 200 com texto ("Invalid MAP_KEY.") lida como "zero focos";
- falta de deduplicação e de validação de faixa de coordenadas;
- ids aleatórios a cada consulta (agora determinísticos).

Semântica explícita: **foco de calor = anomalia térmica detectada por satélite, não confirmação de incêndio** (campo `disclaimer` na API e texto fixo na UI).

## 6. Atualização — Sprint 0.1 (03/11/2026)

Estado dos achados acima depois da Sprint 0.1, mais os achados novos desta rodada.

| ID | Grav. | Achado | Estado |
|---|---|---|---|
| X-01 | P1 | `main`/`master` do frontend: **históricos sem ancestral comum** (`git merge-base` vazio) | Estratégia em `ignis-fire-watch/docs/IGNIS/BRANCH-STRATEGY.md`. A execução é decisão do proprietário |
| X-02 | P1 | Sem CI | **Corrigido**: GitHub Actions obrigatório nos dois repositórios (ver SPRINT-0-DELIVERY §8) |
| X-03 | P1 | API de produção 404 | **Diagnosticado**: não existe projeto ou serviço IGNIS na conta Railway autenticada; recuperação = novo provisionamento ([RAILWAY-RECOVERY](RAILWAY-RECOVERY.md)) |
| B-05 | P0 | Seed demo em produção | **Corrigido sem exceção**: o override `SEED_DEMO_DATA` foi removido; seed só em development/test/demo. Procedimento `seed.demo_users` pronto e **não executado** em produção |
| B-22 | P1 | (Codex P1) `.env` com `SEED_DEMO_DATA`, ou o próprio `.env.example` (`POSTGRES_*`), derrubava o boot com `extra_forbidden` | **Corrigido** (`17bdd29`), com testes que carregam `.env` real |
| B-23 | P1 | `APP_ENV` livre: um erro de digitação (`prod`) virava ambiente não operacional, com seed e segredo dev permitidos. Sem `APP_ENV` no container, o padrão era `development` | **Corrigido**: lista fechada + entrypoint exige `APP_ENV` (fail-closed) |
| B-24 | P1 | `POST /admin/users` aceitava qualquer senha (inclusive `admin@123`) e qualquer string como `role` (papel inválido quebrava a autorização do usuário) | **Corrigido** (`f9d261b`): senha de 12 a 72 bytes, lista de senhas publicadas, `role` validado contra o enum, e-mail validado |
| B-25 | P1 | `JWT_ALGORITHM` livre (aceitaria `none`); tokens sem `exp`/`iat`/`sub` aceitos | **Corrigido**: só família HS; claims obrigatórias |
| B-26 | P1 | Sem `.dockerignore` (`.env`, `.venv`, `.git` iam para a imagem); container como root | **Corrigido** (`85e60b6`) |
| B-27 | P2 | Protocolo público gerado com `random` (PRNG previsível) | **Corrigido**: `secrets.choice` |
| B-28 | P2 | Em ambiente operacional, `DATABASE_URL` ausente caía no padrão de desenvolvimento com a senha publicada | **Corrigido**: boot recusado |
| F-14 | P1 | Vulnerabilidades npm de runtime | **Corrigido**: 0 (zod 4.6.7, react-router 7.18.5) |
| F-17 | P1 | (Codex P2) Botão de ativação de protocolo ficava indisponível para sempre após falha da API | **Corrigido** (`990b689`), validado no navegador |
| F-18 | P2 | Protocolo inexistente (404) aparecia como "serviço indisponível" e acionava a faixa de falha (achado na validação da 0.1) | **Corrigido** (`23df18b`) |
