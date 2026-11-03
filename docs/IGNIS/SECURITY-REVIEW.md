# IGNIS — Revisão de Segurança (Sprint 0)

Data: 03/11/2026. Escopo: backend `ignis-orbital-api` e frontend `ignis-fire-watch`. Os IDs `B-`/`F-`/`X-` remetem ao [AUDIT-REPORT](AUDIT-REPORT.md).

> O IGNIS pretende atender instituições de emergência. Aqui, uma **confirmação falsa** ou um **dado fictício apresentado como real** conta como falha de segurança, no mesmo nível de um acesso indevido.

## 1. Ativos e atores

**Ativos:**
- incidentes e sua timeline;
- denúncias de cidadãos, com dados pessoais (nome e contato) e localização;
- usuários e papéis;
- trilha de auditoria;
- credenciais (`JWT_SECRET_KEY`, `NASA_FIRMS_MAP_KEY`, `DATABASE_URL`);
- **confiabilidade da informação exibida**.

| Ator | Capacidade |
|---|---|
| Visitante anônimo | Endpoints públicos: denúncia, consulta de protocolo, AURORA chat, clima, geocoding, áreas protegidas e alertas orbitais |
| Cidadão | Envia denúncia e consulta o protocolo |
| Usuário `campo` / `gestor` / `orgao` / `admin` | Hierarquia linear (`app/dependencies.py:14-20`) |
| Usuário de **outra instituição** | Hoje é indistinguível: não há modelo de instituição (B-07) |
| Provedor externo (NASA, Open-Meteo, Nominatim) | Pode falhar, atrasar ou responder com formato inesperado |
| Atacante com XSS no frontend | Leria o JWT em `localStorage` (F-13) |

## 2. Ameaças × controles

| Ameaça | Antes da Sprint 0 | Depois da Sprint 0 | Risco residual |
|---|---|---|---|
| Forjar token de admin | Segredo padrão aceito em produção (B-06) | Boot recusa segredo publicado ou com menos de 32 caracteres (`app/config.py`, `test_sprint0_security.py`) | Médio: sem rotação, sem revogação e JWT de 8 h (B-21) |
| Login com senha publicada | Seed com `admin@123` executado em todo boot, inclusive em produção (B-05) | Seed ignorado em produção, salvo com `SEED_DEMO_DATA=true`; `ensure_seed_allowed()` | **Alto se algum banco de produção já foi semeado**: ver R-01 |
| Força bruta no login | Nenhum limite | 10 req/min/IP por processo (`app/core/rate_limit.py`) | Médio: em memória e por worker, sem lockout por conta |
| Acesso administrativo sem autorização | `POST /orbital-alerts/ingest` aberto (B-03). Frontend dava UI de admin sem login (F-08) | Ingestão exige ADMIN e é auditada. `/select-profile` só em modo demo. Logout apaga token. 401 encerra a sessão | Baixo: autorização efetiva no backend (`require_role`) |
| Alteração de incidente por usuário sem permissão | `require_role(GESTOR)` em todas as escritas | Sem mudança | **Alto em cenário multi-institucional**: qualquer gestor altera qualquer incidente (B-07). Transições livres (B-12) |
| Escalada de privilégio | Só ADMIN cria ou altera usuários; o papel é relido do banco a cada requisição | Sem mudança | Baixo. Falta proteção do "último admin" (B-20) |
| Acesso entre instituições | Sem modelo de organização | Sem mudança (fora do escopo seguro da sprint) | **Bloqueante para uso multi-institucional**: Fase 4 |
| Exposição de credenciais | MAP_KEY na mensagem de erro (B-04). DSN no `/ready` (B-08) | Só o tipo da exceção é exposto; `/ready` genérico; testes de não-vazamento | Baixo |
| Dados sensíveis em endpoint público | `/reports/lookup` já usava schema sem dados pessoais. Denúncia anônima guardava nome | O validador descarta nome e contato quando `is_anonymous` | Médio: o `POST /reports` devolve `ReportRead` ao próprio remetente (inclui contato informado). Aceitável, mas revisar com LGPD |
| Injeção e dados inválidos | Denúncia pública sem limites (B-09) | Limites de tamanho, faixas geográficas, URLs só `http(s)`, `extra="forbid"` | Baixo. ORM parametrizado (SQLAlchemy), sem SQL dinâmico |
| Abuso de provedores externos via API | Geocoding e clima sem limite; FIRMS consultado em todo `ingest` | Rate limit; backoff de 5 min após falha do FIRMS; cache | Médio: cache por processo |
| Operação crítica sem trilha | Ativação de protocolo, validação e conversão já auditavam. Ingestão não | Ingestão auditada | Médio: `incident events` sem audit (B-19); auditoria mutável |
| **Confirmação falsa / dado fictício como real** | Endêmico no frontend (F-01…F-07, F-10) e no FIRMS (B-01, B-02) | Estados de ação explícitos; faixa global de integridade; FIRMS com estados honestos; mocks sem alegações institucionais | Médio: em modo API ainda há fallback para mock em hooks secundários (área, war room) quando a consulta falha, sinalizado pela faixa "API indisponível" |
| Indisponibilidade de fonte externa | FIRMS: "chave ausente" mostrado em qualquer falha | `unavailable` explícito, lista vazia, mensagem segura | Baixo |
| XSS → roubo de sessão | JWT em `localStorage`, sem CSP | Sem mudança | Médio (R-07) |
| Dependências vulneráveis | npm: 12 em runtime (5 altas); Python: 0 conhecidas | npm: 3 restantes (zod alta, react-router moderada) | Médio (R-08) |
| Personificação institucional | Mocks e seed com e-mails `.gov.br` reais e "notificação enviada à SEMACE/IBAMA/Defesa Civil" | Mocks do frontend corrigidos | Médio: o seed do backend ainda usa domínios reais (B-16) |

