# IGNIS — Checklist de homologação (Railway)

Use este checklist em **staging** primeiro. Em **production**, rode a mesma lista, com segredos novos, antes de anunciar o go-live.
Para cada item, registre a data, o responsável e a evidência (saída do comando ou captura). O plano de implantação está em [RAILWAY-DEPLOYMENT.md](RAILWAY-DEPLOYMENT.md).

Variáveis usadas nos comandos: `API=https://<dominio-api>` e `WEB=https://<dominio-web>`.

## A. Infraestrutura e isolamento

| # | Verificação | Como | Esperado |
|---|---|---|---|
| H-01 | O IaC corresponde ao projeto | `cd .railway && npm ci && railway config plan` | Nenhuma mudança pendente depois do apply; recursos `postgis`, `postgis-data`, `api`, `web` |
| H-02 | Branch de cada ambiente | Railway → serviço → *Settings → Source* | staging: `main`/`master`; production: `production` nos dois serviços |
| H-03 | *Wait for CI* ativo | Railway → serviço → *Settings* | Ligado em `api` e `web` |
| H-04 | Banco sem exposição pública | Railway → `postgis` → *Networking* | Sem domínio público e sem TCP proxy |
| H-05 | Segredos selados e distintos por ambiente | Railway → *Variables* | `JWT_SECRET_KEY` e `POSTGRES_PASSWORD` selados; os valores de staging ≠ os de production (comparar só a origem da geração, nunca exibir o valor) |
| H-06 | Guarda de ambiente | Copiar temporariamente `APP_ENV=production` para o `api` de staging e redeployar | O pre-deploy falha com "não corresponde ao ambiente Railway"; a versão anterior continua no ar. Reverter a variável |

## B. API

| # | Verificação | Como | Esperado |
|---|---|---|---|
| H-07 | Pre-deploy migrou | Log do deploy (fase *pre-deploy*) | `alembic upgrade head` sem erro; `alembic current` = head |
| H-08 | Seed bloqueado | Log do `api` | Contém "Seed demonstrativo ignorado"; **não** contém "Seeding users" |
| H-09 | Saúde | `curl -sf $API/health; curl -sf $API/ready` | `environment` igual ao ambiente; `database: connected` |
| H-10 | Ingestão protegida | `curl -s -o /dev/null -w '%{http_code}' -X POST $API/api/v1/orbital-alerts/ingest` | `401` |
| H-11 | CORS | Preflight com `Origin: $WEB` e com `Origin: https://evil.example.com` | 200 com `access-control-allow-origin: $WEB` / 400 sem o header |
| H-12 | IP do cliente | 12 logins inválidos seguidos da mesma máquina; depois 1 de outra rede (ex.: 4G) | A 1ª máquina recebe `429`; a outra não. Se todas forem bloqueadas juntas, o `X-Real-IP` não traz o IP do cliente: abrir chamado no Railway e voltar `TRUST_PROXY_HEADERS=false` |
| H-13 | Sem contas demo | `railway ssh --service api` → `python -m seed.demo_users check` | exit 0 |
| H-14 | Primeiro admin | `python -m seed.bootstrap_admin …` (senha no prompt) | Admin criado; auditoria `user.bootstrap_admin_created` |
| H-25 | Jurisdições oficiais | Log do pre-deploy; `railway ssh --service api` → `python -m seed.jurisdictions` | Pre-deploy contém "Jurisdições IBGE: 184 municípios"; a reexecução manual mostra `inseridas 0, atualizadas 0, sem alteração 185` |
| H-27 | FIRMS com chave real (staging) | `railway ssh --service api` → `python -m app.orbital.worker --window-hours 26` | exit 0; 5 execuções `ok`; `records_inserted > 0` na FIRMS; a chave não aparece na saída |
| H-28 | Reexecução idempotente | Repetir H-27 | `records_inserted = 0` em todas as execuções |
| H-29 | Ingestão manual auditada | `POST $API/api/v1/orbital-alerts/ingest` com token de admin → `GET …/ingestion-runs/{run_id}` | 202 com `run_id`; estado final na consulta; `audit_logs` com `orbital_ingest.requested` e o `user_id` |
| H-30 | Job agendado em staging (autorização) | `ENABLE_ORBITAL_INGEST_JOB=true` só em staging → `railway config plan/apply`; observar 48 h | Nenhuma execução `error`; nenhuma `running` com mais de 15 min |
| H-31 | Recuperação após queda | *Restart* do `orbital-ingest` no meio de uma rodada | A rodada seguinte recupera a execução como `abandoned` e roda normalmente |
| H-26 | Malha íntegra na imagem | `railway ssh --service api` → `python -m seed.jurisdictions --verify-files` | "Arquivos conferem" (SHA-256 do conjunto `b12b2f26…a4eff`) |

