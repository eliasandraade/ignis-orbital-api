# IGNIS Orbital — sequência de merge e promoção para produção

Preparada em 05/11/2026. **Nada desta sequência foi executado.** Cada merge exige autorização explícita do proprietário.

Regras:
- Merge commit em todos os PRs (`--merge`). **Nunca** squash, rebase ou force-push.
- Não apagar branches durante a sequência.
- Não pular check vermelho.

Os commits promovidos são os **merge commits** gerados nos §§1 e 2 (`M_API` e `M_WEB`), que ainda não existem. A árvore de cada um deve ser idêntica à do topo da pilha (conferência nos §§1 e 2). Confira os HEADs com `git ls-remote` antes de começar.

Atualizado em 05/11/2026, depois da preparação final. Os rulesets já exigem PR, merge commit e checks verdes em `main` e `master`.

## 0. Pré-requisitos (antes do primeiro merge)

| # | Condição | Estado | Como conferir |
|---|---|---|---|
| P1 | GitGuardian classificado pelo proprietário | **Feito.** O check passa nos HEADs novos; PRs antigos só reavaliam em nova execução | `gh pr checks` nos PRs do topo da pilha |
| P2 | Vercel não publica a partir de `master` | **Decisão pendente.** O merge do web leva o `vercel.json` que desliga deploys por Git. A desconexão fica para quando o proprietário confirmar que a entrega acadêmica não precisa ficar no ar (`ignis-fire-watch/docs/IGNIS/BRANCH-STRATEGY.md`) | Painel da Vercel |
| P3 | `promote.yml` do web pode ser disparado | **Feito**, por tag `promote/*`, sem trocar o branch padrão. Gatilho e espera de aprovação testados em 05/11/2026 | §4 |
| P4 | Environment `production` e rulesets | **Feito** nos dois repositórios (RAILWAY-DEPLOYMENT §6) | `gh api repos/…/environments/production`, `gh api repos/…/rulesets` |
| P5 | Segredos selados | **Feito** nos dois ambientes. Valor conferido por hash dentro do container de staging depois do redeploy | Railway → *Variables* |
| P6 | Decidir a ingestão INPE em produção (D-6) | **Decisão pendente.** Sem ela, o mapa abre vazio. NASA FIRMS segue desligada na versão inicial | §5 |
| P7 | Autorização explícita de merge e promoção | **Pendente** | — |
| P8 | Teste de restauração (H-22) | **Feito** com `pg_dump` em banco descartável (RAILWAY-PROVISIONING-REPORT §14). A restauração nativa de volume do Railway **não** foi testada, pois substituiria o volume | HOMOLOGATION-CHECKLIST H-22 |
| P9 | SonarCloud do web | **Decisão pendente.** O projeto não existe na conta pública: criar ou seguir sem ele. Não é check obrigatório no ruleset do web | Sonar |
| P10 | Aviso de privacidade | **Decisão pendente.** Rascunho em [PRIVACY-NOTICE-DRAFT.md](PRIVACY-NOTICE-DRAFT.md); não publicado | §6 |
| P11 | Alertas no Railway | **Pendente (proprietário).** Ligar as notificações de deploy no painel. O monitor externo entra com o merge (`uptime.yml`) | §6 |

## 1. Merge da API (`ignis-orbital-api`, base `main`)

**Merge único do topo da pilha, com merge commit.** Por quê:
- Todos os commits da pilha entram em `main` com o histórico intacto.
- `main` nunca passa por um estado intermediário. Isso importa porque:
  - os PRs #7 e #8 contêm um teste com data fixa, corrigido só no topo da pilha, que falharia na CI de push (§8);
  - o mesmo vale para o web #4, sem o bloqueio da Vercel.
- A pilha é linear e sem conflito: `git merge-tree` de `main` × HEAD gera exatamente a árvore do HEAD.

O PR #2 (`feature/real-orbital-apis`) **não** faz parte da pilha: não mergear; decidir à parte.

```bash
R=eliasandraade/ignis-orbital-api
gh pr edit 9 --repo $R --base main
gh pr checks 9 --repo $R
gh pr merge 9 --repo $R --merge
```

Só rode o `gh pr merge` com o `gh pr checks` sem `fail`. A mudança de base pode fazer o GitGuardian reavaliar a pilha inteira; os incidentes de P1 cobrem isso. O ruleset `integracao` recusa o merge com check obrigatório vermelho.

Depois do merge:
- O #3 deve aparecer como *merged* automaticamente, pois seu head já está em `main`. Confira.
- Encerre os intermediários, **sem apagar branches**:

```bash
for n in 5 6 7 8; do gh pr close $n --repo $R --comment "Incluído em main pelo merge do #9 (merge commit, histórico preservado)."; done
```

Conferência (a árvore de `main` deve ser idêntica à do topo da pilha):

```bash
git fetch origin
test "$(git rev-parse origin/main^{tree})" = "$(git rev-parse origin/feat/ignis-admin-cockpit^{tree})" && echo idêntica
```

Em relação ao `staging` homologado, a diferença só pode ter testes e documentação. O `staging` avança no §3:

```bash
git diff --stat origin/staging origin/main
```

## 2. Merge do web (`ignis-fire-watch`, base `master`)

O branch padrão do web continua `main`; a base deste PR é `master`, e nada entra em `main`.

```bash
R=eliasandraade/ignis-fire-watch
gh pr edit 8 --repo $R --base master
gh pr checks 8 --repo $R
gh pr merge 8 --repo $R --merge
```

```bash
for n in 6 7; do gh pr close $n --repo $R --comment "Incluído em master pelo merge do #8 (merge commit, histórico preservado)."; done
```

O #4 deve aparecer como *merged* automaticamente. Mesma conferência, com `origin/master^{tree}`.

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
4. Só então promover o web. Depois de conferir a CI de push em `M_WEB`, use uma tag, pois `main` é o branch padrão do web e o GitHub não oferece `workflow_dispatch` para workflows fora dele:
   ```bash
   git tag promote/AAAAMMDD-HHMM "$M_WEB"
   ```
   ```bash
   git push origin promote/AAAAMMDD-HHMM
   ```
5. Aprovar e acompanhar.
6. Ligar o monitor de produção:
   ```bash
   gh variable set UPTIME_PRODUCTION --repo eliasandraade/ignis-orbital-api --body true
   ```

O ruleset de `production` exige os checks da CI no SHA promovido e recusa force-push e exclusão. **Ele não impede push direto do proprietário:** o GitHub não aceita o app *GitHub Actions* como exceção de ruleset em repositório pessoal, e restringir atualizações bloquearia o próprio `promote.yml`. O limite é a regra deste runbook: nada de `git push` manual em `production`.

**Ainda não testado (H-15), pois exigiria publicar:** o push real em `production`. O gatilho e a espera de aprovação foram testados no web em 05/11/2026 (tag em commit fora de `master`, execução cancelada e tag apagada, sem nenhuma etapa executada). O push feito pelo `GITHUB_TOKEN` não dispara nova CI, e o Railway deve aproveitar as *check suites* do mesmo SHA. Se o deploy não aparecer ou ficar parado em `WAITING`, **não** faça push manual em `production`. Dispare o mesmo SHA pelo painel do Railway (*Deploy*), depois de confirmar a CI verde.

## 5. Ingestão em produção (decisão D-6, opcional)

A ingestão usa só dados públicos do INPE e não coleta dados pessoais. A NASA FIRMS fica desligada na versão inicial, sem chave configurada, até haver homologação. Se o INPE for autorizado, em um PR próprio:

1. Mudar `INGEST.production` em `.railway/railway.ts` e ajustar a checagem correspondente em `contract.check.ts`.
2. `service: true`, `cron: false` no primeiro momento.
3. Gerar um `JWT_SECRET_KEY` próprio para `ignis-ingest` por stdin e selar.
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
| Vazamento de segredo | Gerar novo valor por stdin, selar e redeployar. Valores selados não podem ser lidos nem deselados |

Nunca: force-push, `alembic downgrade` sem backup, ou abrir denúncias (`PUBLIC_REPORTS_ENABLED`) antes da decisão LGPD (D-1).

## 8. Teste com data fixa (corrigido em 05/11/2026)

`test_admin_ingest_returns_the_real_runs_and_audits_the_requester` usava a janela de 26 h do relógio real, enquanto o servidor falso só conhece o arquivo INPE de 03/11/2026. A partir de 05/11/2026 00:00 UTC ele falha em **qualquer** commit. A produção se comporta corretamente: um dia passado sem arquivo é erro. A correção fixa a janela no teste e está só no topo da pilha da API: as CIs antigas dos PRs #7 e #8 ainda aparecem verdes, mas uma execução nova delas falharia.

A correção não mascara erro do worker. Conferido em 05/11/2026: o teste continua exigindo `ok` e as contagens das fixtures, passa com o relógio em 2030 e na véspera da fixture, e falha com `unavailable` se a janela apontar para um dia sem arquivo ou sem a correção.
