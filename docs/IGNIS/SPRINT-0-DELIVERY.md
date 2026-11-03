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

---

# Sprint 0.1 — Fechamento técnico e validação (03/11/2026)

Objetivo: destravar a revisão dos PRs #3 e #4, estabelecer uma CI real e preparar uma decisão segura de merge. A Fase 1 **não** foi iniciada. A única exceção é o lockfile (P0-02), exigido pelo gate de segurança da CI.

## 8. Commits da Sprint 0.1

**ignis-orbital-api** (PR [#3](https://github.com/eliasandraade/ignis-orbital-api/pull/3)):

| Commit | Conteúdo |
|---|---|
| `17bdd29` | Codex P1: `.env` real não derruba o boot; `APP_ENV` fail-closed; seed proibido em staging/production, sem override; JWT só HS |
| `f9d261b` | Senhas publicadas e curtas recusadas; `role` validado; claims JWT obrigatórias |
| `6fb911a` | Issues do Sonar (response_model redundante; justificativas de falsos positivos) |
| `85e60b6` | Imagem não-root, `.dockerignore`, protocolo público com CSPRNG |
| `05c2caf` | CI GitHub Actions |
| `25fbde8` | Procedimento `seed.demo_users` (check/deactivate) |
| `67ff35a` | `uv.lock` + exportações com hash; CI e Docker só com wheels travados; actions fixadas por SHA |
| `cad9203` | Nenhuma credencial de banco no código |
| `3bb5266` | Docs: RAILWAY-RECOVERY, AUDIT-REPORT §6, SECURITY-REVIEW §6 |
| `832a1ef` | Correção do YAML da CI (`:all:` sem aspas) |
| `0fa7996` | Codex P1 nº 2: `seed.bootstrap_admin` + trava contra desativar o último admin |
| `f93ae1d` | Sonar: S2115 justificado (placeholder dev recusado em produção); S5778 |
| `711b7f2` | Testes leem as senhas demo do seed, sem repetir literais (GitGuardian) |
| `aeaa802` | Achados da revisão independente: CRLF no bootstrap, conta demo inativa, segredo/URL/senha triviais, `--reload` só em development, código read-only na imagem, exit codes |

**ignis-fire-watch** (PR [#4](https://github.com/eliasandraade/ignis-fire-watch/pull/4)):

| Commit | Conteúdo |
|---|---|
| `990b689` | Codex P2: a ativação de protocolo volta a ficar disponível quando a API se recupera (máquina de estados pura + 7 testes) |
| `23df18b` | Lookup 404 vira "não encontrado", não falha do serviço (achado na validação) |
| `4eb3df0` | zod 4, @hookform/resolvers 5, react-router 7: **0** vulnerabilidades em runtime |
| `da496df` | CI GitHub Actions + cobertura (Vitest v8) |
| `503a2c6` | Lint ignora `coverage/` |
| `dc22dbb` | BRANCH-STRATEGY (`main` × `master`) |
| `49057bc` | Actions fixadas por SHA |
| `ee92f86` | FRONTEND-INVENTORY atualizado |

## 9. Comentários do Codex

| PR | Apontamento | Estado |
|---|---|---|
| #3 | P1: `SEED_DEMO_DATA` × Pydantic Settings (`extra_forbidden`) | **Resolvido** (`17bdd29`), com resposta e evidência no thread |
| #3 | P1: o procedimento revogaria o único admin, e não há bootstrap em banco operacional novo (levantado na re-revisão de `3bb5266`) | **Resolvido** (`0fa7996`), com resposta e evidência no thread |
| #4 | P2: botão de protocolo indisponível para sempre após falha | **Resolvido** (`990b689`), com resposta e evidência no thread |
| #4 | Re-revisão de `49057bc` | **Sem apontamentos** (`has_any_findings: false`) |
| #3 | Re-revisão de `f93ae1d` | **Não executada.** O Codex respondeu "You have reached your Codex usage limits for code reviews". Como compensação, foi feita uma revisão independente por agente separado (§17) |

## 10. CI (GitHub Actions)

| Repositório | Jobs | Execução de referência |
|---|---|---|
| backend | Lockfile em sincronia · Ruff · Pytest + cobertura (mínimo 75 %) · Migrations em PostGIS 16-3.4 isolado (upgrade/downgrade/upgrade, seed idempotente, seed recusado em production/staging, fluxo bootstrap → revogação de contas demo, healthcheck `/health` e `/ready`, ingestão sem token = 401) · pip-audit (prod + dev) · Docker build (import, não-root, recusa sem `APP_ENV`) · SonarQube Cloud (opt-in) | `0fa7996` → run 41711558917: **todos verdes** (Sonar *skipped*) |
| frontend | Typecheck, lint, Vitest com cobertura, build nos modos API e demo · npm audit (runtime, falha com high/critical) · SonarQube Cloud (opt-in) | `49057bc` → run 41710565355: **todos verdes** (Sonar *skipped*) |

**Prova de que teste com falha reprova o check.** PRs-canário temporários (draft, fechados e com a branch apagada, nada mergeado):

| Repositório | Canário | Run | Resultado |
|---|---|---|---|
| backend | #4 | 41708759577 | `Pytest + cobertura: failure` (`assert 1 == 2`); demais jobs verdes |
| frontend | #5 | 41708802497 | `Typecheck, lint, testes e build: failure` (`expected 1 to be 2`) |

Uma execução falhou por erro meu no workflow (run 41710469969, YAML inválido), corrigido em `832a1ef`. `actionlint` 1.7.7 está limpo nos dois workflows.

## 11. Cobertura

| Escopo | Resultado |
|---|---|
| Backend total (`app/`) | **78,95 %** (2.608 instruções), mínimo exigido na CI: 75 % |
| Backend, módulos alterados | `nasa_firms/client.py` 100 %, `nasa_firms/service.py` 97 %, `orbital_alerts_router.py` 100 %, `config.py` 95 %, `passwords.py` 91 %, `rate_limit.py` 83 % |
| Frontend total (`src/`, exceto `components/ui`) | **5,3 %** de linhas. Páginas e componentes não têm teste, porque o projeto não tinha nenhum até a Sprint 0 |
| Frontend, módulos de lógica alterados | `dataIntegrity` 96 %, `teamAdapter` 96 %, `actionState` 88 %, `client.ts` 87 %, `reportAdapter` 76 %; `protocolActivation` coberto por 7 testes dedicados |

## 12. SonarQube Cloud

- **Backend:** análise automática do SonarQube Cloud ativa. Evolução das issues novas no PR #3:
  - análise inicial: 10;
  - depois da CI e dos locks: 19, com Quality Gate **ERROR** (`new_security_rating` E);
  - em `cad9203`: 4.

  O que foi feito com cada regra:

  | Regras | Tratamento |
  |---|---|
  | S8544, S8541 (deps sem lock / sem `--only-binary`), S7637 (actions sem SHA), S6698 (senha no código) | Corrigidas |
  | S2115 | Falso positivo justificado com NOSONAR em `f93ae1d` |
  | S5778 | Corrigida |
  | S8410 (×2, `Annotated` em `Depends`, MINOR) | Mantida: o projeto inteiro usa `= Depends()`; a mudança será uma migração única |
  | S7504, S7503 em `rate_limit.py` | Falsos positivos anotados no código |

  **Estado final (`f93ae1d`): Quality Gate OK.** Segurança, confiabilidade e manutenibilidade em A; hotspots 100 % revisados; restam 2 issues MINOR (S8410), justificadas.
- **Cobertura no Sonar:** **não publicada.** Exige `SONAR_TOKEN` (segredo inexistente) e desligar a Automatic Analysis; não alterei segredos nem configurações. O job está pronto e ativável pela variável `SONAR_CI_ANALYSIS=true` (§15).
- **Frontend:** não existe projeto no SonarQube Cloud (`eliasandraade_ignis-fire-watch` não encontrado). `sonar-project.properties` e o job opt-in estão prontos.
- **Branch `main` do backend** (preexistente, fora do PR): S2068 nas senhas do seed e dos testes, S6698 no `docker-compose.yml` (senha de dev padrão) e S1244 (floats em testes), todos fora de código operacional. S8565 (sem lockfile) fica resolvido quando o PR #3 for mergeado.

## 13. Vulnerabilidades remanescentes

| Origem | Situação |
|---|---|
| Python, prod e dev (`pip-audit` nos locks com hash) | **0** |
| npm runtime (`npm audit --omit=dev`) | **0** (antes 3; no início da Sprint 0, 12) |
| npm dev/build (`npm audit`) | 22 (1 alta, 2 críticas): `vitest` ≤ 4.1.10 e `tinypool` (críticas), `vite` ≤ 6.4.3 (alta). Afetam o servidor de desenvolvimento e o runner de testes, **não o bundle publicado**. A correção exige vite 6+/vitest 4 (major) → P1 da próxima sprint |
| Imagem Docker | não-root e sem segredos copiados. Sem scanner de imagem (Trivy) ainda → P2 |

## 14. Recomendação de merge

| PR | Recomendação | Fundamento | Condições |
|---|---|---|---|
| **#3 backend** | **Mergear**, desde que a última re-revisão do Codex (`f93ae1d`) não traga apontamento P0/P1 | CI verde em todos os jobs; os dois P1 do Codex resolvidos e validados; não existe deploy ativo no Railway, então o merge **não afeta produção** | Antes do **próximo deploy** (não do merge): seguir RAILWAY-RECOVERY. O boot exige `APP_ENV`, `JWT_SECRET_KEY` forte e `DATABASE_URL` real |
| **#4 frontend** | **Mergear**, com uma decisão consciente sobre deploy | CI verde; Codex sem apontamentos; 0 vulnerabilidades de runtime; elimina dados falsos e confirmações falsas | O merge em `master` **provavelmente publica em produção na Vercel** (`ignis-fire-watch`). Antes, confirmar na Vercel `VITE_USE_API`/`VITE_API_URL`. Com a API fora do ar, a interface mostrará "API indisponível", o comportamento honesto. Se a demo pública precisa continuar funcionando sem API, manter `VITE_USE_API=false` (modo demonstrativo rotulado) |

**Ordem recomendada:**
1. Mergear o #3.
2. Configurar a Vercel e mergear o #4.
3. Provisionar a API conforme RAILWAY-RECOVERY.
4. Apontar o frontend para a nova API.

## 15. Pendências que exigem o proprietário

1. **SonarQube Cloud com cobertura:**
   - desligar a Automatic Analysis no projeto backend;
   - criar o segredo `SONAR_TOKEN` e a variável `SONAR_CI_ANALYSIS=true`;
   - para o frontend, criar o projeto no SonarQube Cloud.
2. **Proteção de branch:**
   - exigir os checks da CI nos dois repositórios (`main` no backend, `master` no frontend);
   - exigir o Quality Gate do Sonar no backend.
3. **Railway:** decidir entre recuperar o projeto antigo (outra conta?) e provisionar um novo (RAILWAY-RECOVERY).
4. **Vercel:** confirmar a *Production Branch* e as variáveis dos dois projetos. Executar a estratégia de BRANCH-STRATEGY (tag de arquivamento + branch padrão `master`).
5. **Usuários demo:**
   - em banco novo, executar `seed.bootstrap_admin`;
   - em banco reaproveitado, executar `bootstrap` → `demo_users check` → `deactivate` (com autorização).
6. **Upgrade das dependências de desenvolvimento do frontend** (vite 6+/vitest 4): agendar.

## 16. Revisão independente (substitui a re-revisão do Codex)

A re-revisão do Codex sobre `f93ae1d` não foi executada porque a conta atingiu o limite de uso. Para não deixar o último incremento sem segunda leitura, um agente separado fez uma revisão adversarial do diff `869382f..f93ae1d`. Ele trabalhou sem as conclusões do autor e em modo somente leitura.

Resultado: **nenhum P0**, 1 P1 e 8 P2.

| # | Grav. | Achado | Tratamento |
|---|---|---|---|
| 1 | P1 | `bootstrap_admin` mantinha o `\r` de pipes do Windows na senha. O admin criado ficava inutilizável e ainda liberava o `deactivate` | **Corrigido** (`aeaa802`) + teste |
| 2 | P2 | Conta demo inativa mantinha o hash da senha publicada e podia ser reativada | **Corrigido**: senha publicada é risco mesmo em conta inativa, e o hash é rotacionado |
| 3 | P2 | Segredo JWT trivial (`"x"*48`, espaços, valor publicado + sufixo) aceito em produção | **Corrigido** + testes |
| 4 | P2 | `DATABASE_URL` vazio, sem senha ou variante dev aceito em produção | **Corrigido** + testes |
| 5 | P2 | Política de senha aceitava espaços, baixa variedade e `Admin@123Admin` | **Corrigido** + testes |
| 6 | P2 | `--reload` em `demo` e código gravável pelo usuário de runtime | **Corrigido**: reload só em `development`; código do root; a CI verifica |
| 7 | P2 | Hash malformado derrubava o `scan` | **Corrigido** + teste |
| 8 | P2 | Exit 2 do `check` colidia com erro de uso do argparse | **Corrigido**: risco = 4; último admin = 3 |
| 9 | P2 | Espaço de protocolos `RP-YYYYMMDD-XXXX` (36⁴ por dia), enumerável apesar do CSPRNG | **Não corrigido** (preexistente; o formato é usado pelo frontend). Fase 1: protocolo mais longo + limite por protocolo |

## 17. GitGuardian

O check `GitGuardian Security Checks` do PR #3 falhou com o incidente **33462092** ("Generic Password").

- **O que foi detectado:** a senha demo `admin@123`, já publicada em `seed/seed_users.py` desde `main`, que eu usei em testes que verificam que ela é **recusada** (commit `f9d261b`).
- **Por que não é um segredo novo:** não é credencial de nenhum sistema ativo. O projeto Railway não existe mais, e o seed não roda em produção.
- **O que foi feito:**
  - os testes passaram a ler o valor do seed, sem novos literais (`711b7f2`);
  - o histórico do PR **não** foi reescrito (sem force-push).
- **Ação do proprietário:** classificar a ocorrência como falso positivo / credencial de teste no painel do GitGuardian. Enquanto isso não for feito, o check permanece vermelho, porque o literal continua no histórico.

## 18. Critério final da Sprint 0.1

| Critério | Situação |
|---|---|
| CI própria (GitHub Actions) sem falhas | ✅ nos últimos HEADs de código |
| Comentários críticos do Codex resolvidos | ✅ 3 de 3 resolvidos, com resposta e evidência nos threads. ⚠️ A re-revisão final do backend não rodou (cota do Codex); foi substituída pela revisão independente (§16), sem P0 e com o P1 corrigido |
| Riscos P0 tratados | ✅ seed/credenciais demo (bloqueio, bootstrap, revogação); `APP_ENV`/segredo/URL fail-closed. B-07 (isolamento entre instituições) continua P0 **arquitetural**, com tratamento definido: uso restrito a uma instituição até a Fase 4 |
| Quality Gate do Sonar no PR #3 | ✅ OK (reanálise de `f93ae1d`); o estado após `aeaa802` está no relatório final |
| Check GitGuardian do PR #3 | ❌ **vermelho** até o proprietário classificar o incidente 33462092 (§17) |

**Conclusão: a Sprint 0.1 não pode ser declarada concluída.** Do lado técnico, tudo o que não depende de acesso privilegiado foi feito e verificado. Restam dois bloqueios que dependem do proprietário:

1. o check do GitGuardian, que exige classificar o incidente no painel;
2. a re-revisão do Codex, que exige créditos.

Não restam falhas de CI próprias nem comentários críticos abertos.
