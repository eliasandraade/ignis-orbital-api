# IGNIS Core — Recuperação da API no Railway (checklist)

Data: 03/11/2026 (Sprint 0.1).
> Este documento é um **procedimento**: nada aqui foi executado em produção. Os passos que criam serviço, alteram variável, fazem deploy ou mexem em dados exigem a **autorização do proprietário**.

## 1. Diagnóstico (somente leitura)

| Verificação | Resultado |
|---|---|
| `curl https://ignis-api-production.up.railway.app/health` | `404 {"message":"Application not found"}`: resposta do roteador do Railway quando nenhum serviço está ligado ao domínio |
| `railway whoami` | conta `oeliasandraade@gmail.com` autenticada |
| `railway list` | 8 projetos (orken-hub, orken-platform, orkengov, precatorios-general-sampaio, lumen+, repbrasil, nexoerp, rst-transparente). **Nenhum projeto ou serviço IGNIS** |
| Repositório | Sem `railway.json`/`railway.toml`. O deploy usava o `Dockerfile` e `scripts/entrypoint.sh` |
| Deploys no GitHub (`/deployments`) | Nenhum deploy registrado para `ignis-orbital-api` |

**Conclusão:**
- o serviço da API foi removido, ou está em outra conta ou time do Railway que não está visível para esta conta;
- não há o que "religar": a recuperação é um **novo provisionamento**;
- os dados do banco antigo, se existiam, não estão acessíveis.

**Decisão do proprietário:** confirmar se existe outra conta ou time com o projeto antigo, para recuperar o banco, ou provisionar do zero.

## 2. Pré-requisitos

- [ ] PR #3 mergeado em `main`, com a CI verde.
- [ ] Decisão de ambiente: só `production`, ou `staging` + `production` (recomendado, no padrão do OrkenGov).
- [ ] **PostgreSQL com PostGIS.** A migration `a001` executa `CREATE EXTENSION postgis`; um Postgres sem PostGIS falha no boot. Usar o template PostGIS do Railway ou a imagem `postgis/postgis:16-3.4`.
- [ ] Região e LGPD: dados de denúncias têm dados pessoais. Registrar a região escolhida.

## 3. Variáveis de ambiente

| Variável | Obrigatória | Valor / regra | Comportamento se ausente ou inválida |
|---|---|---|---|
| `APP_ENV` | **sim** | `production` (ou `staging`) | Container **não inicia** (entrypoint). Valor fora da lista → erro de validação |
| `DATABASE_URL` | **sim** | `postgresql+asyncpg://…` (o Railway fornece `postgresql://`; trocar o esquema) | Em ambiente operacional, o padrão de desenvolvimento é recusado no boot |
| `JWT_SECRET_KEY` | **sim** | ≥ 32 caracteres aleatórios (`python -c "import secrets;print(secrets.token_hex(32))"`), gravado via stdin/painel e nunca em linha de comando ou chat | Boot recusado |
| `CORS_ORIGINS` | sim | domínio(s) de produção do frontend (vírgula ou JSON) | Default inclui `localhost`: **não usar em produção** |
| `TRUST_PROXY_HEADERS` | sim | `true` (atrás do proxy do Railway) | Rate limit agrupa todos os clientes no IP do proxy |
| `RATE_LIMIT_ENABLED` | não | `true` | — |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | não | 5–1440 (padrão 480) | Fora da faixa → boot recusado |
| `NASA_FIRMS_MAP_KEY` | não | chave do proprietário | Sem chave: alertas orbitais `disabled_missing_api_key` (lista vazia) |
| `ORBITAL_ALERTS_DEMO_MODE` | não | `false` (**nunca** `true` em produção) | — |
| `PORT` | fornecida pelo Railway | — | entrypoint usa `${PORT:-8000}` |
| `SEED_DEMO_DATA` | **não usar** | removida | É ignorada; o seed nunca roda em staging/production |

## 4. Provisionamento (com autorização)

1. Criar o projeto `ignis` com:
   - o serviço `api` (repositório `ignis-orbital-api`, branch `main`, builder Dockerfile);
   - um serviço Postgres com PostGIS.
2. Configurar as variáveis do §3. Segredos só pelo painel ou por `railway variables set … --stdin`.
3. Healthcheck do serviço `api`:
   - path `/ready` (verifica o banco; responde 503 sem detalhes se cair);
   - timeout de 120 s, porque o primeiro boot aplica migrations.
4. Deploy. O entrypoint:
   1. aguarda o banco;
   2. roda `alembic upgrade head`;
   3. executa `python -m seed --if-allowed`, que **ignora** o seed em produção e registra no log "Seed demonstrativo ignorado";
   4. sobe o uvicorn com 2 workers e `--proxy-headers`.
