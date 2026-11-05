# IGNIS Orbital — sequência de merge e promoção para produção

Preparada em 05/11/2026. **Nada desta sequência foi executado.** Cada merge exige autorização explícita do proprietário.

Regras:
- Merge commit em todos os PRs (`--merge`). **Nunca** squash, rebase ou force-push.
- Não apagar branches durante a sequência.
- Não pular check vermelho.

Referência dos commits verificados em 05/11/2026: no web, os HEADs de `feat/ignis-admin-cockpit` e de `staging` são iguais. Na API, `feat/ignis-admin-cockpit` está à frente de `staging` apenas com commits de teste e documentação (`git diff --stat origin/staging origin/feat/ignis-admin-cockpit`), então o código em execução é o mesmo. O SHA final aparece no relatório de encerramento da missão; confira com `git ls-remote` antes de começar.

## 0. Pré-requisitos (antes do primeiro merge)

| # | Quem | Ação | Por quê | Como conferir |
|---|---|---|---|---|
| P1 | Proprietário | GitGuardian, no painel, depois de conferir a evidência ao lado, e reexecutar o check em cada PR: **33462092** (api #3) como *Test credential*; **39541748–39541751** (api #8) como *False positive*; **39592651** (api #9) e **39592652** (web #8) como *Test credential* | O check está vermelho nesses 4 PRs. Evidência de 05/11/2026; nenhum valor coincide com segredos do Railway ou de `.staging.env` (comparação sem expor valores). 33462092: senha demo já publicada, ainda em `README.md` e `seed/seed_users.py`, recusada por `app/core/passwords.py`; o seed é recusado em staging e produção. **Não é falso positivo.** 39541748–51: referências a variáveis e geradores de `/dev/urandom` em `deploy/local/`, sem literal. 39592651/2: ver ADMIN-SECURITY-REVIEW §11; ausentes em `HEAD`. Sem regra de proteção, o GitHub deixaria mergear mesmo vermelho: **isso seria ignorar verificação** | `gh pr checks <n>` sem `fail` |
| P2 | Proprietário | **Vercel:** desconectar o repositório `ignis-fire-watch` dos dois projetos (`ignis-fire-watch` e `ignis-fire-watch-main`) | O projeto Vercel publicava `master`. O merge único do §2 já traz o `vercel.json` que desliga os deploys (o web #4 sozinho ainda traz o antigo), mas só a desconexão elimina o risco. A conta Vercel conectada a esta sessão não enxerga esses projetos, então o vínculo **não foi confirmado** | Painel da Vercel; nenhum `vercel[bot]` novo em `repos/…/deployments` |
| P3 | Proprietário | **Web:** criar a tag `archive/lovable-main-2025` e trocar o branch padrão para `master` (`ignis-fire-watch/docs/IGNIS/BRANCH-STRATEGY.md`) | O padrão hoje é `main`, de histórico sem relação com `master`. `workflow_dispatch` só existe para workflows presentes no branch padrão: sem isso, o `promote.yml` do web não pode ser disparado | `gh api repos/eliasandraade/ignis-fire-watch --jq .default_branch` = `master` |
| P4 | Proprietário | GitHub, nos dois repositórios: environment `production` com *Required reviewers* = proprietário; rulesets em `production`, `staging` e no branch padrão (RAILWAY-DEPLOYMENT §6) | Hoje não há nenhuma regra. O environment não existe na API (seria criado sem proteção no 1º uso) e, no web, só existe o `Production` criado pela Vercel, sem regra; o nome não diferencia maiúsculas. Sem revisores, o `promote.yml` não pede aprovação | `gh api repos/…/environments` mostra `required_reviewers` |
| P5 | Proprietário | Selar `POSTGRES_PASSWORD` e `JWT_SECRET_KEY` nos dois ambientes | 0 variáveis seladas hoje | Railway → *Variables* |
| P6 | Proprietário | Decidir a ingestão em produção (D-6) | Sem ela, o mapa de produção abre vazio, com a fonte em "nunca executada": honesto, mas sem dados para validar | Ver §5 |
| P7 | Proprietário | **Autorização explícita de merge** | Exigida pela missão | — |
| P8 | Proprietário + execução | Autorizar e executar o teste de restauração (H-22) | Os backups existem e estão agendados, mas nenhuma restauração foi testada. Um `pg_dump` exige chave SSH própria do IGNIS; restaurar o volume de staging substitui o conteúdo dele | HOMOLOGATION-CHECKLIST H-22 |
| P9 | Proprietário | SonarCloud do web: criar o projeto ou decidir seguir sem ele | O PR web #8 não tem check de Quality Gate, e `eliasandraade_ignis-fire-watch` não é encontrado na API pública (o projeto pode ser privado). Na API, o Quality Gate do #9 está `OK` | Check `SonarCloud Code Analysis` no PR web #8 |

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

Só rode o `gh pr merge` com o `gh pr checks` sem `fail` (a mudança de base pode fazer o GitGuardian reavaliar a pilha inteira; os incidentes de P1 cobrem isso).

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

**Só depois de P2 e P3.**

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

## 8. Teste com data fixa (corrigido em 05/11/2026)

`test_admin_ingest_returns_the_real_runs_and_audits_the_requester` usava a janela de 26 h do relógio real, enquanto o servidor falso só conhece o arquivo INPE de 03/11/2026. A partir de 05/11/2026 00:00 UTC ele falha em **qualquer** commit. A produção se comporta corretamente: um dia passado sem arquivo é erro. A correção fixa a janela no teste e está só no topo da pilha da API: as CIs antigas dos PRs #7 e #8 ainda aparecem verdes, mas uma execução nova delas falharia.

A correção não mascara erro do worker. Conferido em 05/11/2026: o teste continua exigindo `ok` e as contagens das fixtures, passa com o relógio em 2030 e na véspera da fixture, e falha com `unavailable` se a janela apontar para um dia sem arquivo ou sem a correção.