## 3. Riscos residuais e ações do proprietário

| ID | Risco | Ação recomendada | Responsável |
|---|---|---|---|
| R-01 | Qualquer banco que já rodou o entrypoint antigo em produção contém `admin@ignis-orbital.com` / `admin@123` e outros 3 usuários com senhas publicadas | Antes de qualquer exposição pública: desativar ou trocar a senha desses usuários (`PATCH /api/v1/admin/users/{id}` com `is_active=false`), ou recriar o banco. A Sprint 0 **não** tocou em produção | Proprietário |
| R-02 | Sem isolamento entre instituições | Não habilitar acesso de mais de uma instituição antes da Fase 4 | Proprietário + Fase 4 |
| R-03 | `JWT_SECRET_KEY` atual de produção pode ser fraco | Antes do merge do PR do backend: confirmar no Railway uma chave com ≥ 32 caracteres. Senão o novo boot **falha de propósito** | Proprietário |
| R-04 | Rate limit em memória por processo | Mover para Redis ou para a borda (Cloudflare/Railway) na Fase 1; ligar `TRUST_PROXY_HEADERS=true` só atrás de proxy confiável | Fase 1 |
| R-05 | Transições de incidente livres; ativação de protocolo sem segundo fator | Máquina de estados + motivo obrigatório + papel mínimo por transição | Fase 1 (P1-07) |
| R-06 | Auditoria mutável, sem IP e user agent | Tabela append-only (revogar UPDATE/DELETE do usuário da aplicação), IP e request id | Fase 3 |
| R-07 | JWT em `localStorage`, sem CSP | Cookie `HttpOnly; Secure; SameSite=Strict` + CSRF, ou CSP estrita na Vercel (`vercel.json` headers) | Fase 1 (P1-08) |
| R-08 | zod < 4.6.6 (alta) e react-router 6.x (moderada) | Upgrade major com testes de formulário e rotas | Fase 1 (P2-03) |
| R-09 | `/docs` público em produção | Proteger ou desabilitar com `APP_ENV=production`, mantendo o OpenAPI exportado no repositório | Fase 4 |
| R-10 | Tiles do `tile.openstreetmap.org` em produção institucional violam a política de uso da OSMF | Provedor de tiles contratado ou próprio (ver ARCHITECTURE §4) | Fase 1 |
| R-11 | Seed do backend com domínios institucionais reais | Trocar por `*.example` e documentar a migração de logins demo | Fase 1 (P2-01) |

## 4. Configuração segura de produção (checklist)

