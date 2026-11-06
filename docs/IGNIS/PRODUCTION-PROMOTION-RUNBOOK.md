# IGNIS Orbital — sequência de merge e promoção para produção

Preparada em 05/11/2026. **Nada desta sequência foi executado.** Cada merge exige autorização explícita do proprietário.

Regras:
- Merge commit em todos os PRs (`--merge`). **Nunca** squash, rebase ou force-push.
- Não apagar branches durante a sequência.
- Não pular check vermelho.

Os commits promovidos são os **merge commits** gerados nos §§1 e 2 (`M_API` e `M_WEB`), que ainda não existem. A árvore de cada um deve ser idêntica à do topo da pilha (conferência nos §§1 e 2). Confira os HEADs com `git ls-remote` antes de começar.

Atualizado em 06/11/2026, com as decisões do proprietário sobre a versão inicial: validação e consulta ambiental com dados públicos do INPE; NASA FIRMS, denúncias e comunicação institucional desligadas. Os rulesets já exigem PR, merge commit e checks verdes em `main` e `master`.

## 0. Pré-requisitos (antes do primeiro merge)

| # | Condição | Estado | Como conferir |
|---|---|---|---|
| P1 | GitGuardian classificado | **Feito.** Verde nos HEADs de api #9, web #8 e dos PRs novos | `gh pr checks` |
| P2 | Vercel não publica a partir de `master` | **Feito no código.** O merge do web leva o `vercel.json` que desliga deploys por Git. Por decisão do proprietário, não desconectar sem comprovar que nada depende dela | Sem novo `vercel[bot]` em `repos/…/deployments` depois do merge |
| P3 | `promote.yml` do web pode ser disparado | **Feito**, por tag `promote/*`. Branch padrão mantido em `main` | §4 |
| P4 | Environment `production` e rulesets | **Feito** nos dois repositórios | `gh api repos/…/rulesets` |
| P5 | Segredos selados | **Feito** nos dois ambientes | Railway → *Variables* |
| P6 | Ingestão INPE aprovada | **Aprovada, cron desligado.** Configuração no PR api #10, aplicada só no §5 | §5 |
| P7 | Autorização de merge e promoção | **Pendente** | — |
| P8 | Restauração em banco descartável | **Feito** com `pg_dump`. Restauração nativa de volume não testada | HOMOLOGATION-CHECKLIST H-22 |
| P9 | SonarCloud do web | **Pendente: exige login do proprietário.** Não bloqueia os checks atuais | Passos abaixo |
| P10 | Aviso de privacidade | **Pendente: 7 campos jurídicos** (PRIVACY-DATA-MAP §6). PR web #9 pronto e travado | PR web #9 |
| P11 | Alertas do Railway | **Pendente: exige o painel.** A API do Railway recusou a regra por canal não documentado, e nenhuma regra foi criada. O `uptime.yml` entra com o merge | Passos abaixo |

**P9, SonarCloud do web:**
1. Entrar em sonarcloud.io com o GitHub e importar `ignis-fire-watch` na organização `eliasandraade`. A chave `eliasandraade_ignis-fire-watch` já está em `sonar-project.properties`.
2. Escolher um método, nunca os dois:
   - *Automatic Analysis*, como na API, sem cobertura;
   - análise pela CI, com cobertura: desligar a automática, gravar o segredo `SONAR_TOKEN` e a variável `SONAR_CI_ANALYSIS=true`. O job já existe no `ci.yml`.
3. Conferir a primeira análise. Só então acrescentar `SonarCloud Code Analysis` ao ruleset `integracao` do web.

**P11, alertas do Railway:**
1. Nas notificações do workspace, manter falha de build e queda de deploy em *Email & In-App*.
2. No projeto, em *Observability*, selecionar `production`, abrir o menu de um widget e usar *Add monitor* para CPU, memória e disco.

## Commits em 06/11/2026