## C. Deploy condicionado à CI

| # | Verificação | Como | Esperado |
|---|---|---|---|
| H-15 | Promoção | Disparar `promote.yml` (backend e frontend) com o HEAD homologado | Aprovação pedida pelo environment `production`; `production` avança por fast-forward; o Railway de produção faz deploy **do mesmo SHA** de staging, depois do *Wait for CI* |
| H-16 | CI vermelha bloqueia | Apontar temporariamente o `api` de staging para um branch descartável `ci-canary`, dar push de um teste que falha e depois restaurar o branch `main` | Deploy em `WAITING` → *skipped*; a versão anterior continua no ar |
| H-17 | Merge em `main`/`master` não toca produção | Merge qualquer em `main` | Só o ambiente staging redeploya |

## D. Frontend

| # | Verificação | Como | Esperado |
|---|---|---|---|
| H-18 | Saúde e SPA | `curl -sf $WEB/healthz`; abrir `$WEB/gestor/war-room` diretamente, sem passar pela home | `ok`; a página da aplicação carrega (sem 404 do servidor) |
| H-19 | Headers e CSP | `curl -sI $WEB/` | CSP com `connect-src 'self' $API`; `X-Frame-Options: DENY`; `nosniff`; HSTS; o console do navegador sem violações de CSP no login, no mapa e na sala de situação |
| H-20 | Integração real | Login com o admin real → painel admin → mapa público | Dados vindos da API (selo "API"); nenhum banner de dado demonstrativo onde a API responde |
| H-21 | Modo demonstrativo desligado | Inspecionar o bundle: `VITE_USE_API=true` | O frontend não usa `src/data` nas telas já integradas |

## E. Operação

| # | Verificação | Como | Esperado |
|---|---|---|---|
| H-22 | Backup e restauração | Backup de volume do `postgis-data`, mais `pg_dump`; restaurar num serviço temporário de staging | Restauração íntegra (contagem de tabelas e linhas); o serviço temporário é removido em seguida |
| H-23 | Rollback | *Redeploy* da versão anterior do `api` | Volta em menos de 5 min; `/ready` ok |
| H-24 | Alertas | Derrubar o `api` de staging (escalar a 0 ou forçar falha) | O alerta chega ao responsável |

## F. Go-live de produção

- [ ] A–E aprovados em staging, com evidências anexadas.
- [ ] Decisões D-1 (região/LGPD), D-3 (`/docs`) e D-4 (Vercel desconectada) registradas (RAILWAY-DEPLOYMENT §11).
- [ ] Segredos de produção gerados na hora, selados, sem reutilizar nada de staging.
- [ ] A–E repetidos em production (H-06, H-12 e H-16 podem ser substituídos pelas evidências de staging, por decisão do proprietário).
- [ ] O banner "PROTÓTIPO NÃO OPERACIONAL" continua visível enquanto a Fase 1 não terminar. Ele só sai quando houver dados reais de ingestão, por decisão explícita do proprietário.