- [ ] `APP_ENV=production`, `DEBUG=false`
- [ ] `JWT_SECRET_KEY` aleatória com ≥ 32 caracteres (`python -c "import secrets; print(secrets.token_hex(32))"`)
- [ ] `SEED_DEMO_DATA` ausente ou `false`; usuários demo inexistentes ou desativados (R-01)
- [ ] `ORBITAL_ALERTS_DEMO_MODE=false`
- [ ] `CORS_ORIGINS` só com as origens do frontend oficial
- [ ] `TRUST_PROXY_HEADERS=true` somente atrás do proxy do Railway
- [ ] `NASA_FIRMS_MAP_KEY` configurada via cofre de variáveis, nunca no repositório
- [ ] Frontend: `VITE_USE_API=true` e `VITE_API_URL` apontando para a API ativa (hoje 404, X-03)

## 5. O que foi verificado e como

| Controle | Verificação |
|---|---|
| Segredo JWT em produção | `tests/test_sprint0_security.py::test_production_rejects_insecure_jwt_secret` (3 casos) |
| Seed em produção | Testes unitários + execução real: `APP_ENV=production python -m seed` → `DemoSeedRefusedError` |
| Ingestão restrita | `tests/test_orbital_alerts_contract.py` (sem token → 401/403; publico/campo/gestor/orgao → 403) + `curl` local → 401 |
| Não-vazamento da MAP_KEY | 2 testes com `HTTPStatusError` contendo a chave na URL |
| Validação de denúncia | 9 casos inválidos + `curl` local (lat=500 → 422; anônima → `reporter_name` nulo no banco) |
| Rate limit | Teste (11ª tentativa → 429) + `curl` local + UI exibindo a mensagem 429 |
| 401 → fim de sessão | `src/services/contracts.test.ts` (frontend) |
| Dependências | `pip-audit` (81 pacotes, 0 vulnerabilidades); `npm audit` antes e depois |

## 6. Atualização — Sprint 0.1 (03/11/2026)

| Tema | Verificação | Resultado |
|---|---|---|
| Endpoints administrativos | `/api/v1/admin/*`, `/orbital-alerts/ingest`, criação de times/recursos: `require_role` no backend. Papel relido do banco a cada requisição | OK. Criação de usuário agora valida papel, senha e e-mail (B-24) |
| Seeds e credenciais demo em produção | Seed só em development/test/demo, sem override (teste + CI). Senhas publicadas recusadas na API. `seed.demo_users` detecta e revoga contas existentes | **R-01 continua aberto até o proprietário executar o procedimento** em qualquer banco reaproveitado |
| Proteção do JWT | Segredo forte obrigatório em staging e production; algoritmos só HS256/384/512; claims `exp`/`iat`/`sub` obrigatórias; expiração de 5–1440 min; testes para token sem assinatura, expirado e sem claim | OK. Pendentes: refresh, revogação e cookie HttpOnly (R-07) |
| Variáveis ausentes ou inválidas | `APP_ENV` obrigatório e de lista fechada; `JWT_SECRET_KEY`/`DATABASE_URL` padrão recusados em ambiente operacional; `.env` com chaves desconhecidas não derruba o boot | Fail-closed (testes + CI + container verificado) |
| Criação acidental de contas com senha pública | Seed bloqueado em ambiente operacional e API recusa senhas publicadas e curtas | OK |
| Dependências do frontend | `npm audit --omit=dev`: **0** (antes 3, original 12). Total com dev: ver SPRINT-0-DELIVERY | CI falha com high/critical em runtime |
| Dependências do backend | `pip-audit`: 0 vulnerabilidades conhecidas (CI) | Sem lockfile (Sonar S8565): Fase 1 P0-02 |
| Falha de serviços externos | FIRMS: `unavailable` + backoff; Open-Meteo: `unavailable` e score "—" na UI; lookup de protocolo: 404 vira "não encontrado", 5xx vira erro explícito; Sala de Crise recupera após a API voltar | OK (testes + navegador) |
| Imagem de container | Usuário não-root; `.dockerignore`; container sem `APP_ENV` não inicia | OK (CI) |

**Riscos residuais atualizados:**
- **R-03** vira condição de boot: o deploy falha se o segredo for fraco.
- **R-08** resolvido.
- **Novo R-12:** o projeto Railway da API não existe mais (X-03). Qualquer banco antigo restaurado deve passar por `seed.demo_users check`.
