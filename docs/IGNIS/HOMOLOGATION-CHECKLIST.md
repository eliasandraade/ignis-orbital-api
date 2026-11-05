# IGNIS — Checklist de homologação (Railway)

Rode este checklist em **staging** primeiro e, em **production**, a mesma lista, antes de anunciar a publicação. Em cada item, registre a data, o responsável e a evidência. O plano de implantação está em [RAILWAY-DEPLOYMENT.md](RAILWAY-DEPLOYMENT.md); o estado real e os IDs, em [RAILWAY-PROVISIONING-REPORT.md](RAILWAY-PROVISIONING-REPORT.md).

Arquitetura same-origin: só o `ignis-web` é público, e a API fica atrás de `$WEB/api/v1`. Variável usada nos comandos: `WEB=https://ignis-web-staging.up.railway.app` (produção: `https://ignis.andradesystems.com.br`).

Coluna **Staging 04/11/2026**: o resultado executado nesta data. "—" indica item não executado.

## A. Infraestrutura e isolamento

| # | Verificação | Como | Esperado | Staging 04/11/2026 |
|---|---|---|---|---|
| H-01 | O IaC corresponde ao projeto | `railway environment link <amb>`; `railway config plan` (PowerShell, RAILWAY-DEPLOYMENT §1) | Só a diferença cosmética `restartPolicyType (null → "ON_FAILURE")` (o padrão do Railway é lido como `null`) | OK, nos dois ambientes |
| H-02 | Branch de cada ambiente | Railway → serviço → *Source* | staging: `staging`; production: `production` | OK |
| H-03 | *Wait for CI* ativo | `config plan` sem diferença em `source.checkSuites`; deploys `WAITING` até a CI | Ligado em `ignis-api`, `ignis-web`, `ignis-ingest` | OK (deploys `WAITING` → `SUCCESS`/`SKIPPED` observados) |
| H-04 | Banco e API sem exposição pública | Railway → *Networking* | Só o `ignis-web` tem domínio; sem TCP proxy | OK |
| H-05 | Segredos distintos por ambiente e selados | Railway → *Variables* | Gerados por ambiente; selados | Gerados por ambiente (stdin). **Selagem pendente (B7)** |
| H-06 | Guarda de ambiente | `APP_ENV=production` temporário no `ignis-api` de staging | O pre-deploy falha; a versão anterior continua | — (coberto por teste; não repetido no Railway) |

## B. API

| # | Verificação | Como | Esperado | Staging 04/11/2026 |
|---|---|---|---|---|
| H-07 | Pre-deploy migrou | Log do deploy | `alembic upgrade head` até `a015` | OK |
| H-08 | Seed bloqueado | Log do `ignis-api` | "Seed demonstrativo ignorado" | OK |
| H-09 | Saúde | `curl -sf $WEB/health; curl -sf $WEB/ready` | `{"status":"ok",…}` sem versão nem ambiente; `database: connected` | OK |
| H-10 | Ingestão protegida | `POST $WEB/api/v1/orbital-alerts/ingest` sem token | 401 | OK |
| H-11 | CORS | Preflight com `Origin: $WEB` e com uma origem estranha | 200 com `allow-origin` / 400 sem o header | OK |
| H-12 | IP do cliente | 12 logins inválidos, com `X-Real-IP`/`X-Forwarded-For` forjados | 429 na 11ª tentativa (a borda sobrescreve o header) | OK. Ainda não testado a partir de uma segunda rede |
| H-13 | Sem contas demo | `python -m seed.demo_users check` (shell) | exit 0 | — (sem SSH). Equivalente: só contas `*.homologacao@example.org` e `e2e.*` na listagem do cockpit |
| H-14 | Primeiro admin | RAILWAY-PROVISIONING-REPORT §7 (staging) / §12 (produção) | Auditoria `user.bootstrap_admin_created` | OK em staging |
| H-25 | Jurisdições oficiais | Log do pre-deploy | "184 municípios no arquivo; inseridas 185"; `GET $WEB/api/v1/jurisdictions/municipalities` → 184 | OK |
| H-26 | Malha íntegra na imagem | `python -m seed.jurisdictions --verify-files` | "Arquivos conferem" | Implícito: o pre-deploy aborta com SHA divergente |
| H-27 | FIRMS com chave real | Rodada com `NASA_FIRMS_MAP_KEY` | `records_inserted > 0` | **Pendente**: sem chave; FIRMS `disabled/missing_api_key` |
| H-28 | Reexecução idempotente | 2ª rodada | 0 novos | OK (INPE: ETag/304, 0 novos) |
| H-29 | Ingestão manual auditada | `POST /ingest` com token de admin | 202 + `orbital_ingest.requested` | OK |
| H-30 | Cron de staging | `INGEST.staging.cron = true` no IaC → apply | Execuções agendadas sem `error`; nenhuma `running` > 15 min | Ligado. Em 05/11 00:42 UTC: 23/23 rodadas INPE `ok` em 5,7 h, intervalos de 12,7–17 min, nenhuma presa. Observação de 48 h **pendente** (até 06/11 19:00 UTC) |
| H-31 | Recuperação após queda | Restart no meio de uma rodada | A rodada seguinte marca `abandoned` e segue | — |
| H-32 | Fonte indisponível | URL do INPE inalcançável numa rodada | `unavailable`/`connection_error`, exit 2; o portal mostra "fonte indisponível" e mantém o último sucesso | OK |
| H-33 | Aurora experimental | `POST $WEB/api/v1/aurora/chat` | 404 | OK |
| H-34 | Denúncias fechadas | `GET $WEB/api/v1/reports/intake`; `POST $WEB/api/v1/reports` | `accepting:false`; 503 | OK (`accepting:false`; formulário ausente, pelo E2E) |