Confira com `git ls-remote` antes de começar. Um commit novo em qualquer PR exige refazer esta conferência.

| PR | Destino final | Papel |
|---|---|---|
| [api #9](https://github.com/eliasandraade/ignis-orbital-api/pull/9) | `main` | Pilha da API |
| [web #8](https://github.com/eliasandraade/ignis-fire-watch/pull/8) | `master` | Pilha do web |
| [web #9](https://github.com/eliasandraade/ignis-fire-watch/pull/9) | `master`, depois do #8 | Aviso de privacidade |
| [api #10](https://github.com/eliasandraade/ignis-orbital-api/pull/10) | `main`, depois do primeiro deploy validado | Ingestão de produção com cron desligado |

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

Depois, o aviso de privacidade, com os campos preenchidos e aprovados no branch `feat/privacy-page`:

```bash
gh pr edit 9 --repo $R --base master
gh pr ready 9 --repo $R
gh pr checks 9 --repo $R
gh pr merge 9 --repo $R --merge
```

`M_WEB` é o merge commit deste PR. Se o proprietário decidir publicar antes da aprovação, a página fica oculta, e `M_WEB` é o merge do #8.

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

A ingestão entra só depois, no §5.

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

## 5. Ingestão INPE em produção

Aprovada pelo proprietário em 06/11/2026, com ativação condicionada. A ingestão usa só dados públicos do INPE. A NASA FIRMS fica desligada, sem chave, até haver homologação. **Faça depois do §6:** a API de produção precisa estar validada.

### Configurar, com o cron desligado

1. Fazer o merge do PR api #10:
   ```bash
   gh pr edit 10 --repo eliasandraade/ignis-orbital-api --base main
   gh pr ready 10 --repo eliasandraade/ignis-orbital-api
   gh pr checks 10 --repo eliasandraade/ignis-orbital-api
   gh pr merge 10 --repo eliasandraade/ignis-orbital-api --merge
   ```
2. Com `main` atualizado, aplicar em produção pelo PowerShell. O plano esperado é `1 to add, 2 to change, 0 to destroy`; se aparecer outra coisa, pare.
   ```powershell
   $env:_ = "$env:APPDATA\npm\node_modules\@railway\cli\bin\railway.exe"
   & $env:_ environment link production
   & $env:_ config plan
   & $env:_ config apply
   & $env:_ environment link staging
   ```
   O serviço criado tenta um deploy e recusa iniciar sem o segredo. É o esperado.
3. Gravar um segredo próprio, sem exibi-lo, e selar em Railway → `ignis-ingest` → *Variables* → *Seal*:
   ```bash
   python -c "import secrets;print(secrets.token_hex(32))" | railway variable set JWT_SECRET_KEY --stdin -s ignis-ingest -e production --skip-deploys
   ```

### Rodada manual

```bash
railway redeploy -s ignis-ingest -e production -y
```

```bash
railway logs -s ignis-ingest -e production --lines 40
```

Esperado no log: `round="finished" exit_code=0`, INPE `ok` e FIRMS `disabled`. Em `/api/v1/orbital-alerts/sources`: INPE `live`, FIRMS `disabled`.

### Confirmar que não há execução duplicada

1. Repetir a rodada manual. A segunda não pode inserir os mesmos focos de novo.
2. Dentro de `ignis-postgis` de produção, por SSH com a chave própria do proprietário. Os dois resultados devem ser zero:
   ```sql
   SELECT count(*) FROM (SELECT dedup_key FROM orbital_detections GROUP BY 1 HAVING count(*) > 1) d;
   SELECT count(*) FROM ingestion_runs a JOIN ingestion_runs b
     ON a.id < b.id AND a.source = b.source AND a.product = b.product
    AND a.started_at < coalesce(b.finished_at, now())
    AND b.started_at < coalesce(a.finished_at, now());
   ```
3. Conferir a configuração: uma réplica, nenhum cron em `ignis-ingest` e nenhuma rodada fora dos horários disparados.

Proteções já existentes:
- `dedup_key` único e lease por produto no banco (`test_concurrent_rounds_never_run_the_same_product_twice`);
- nenhum agendador dentro da API;
- rodada limitada a 13 minutos;
- [o Railway pula a execução](https://docs.railway.com/reference/cron-jobs) se a anterior ainda estiver rodando.

### Ligar o cron

Só com as três etapas acima aprovadas, em outro PR com autorização explícita:
1. `INGEST.production.cron = true` em `.railway/railway.ts`.
2. Trocar a verificação correspondente em `.railway/contract.check.ts`.
3. Merge, `config plan` e `config apply`.
4. Conferir duas rodadas seguidas, com intervalo próximo de 15 minutos, e repetir as consultas acima.
5. Ligar o monitor:
   ```bash
   gh variable set UPTIME_PRODUCTION_INGEST --repo eliasandraade/ignis-orbital-api --body true
   ```

## 6. Primeiro administrador e verificação final

1. Proprietário: RAILWAY-PROVISIONING-REPORT §12 (chave SSH própria, senha digitada no prompt, e-mail institucional real).
2. Smoke anônimo no domínio:
   ```bash
   WEB=https://ignis.andradesystems.com.br
   ```
   Depois, RAILWAY-DEPLOYMENT §8 inteiro, mais: `/public/map` abre com a malha; `POST /api/v1/reports` → 503; `/api/v1/reports/intake` → `accepting:false`.
3. Proprietário, com a própria conta: login → `/admin` → fontes, execuções, auditoria (`user.bootstrap_admin_created`) → mapa → logout.
4. Só depois disso, executar o §5.
5. **Não** rodar `e2e/admin.spec.ts` em produção: ele cria contas. `e2e/ignis.spec.ts` também exige contas `gestor`/`campo`, que não existem nem devem ser criadas para isso.

## 7. Se algo falhar

| Situação | Ação |
|---|---|
| Migração ou healthcheck falha na API | O deploy não entra no ar. Domínio segue em 404. Investigar o log; o banco está vazio, sem risco de dados |
| Regressão no web ou na API | Railway → *Deployments* → *Rollback* para o deploy anterior (8 s no teste em staging). **Não** retroceder branches |
| Primeiro deploy do web com problema (sem versão anterior) | Remover o deploy no Railway: o domínio volta a responder 404 |
| Vazamento de segredo | Gerar novo valor por stdin, selar e redeployar. Valores selados não podem ser lidos nem deselados |

Observação de staging em 06/11/2026: o nginx registra `connect() failed` para a API e tenta de novo; as respostas observadas foram 200. Em 500 linhas de log houve 2 respostas 5xx, não investigadas. Vale olhar depois do primeiro deploy.

Nunca: force-push, `alembic downgrade` sem backup, abrir denúncias (`PUBLIC_REPORTS_ENABLED`) antes da decisão LGPD (D-1), criar contas reais de órgãos públicos ou ativar comunicação institucional, despacho ou operação de emergência.

## 8. Teste com data fixa (corrigido em 05/11/2026)

`test_admin_ingest_returns_the_real_runs_and_audits_the_requester` usava a janela de 26 h do relógio real, enquanto o servidor falso só conhece o arquivo INPE de 03/11/2026. A partir de 05/11/2026 00:00 UTC ele falha em **qualquer** commit. A produção se comporta corretamente: um dia passado sem arquivo é erro. A correção fixa a janela no teste e está só no topo da pilha da API: as CIs antigas dos PRs #7 e #8 ainda aparecem verdes, mas uma execução nova delas falharia.

A correção não mascara erro do worker. Conferido em 05/11/2026: o teste continua exigindo `ok` e as contagens das fixtures, passa com o relógio em 2030 e na véspera da fixture, e falha com `unavailable` se a janela apontar para um dia sem arquivo ou sem a correção.
