# IGNIS — Entrega da Sprint 0

Data: 03/11/2026. Executor: agente Claude Code (modo autônomo), a pedido de Elias Andrade.
Estado da sprint: **parcialmente concluída**. Os critérios técnicos estão atendidos. Pendências que dependem do proprietário: §7.

## 1. Pull requests

| Repositório | PR | Branch → base | Commits |
|---|---|---|---|
| ignis-orbital-api | [#3](https://github.com/eliasandraade/ignis-orbital-api/pull/3) | `audit/ignis-sprint-0` → `main` | `139f425`, `ca9a0d4`, `6b45a9d`, `6450dd6` + este documento |
| ignis-fire-watch | [#4](https://github.com/eliasandraade/ignis-fire-watch/pull/4) | `audit/ignis-sprint-0` → `master` | `7c7f26f`, `042915a`, `0a5fa0e`, `3c0c59f`, `021dbda`, `086bdc3` |
| orkengov | — | somente leitura | nenhum |

Checks na abertura:
- **GitGuardian:** OK nos dois PRs.
- **Vercel (preview, frontend):** um projeto concluído; o outro estava em deploy.
- **CI própria de testes:** não existe em nenhum repositório (X-02).
- Nada foi mergeado nem enviado para produção.

## 2. Baseline (antes de qualquer mudança)

| Repo | Comando | Resultado |
|---|---|---|
| backend `main` `3e22ecb` | `uv venv` + `uv pip install -e ".[dev]"` (Python 3.12.10) | OK; **sem lockfile** |
| | `ruff check .` | All checks passed |
| | `pytest` | **110 passed** (sem banco; AsyncMock) |
| frontend `master` `e56d02f` | `npm ci` (Node 22.19, npm 10.9) | OK (398 pacotes) |
| | `tsc -p tsconfig.app.json --noEmit` | **6 erros** (`internalReportAdapter.ts`: campos ausentes em `ApiReportRead`) |
| | `npm run lint` | **crash**: `TypeError … allowShortCircuit` (eslint 9.39.4 × typescript-eslint 8.11.0) |
| | `npm run build` | OK (o Vite não checa tipos) |
| | testes | **inexistentes** |

## 3. Evidências após a Sprint 0

### 3.1 Backend (`audit/ignis-sprint-0`)

| Comando | Resultado |
|---|---|
| `ruff check .` | All checks passed |
| `pytest` | **158 passed**, 0 failed (51 novos; 3 testes antigos de endpoint FIRMS removidos, 2 deles fixavam o comportamento incorreto). Cobertura total: 78 %; `nasa_firms/client.py` 100 %, `service.py` 97 %, `orbital_alerts_router.py` 100 %, `rate_limit.py` 83 % |
| `uvx pip-audit` (81 pacotes) | No known vulnerabilities found |
| Ruff format | 12 arquivos fora do formato **já no baseline**; o formato não é aplicado pelo projeto (só lint) |

### 3.2 Frontend (`audit/ignis-sprint-0`)

| Comando | Resultado |
|---|---|
| `npm run typecheck` | 0 erros |
| `npm run lint` | 0 erros, 10 warnings (`react-refresh/only-export-components`) |
| `npm test` (Vitest) | **24 passed** (3 arquivos: estados de ação/integridade, FIRMS, contratos/sessão) |
| `npm run build` | OK |
| `npm audit --omit=dev` | 3 vulnerabilidades (2 moderadas, 1 alta). Antes: 12 (5 altas) |
| `npm audit` (com dev) | 22. Antes: 32 |

### 3.3 Banco e migrations (PostGIS isolado)

Ambiente:
- container descartável `postgis/postgis:16-3.4` na porta 55432, banco `ignis_test`;
- removido ao final;
- **nenhum banco de produção foi acessado**.

| Passo | Resultado |
|---|---|
| `alembic upgrade head` | OK até `438a82832b4f` (15 revisões) |
| `alembic downgrade base` → `upgrade head` | OK |
| `alembic check` | Ruído das tabelas `tiger`/`topology` do PostGIS (falta `include_object`). **Drift real:** 15 colunas `timestamptz` no banco vs `DateTime()` nos modelos (B-13) |
| `python -m seed` (2×) | OK e idempotente |
| `APP_ENV=production python -m seed` sem opt-in | `DemoSeedRefusedError` (esperado) |

### 3.4 Smoke test da API local (uvicorn + PostGIS isolado)

| Verificação | Resultado |
|---|---|
| `GET /health`, `GET /ready` | 200 / `{"database":"connected"}` |
| Boot com `CORS_ORIGINS=a,b` | **Falhava** (`SettingsError`) → corrigido (`6b45a9d`) |
| `GET /api/v1/orbital-alerts` sem chave | `items=[]`, `source_status=disabled_missing_api_key`, `persisted=false` |
| `POST /api/v1/orbital-alerts/ingest` sem token | 401 |
| `POST /api/v1/reports` com `latitude=500` | 422 |
| Denúncia anônima com nome | gravada com `reporter_name` nulo (conferido no banco) |
| 11 logins inválidos em 1 min | 10× 401, depois 429 |

### 3.5 Navegador (built-in browser)

| Cenário | Resultado |
|---|---|
| Frontend demo (`VITE_USE_API=false`) | Faixa "MODO DEMONSTRATIVO" visível; "Registrar Ativação de Protocolo" → toast "Simulação — nenhum protocolo foi ativado", botão "Simulação concluída — nada registrado"; checklist rotulado |
| Frontend API (`VITE_USE_API=true` → API local) | `/select-profile` → `/login`; login com usuário do seed **local**; dashboard com equipes da API (antes sempre mock); FIRMS "desativada (chave não configurada)" com "—"; Open-Meteo real com horário; "Registrar mobilização" → persistido (`mobilized` + `team.updated` na auditoria; antes dava 422) |
| API derrubada com sessão aberta | Faixa "API indisponível em 2 consultas… Não use para decisão operacional" |

### 3.6 Verificações somente leitura em produção

| URL | Resultado |
|---|---|
| `https://ignis-api-production.up.railway.app/health` e `/api/v1/orbital-alerts` | **404 "Application not found"** (Railway) |
| `https://ignis-fire-watch.vercel.app`, `https://ignis-fire-watch-main.vercel.app` | 200 |

Nenhuma credencial foi usada contra produção.

## 4. Correções entregues

### Backend

| Achado | Correção | Commit | Testes |
|---|---|---|---|
| B-01, B-02 FIRMS demo como `live` e `records_inserted` fictício | Estados honestos: `demo` opt-in, lista vazia sem chave, `processed_not_persisted`, `records_inserted=0`, `persisted=false` | `ca9a0d4` | `tests/test_orbital_alerts_contract.py` |
| B-03 ingestão sem autenticação | `require_role(ADMIN)` + auditoria | `ca9a0d4` | idem (5 casos de papel) |
| B-04 vazamento da MAP_KEY | Mensagens só com o tipo da exceção; corpo não-CSV detectado | `ca9a0d4` | 2 testes de não-vazamento |
| B-05 seed demo em produção | `entrypoint.sh` + `ensure_seed_allowed()` | `139f425` | 3 testes + execução real |
| B-06 segredo JWT padrão em produção | Validador de `Settings` | `139f425` | 5 testes |
| B-08 `/ready` vaza DSN | Resposta genérica + log do tipo | `139f425` | 1 teste |
| B-09 denúncia pública sem validação | `ReportCreate` limitado; anonimato efetivo | `139f425` | 12 testes |
| B-10 sem rate limiting | `app/core/rate_limit.py` (em memória) | `139f425` | 5 testes |
| B-11 CORS por vírgulas derruba o boot | `NoDecode` | `6b45a9d` | 2 testes |

### Frontend

| Achado | Correção | Commit |
|---|---|---|
| X-04 lint quebrado, sem typecheck/testes | typescript-eslint ^8.46, scripts e Vitest | `7c7f26f` |
| F-08 papel sem login, logout inseguro, 401 → demo | Guards e `/select-profile` por modo; `clearSession`; `handleUnauthorized` | `042915a` |
| F-09 contratos quebrados | `apiFetchItems`, `TEAM_STATUS_TO_API`, tipos de denúncia válidos, tipos TS | `042915a` |
| F-01, F-07, F-10 dados demo/inventados como reais | Faixa global, sem mock em erro (incidentes/FIRMS), rótulos honestos, hardcodes removidos | `0a5fa0e` |
| F-02…F-06 confirmações falsas | `actionState`, confirmação, simulação rotulada, desabilitado em modo API | `3c0c59f` |
| F-14 dependências vulneráveis | `npm audit fix` (sem `--force`) | `021dbda` |

## 5. Critérios de aceitação da Sprint 0

| Critério | Situação |
|---|---|
| Componentes operacionais críticos auditados | ✅ AUDIT-REPORT, FRONTEND-INVENTORY, API-INVENTORY |
| Dados demonstrativos não apresentados como reais | ✅ com ressalva: hooks de área e war room ainda usam mock em falha da API, sob a faixa "API indisponível" (Fase 1 P0-08) |
| Operações simuladas sem falsas confirmações | ✅ |
| Inconsistências FIRMS corrigidas ou desabilitadas | ✅ (persistência planejada: Fase 1 P0-03/04) |
| Endpoints sensíveis com autorização adequada | ✅ para o modelo de papéis atual. ⚠️ Não há isolamento entre instituições (B-07, Fase 4): uso restrito a uma instituição |
| Alterações com testes pertinentes | ✅ backend +51, frontend +24 |
| Builds e testes com resultados registrados | ✅ §2–3 |
| Documentação obrigatória disponível | ✅ 10 documentos (índice em `docs/IGNIS/README.md`) |
| Pendências de maior risco identificadas e classificadas | ✅ SECURITY-REVIEW §3 |
| Backlog da Fase 1 pronto | ✅ PHASE-1-BACKLOG |
| PRs abertos | ✅ #3 (backend), #4 (frontend) |

**Por que "parcialmente concluída":** a sprint não pode ser dada como encerrada sem as ações do proprietário (§7):
- confirmar o segredo JWT de produção (bloqueia o merge do backend);
- tratar os usuários demo em bancos existentes;
- decidir a hospedagem da API (hoje 404) e a branch padrão do frontend.

Além disso, não existe CI que rode os testes nos PRs.

## 6. Limitações desta execução

- Não houve teste contra a API de produção (fora do ar), nem com chave NASA real. Os estados `live`/`cached` foram verificados com respostas simuladas da NASA e transporte `httpx.MockTransport`; não foram executados contra o FIRMS real.
- Não houve teste E2E automatizado (Playwright). A verificação de UI foi manual no navegador.
- Os warnings de lint (10) e o formato Ruff (12 arquivos) são preexistentes e não foram tratados.
- O PR #2 do backend não foi alterado nem fechado (decisão do proprietário, X-05).

## 7. Pendências que exigem o proprietário

1. **Segredo JWT de produção** com ≥ 32 caracteres antes do merge do PR #3 (R-03).
2. **Usuários demo em bancos existentes** (`admin@ignis-orbital.com` etc.): desativar ou trocar senhas (R-01).
3. **Hospedagem da API**: a URL documentada está fora do ar (X-03). Decidir plataforma e ambiente.
4. **Branch padrão do frontend**: tornar `master` padrão ou alinhar `main` (X-01).
5. **PR #2 do backend**: fechar ou rebasear conforme PHASE-1 P0-05 (X-05).
6. **Chave NASA FIRMS** para a Fase 1 (cadastro gratuito, credencial do proprietário).
7. **Parcerias institucionais** (CBMCE, Defesa Civil, municípios): pré-requisito das Fases 4–5. Nada foi presumido.
