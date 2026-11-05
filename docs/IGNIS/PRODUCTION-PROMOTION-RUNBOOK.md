# IGNIS Orbital — sequência de merge e promoção para produção

Preparada em 05/11/2026. **Nada desta sequência foi executado.** Cada merge exige autorização explícita do proprietário.

Regras:
- Merge commit em todos os PRs (`--merge`). **Nunca** squash, rebase ou force-push.
- Não apagar branches durante a sequência.
- Não pular check vermelho.

Referência dos commits verificados em 05/11/2026: os HEADs de `feat/ignis-admin-cockpit` e de `staging` são iguais em cada repositório. O SHA final aparece no relatório de encerramento da missão; confira com `git ls-remote` antes de começar.

## 0. Pré-requisitos (antes do primeiro merge)

| # | Quem | Ação | Por quê | Como conferir |
|---|---|---|---|---|
| P1 | Proprietário | GitGuardian: classificar como *Test credential* / *False positive* os incidentes 33462092 (api #3), 39541748–39541751 (api #8), 39592651 (api #9), 39592652 (web #8), e reexecutar o check em cada PR | O check está vermelho nesses 4 PRs; a evidência dos dois últimos está em ADMIN-SECURITY-REVIEW §11. Sem regra de proteção, o GitHub deixaria mergear mesmo vermelho: **isso seria ignorar verificação** | `gh pr checks <n>` sem `fail` |
| P2 | Proprietário | **Vercel:** desconectar o repositório `ignis-fire-watch` dos dois projetos (`ignis-fire-watch` e `ignis-fire-watch-main`) | Crítico: o `vercel.json` que desliga os deploys só entra com o web **#6**. O web **#4** ainda traz o antigo, e o projeto Vercel publicava `master`. Sem isso, o merge do #4 pode publicar um site na Vercel. A conta Vercel conectada a esta sessão não enxerga esses projetos, então o vínculo **não foi confirmado** | Painel da Vercel; nenhum `vercel[bot]` novo em `repos/…/deployments` |
| P3 | Proprietário | **Web:** criar a tag `archive/lovable-main-2025` e trocar o branch padrão para `master` (`ignis-fire-watch/docs/IGNIS/BRANCH-STRATEGY.md`) | O padrão hoje é `main`, de histórico sem relação com `master`. `workflow_dispatch` só existe para workflows presentes no branch padrão: sem isso, o `promote.yml` do web não pode ser disparado | `gh api repos/eliasandraade/ignis-fire-watch --jq .default_branch` = `master` |
| P4 | Proprietário | GitHub, nos dois repositórios: environment `production` com *Required reviewers* = proprietário; rulesets em `production`, `staging` e no branch padrão (RAILWAY-DEPLOYMENT §6) | Hoje não há nenhuma regra. O environment não existe na API (seria criado sem proteção no 1º uso) e, no web, só existe o `Production` criado pela Vercel, sem regra; o nome não diferencia maiúsculas. Sem revisores, o `promote.yml` não pede aprovação | `gh api repos/…/environments` mostra `required_reviewers` |
| P5 | Proprietário | Selar `POSTGRES_PASSWORD` e `JWT_SECRET_KEY` nos dois ambientes | 0 variáveis seladas hoje | Railway → *Variables* |
| P6 | Proprietário | Decidir a ingestão em produção (D-6) | Sem ela, o mapa de produção abre vazio, com a fonte em "nunca executada": honesto, mas sem dados para validar | Ver §5 |
| P7 | Proprietário | **Autorização explícita de merge** | Exigida pela missão | — |

## 1. Merge da API (`ignis-orbital-api`, base `main`)

A pilha é linear e sem conflito (`git merge-tree` de `main` × HEAD gera exatamente a árvore do HEAD). O PR #2 (`feature/real-orbital-apis`) **não** faz parte da pilha: não mergear; decidir à parte.

Um comando de merge por vez, de baixo para cima, redirecionando a base do PR seguinte:

```bash
R=eliasandraade/ignis-orbital-api
gh pr merge 3 --repo $R --merge
gh pr edit 5 --repo $R --base main && gh pr merge 5 --repo $R --merge
gh pr edit 6 --repo $R --base main && gh pr merge 6 --repo $R --merge
gh pr edit 7 --repo $R --base main && gh pr merge 7 --repo $R --merge
gh pr edit 8 --repo $R --base main && gh pr merge 8 --repo $R --merge
gh pr edit 9 --repo $R --base main && gh pr merge 9 --repo $R --merge
```

Conferência (a árvore de `main` deve ser idêntica à do branch homologado):

```bash
git fetch origin
test "$(git rev-parse origin/main^{tree})" = "$(git rev-parse origin/staging^{tree})" && echo idêntica
```

## 2. Merge do web (`ignis-fire-watch`, base `master`)

**Só depois de P2 e P3.**

```bash
R=eliasandraade/ignis-fire-watch
gh pr merge 4 --repo $R --merge
gh pr edit 6 --repo $R --base master && gh pr merge 6 --repo $R --merge
gh pr edit 7 --repo $R --base master && gh pr merge 7 --repo $R --merge
gh pr edit 8 --repo $R --base master && gh pr merge 8 --repo $R --merge
```

Mesma conferência, com `origin/master^{tree}`.

## 3. CI e staging com os commits finais

Chame de `M_API` e `M_WEB` os HEADs de `main` e `master`.

1. Esperar a CI de **push** ficar verde nos dois (o `promote.yml` exige CI de push no SHA exato).
2. Fixar a integração da CI nos branches finais (o E2E hoje clona o outro repositório em `feat/ignis-admin-cockpit`):
   ```bash
   gh variable set IGNIS_WEB_REF --repo eliasandraade/ignis-orbital-api --body master
   gh variable set IGNIS_API_REF --repo eliasandraade/ignis-fire-watch --body main
   ```
3. Avançar o `staging` por fast-forward nos dois repositórios (sem `--force`):
   ```bash
   git push origin $M_API:refs/heads/staging
   ```
   ```bash
   git push origin $M_WEB:refs/heads/staging
   ```
4. Esperar o Railway e repetir o smoke de RAILWAY-DEPLOYMENT §8 em staging. A árvore é a mesma já homologada; o Railway pode marcar `SKIPPED` na API por `watchPatterns`, o que é normal.

## 4. Promoção (API antes do web)

Se P6 = ligar a ingestão, faça o §5 antes deste passo.

```bash
gh workflow run promote.yml --repo eliasandraade/ignis-orbital-api -f sha=$M_API
```

1. Aprovar no environment `production`.
2. Acompanhar o deploy, que roda migração até `a015` e importa a malha IBGE no pre-deploy:
   ```bash
   railway deployment list --service ignis-api --environment production
   ```
3. Confirmar no log: "inseridas 185", "Seed demonstrativo ignorado", `/ready` 200.
4. Só então promover o web:
   ```bash
   gh workflow run promote.yml --repo eliasandraade/ignis-fire-watch -f sha=$M_WEB
   ```
5. Aprovar e acompanhar.

**Ponto ainda não testado (H-15):** o push feito pelo `GITHUB_TOKEN` não dispara nova CI, e o Railway deve aproveitar as *check suites* do mesmo SHA. Se o deploy não aparecer ou ficar parado em `WAITING`, **não** faça push manual em `production`. Dispare o mesmo SHA pelo painel do Railway (*Deploy*), depois de confirmar a CI verde.

## 5. Ingestão em produção (decisão D-6, opcional)

A ingestão usa só dados públicos do INPE e não coleta dados pessoais. Se autorizada, em um PR próprio:

1. Mudar `INGEST.production` em `.railway/railway.ts` e ajustar a checagem correspondente em `contract.check.ts`.
2. `service: true`, `cron: false` no primeiro momento.
3. Gerar um `JWT_SECRET_KEY` próprio para `ignis-ingest` por stdin.
4. Aplicar, validar uma rodada manual e só então ligar `cron: true`.

## 6. Primeiro administrador e verificação final

1. Proprietário: RAILWAY-PROVISIONING-REPORT §12 (chave SSH própria, senha digitada no prompt, e-mail institucional real).
2. Smoke anônimo no domínio:
   ```bash
   WEB=https://ignis.andradesystems.com.br
   ```
   Depois, RAILWAY-DEPLOYMENT §8 inteiro, mais: `/public/map` abre com a malha; `POST /api/v1/reports` → 503; `/api/v1/reports/intake` → `accepting:false`.
3. Proprietário, com a própria conta: login → `/admin` → fontes, execuções, auditoria (`user.bootstrap_admin_created`) → mapa → logout.
4. **Não** rodar `e2e/admin.spec.ts` em produção: ele cria contas. `e2e/ignis.spec.ts` também exige contas `gestor`/`campo`, que não existem nem devem ser criadas para isso.

## 7. Se algo falhar

| Situação | Ação |
|---|---|
| Migração ou healthcheck falha na API | O deploy não entra no ar. Domínio segue em 404. Investigar o log; o banco está vazio, sem risco de dados |
| Regressão no web ou na API | Railway → *Deployments* → *Rollback* para o deploy anterior (8 s no teste em staging). **Não** retroceder branches |
| Primeiro deploy do web com problema (sem versão anterior) | Remover o deploy no Railway: o domínio volta a responder 404 |
| Vazamento de segredo | Gerar novo valor por stdin, selar e redeployar |

Nunca: force-push, `alembic downgrade` sem backup, ou abrir denúncias (`PUBLIC_REPORTS_ENABLED`) antes da decisão LGPD (D-1).