5. Gerar o domínio público e atualizar `CORS_ORIGINS`.
6. **Criar o primeiro administrador real.** O banco novo não tem nenhum usuário, porque o seed é proibido em produção. Criar dentro do serviço (`railway ssh`), com a senha digitada no prompt, nunca na linha de comando:
   ```bash
   python -m seed.bootstrap_admin --email <e-mail-institucional> --name "<Nome>"
   ```
   A política de senha é a mesma da API: 12 a 72 bytes, sem senhas publicadas. O comando recusa e-mail duplicado e recusa um segundo bootstrap quando já há admin legítimo. A criação é auditada (`user.bootstrap_admin_created`).

## 5. Verificação pós-deploy (smoke)

```bash
API=https://<novo-dominio>
curl -sf $API/health                                  # {"status":"ok",...,"environment":"production"}
curl -sf $API/ready                                   # {"status":"ready","database":"connected"}
curl -s  $API/api/v1/orbital-alerts | jq .source_status   # "disabled_missing_api_key" (ou live/cached com chave)
curl -s -o /dev/null -w '%{http_code}\n' -X POST $API/api/v1/orbital-alerts/ingest   # 401
```

- [ ] Log do deploy contém `Seed demonstrativo ignorado` e **não** contém `Seeding users`.
- [ ] `/docs` acessível só se essa for a decisão do proprietário (SECURITY-REVIEW R-09).

## 6. Usuários demonstrativos

Em banco **novo**, o seed não roda em produção, então não haverá contas demo.
Em banco **reaproveitado ou restaurado** de uma versão antiga (que rodava o seed em todo boot), siga os passos abaixo:

1. Verificação, somente leitura:
   ```bash
   python -m seed.demo_users check     # exit 2 = contas ativas com e-mail demo ou senha publicada
   ```
   Executar dentro do serviço (`railway ssh` ou um comando one-off no próprio serviço), porque o banco fica em rede privada.
2. **Antes de desativar, garantir um administrador real ativo.** Se o banco só tem o admin do seed, criar o admin real com `python -m seed.bootstrap_admin` (§4, passo 6). Sem isso, o `deactivate` **recusa a operação** (exit 3), para não trancar o sistema: a API de usuários exige um admin ativo e tokens de contas desativadas deixam de valer na hora.
3. **Com autorização do proprietário**, desativar:
   ```bash
   python -m seed.demo_users deactivate --confirm-host <host-do-DATABASE_URL>
   ```
   Efeito por conta:
   - `is_active=false`;
   - hash trocado por um segredo aleatório;
   - auditoria `user.demo_credentials_revoked`;
   - nenhuma exclusão.
4. Rodar `check` de novo e esperar exit 0.
5. Criar as demais contas reais pelo `POST /api/v1/admin/users`, autenticado com o admin real, que recusa senhas publicadas e senhas com menos de 12 caracteres.

O procedimento foi testado na CI e num PostGIS isolado (SPRINT-0-DELIVERY §3).

## 7. Rollback

| Situação | Ação |
|---|---|
| Deploy novo falha no healthcheck | O Railway mantém o deploy anterior ativo. Corrigir a variável ou o código e redeployar |
| Regressão após o deploy | Railway → Deployments → *Redeploy* da versão anterior |
| Migration problemática | **Antes** de cada deploy com migration, fazer backup (`pg_dump`, ou backup gerenciado do Railway). As migrations atuais são aditivas e têm `downgrade` testado na CI. Mesmo assim, **não** executar `alembic downgrade` em produção sem backup e sem autorização |
| Vazamento de segredo | Rotacionar `JWT_SECRET_KEY` (invalida todas as sessões) e a chave NASA |

## 8. Frontend (Vercel)

- [ ] Projeto de produção com `VITE_USE_API=true` e `VITE_API_URL=https://<novo-dominio>`.
- [ ] Confirmar a *Production Branch* de cada projeto Vercel. Ver a estratégia de branches em `ignis-fire-watch/docs/IGNIS/BRANCH-STRATEGY.md`.
- [ ] O redeploy do frontend só deve ocorrer depois de o smoke da API passar.

## 9. Backups e operação contínua

- [ ] Backup diário do Postgres (backup gerenciado do Railway, ou `backup-worker` no molde do OrkenGov: `pg_dump` cifrado → S3 `sa-east-1`).
- [ ] Alerta de healthcheck (Railway ou monitor externo).
- [ ] Revisão trimestral: `python -m seed.demo_users check` (exit 0 esperado).