## C. Deploy condicionado à CI

| # | Verificação | Como | Esperado | Staging 04/11/2026 |
|---|---|---|---|---|
| H-15 | Promoção | `promote.yml` com o HEAD homologado | `production` avança por fast-forward; o Railway implanta o mesmo SHA | **Bloqueado (B1)** |
| H-16 | CI vermelha bloqueia | Push de um commit com teste falhando num branch descartável apontado temporariamente | Deploy descartado | — |
| H-17 | Mudança sem arquivo observado | Push que só altera docs, `.gitignore` ou `.railway` | Deploy `SKIPPED` | OK (`37c6b66` → `SKIPPED`) |

## D. Frontend

| # | Verificação | Como | Esperado | Staging 04/11/2026 |
|---|---|---|---|---|
| H-18 | Saúde e SPA | `curl -sf $WEB/healthz`; deep link | `ok`; o app carrega | OK |
| H-19 | Headers e CSP | `curl -sI $WEB/` | `connect-src 'self'`; `X-Frame-Options: DENY`; `nosniff`; HSTS; HTTP→HTTPS 301 | OK |
| H-20 | Integração real | E2E completo contra `$WEB` | Todos os testes passam | OK (ADMIN-VALIDATION-GUIDE §5) |
| H-21 | Sem modo demonstrativo | Varredura do bundle na CI | Sem mocks nem texto acadêmico | OK |
| H-35 | Documentação da API não exposta | `curl $WEB/docs`, `$WEB/openapi.json` | SPA (não a API) | OK |
| H-36 | Compressão | GeoJSON com `Accept-Encoding: gzip` | `Content-Encoding: gzip` (1.026 KB → 338 KB) | OK |

## E. Operação

| # | Verificação | Como | Esperado | Staging 04/11/2026 |
|---|---|---|---|---|
| H-22 | Backup e restauração | Backup de volume + `pg_dump`; restaurar num serviço temporário | Restauração íntegra | Agendados. Produção: 1º diário OK (04/11 21:43 UTC). Staging: 1º diário previsto para 02:06 UTC. **Restauração não testada** |
| H-23 | Rollback | Rollback para o deploy anterior do `ignis-web` | Volta em < 5 min; `/healthz` ok | OK: 8 s para voltar e 8 s para avançar |
| H-24 | Alertas | Forçar falha | O alerta chega | **Pendente (B8)** |
| H-37 | Reinício | Restart do `ignis-postgis` e do `ignis-api` | Dados preservados; `/ready` ok | OK (2 s; 320 focos e 184 municípios preservados) |
| H-38 | Logs sem credenciais | Varredura dos logs dos 4 serviços | Sem URL de banco, Bearer, `password=` ou senhas | OK |

## F. Publicação da versão de validação em produção

- [ ] B1: pilha de PRs mergeada; `promote.yml` executado nos dois repositórios.
- [x] B2: DNS (CNAME + TXT) criado; `railway domain status` com `verified: true` e certificado emitido (05/11/2026).
- [ ] B9/B10: Vercel desconectada; `master` como branch padrão do web (PRODUCTION-PROMOTION-RUNBOOK §0).
- [ ] B3: incidentes GitGuardian classificados; CI dos PRs verde.
- [ ] B4: primeiro admin de produção criado pelo proprietário (§12 do relatório); `demo_users check` exit 0.
- [ ] A–E repetidos em produção, exceto H-06, H-12 e H-16, que podem usar as evidências de staging.
- [ ] Denúncias continuam fechadas (`accepting:false`) até a decisão D-1 (LGPD).
- [ ] Ingestão de produção: só por decisão do proprietário (D-6).
