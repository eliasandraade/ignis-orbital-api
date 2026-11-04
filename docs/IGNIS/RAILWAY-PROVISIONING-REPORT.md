# IGNIS Orbital — relatório de provisionamento no Railway

Data: 04/11/2026. Executado com a autorização da missão "Estabilização final + infraestrutura oficial Railway". Nenhum valor de segredo aparece neste documento.

**Classificação: STAGING READY — PRODUCTION BLOCKED.**
- O staging está implantado, homologado e acessível.
- A produção está provisionada e protegida, sem código implantado.
- Os bloqueios de produção (§14) dependem do proprietário.

## 1. Projeto

| Item | Valor |
|---|---|
| Workspace | `eliasandraade's Projects` (`dbc17581-214d-4dfa-87f1-838f49966f2f`), plano **Pro**. É o único workspace da conta: não existe workspace "Andrade Systems" separado |
| Projeto | **IGNIS Orbital**, criado nesta missão (não havia projeto IGNIS anterior) |
| ID do projeto | `801f5962-4b9a-48dc-a83a-5e8ecb383f81` |
| Infraestrutura como código | `.railway/railway.ts` (SDK `railway/iac` 3.16.0, CLI 5.70.0), com contrato verificado na CI (`npm run check`, 28 checagens) |

## 2. Ambientes

| Ambiente | ID | Origem do código | Estado |
|---|---|---|---|
| `staging` | `69081bd6-c712-4c88-a7fd-e3e15e958d63` | branch **`staging`** dos dois repositórios | implantado e homologado |
| `production` | `104876ec-848c-4d5c-a664-d21286a3601a` | branch **`production`**, que ainda **não existe** | infraestrutura criada; **nenhum deploy de aplicação** |

**Por que um branch `staging`** (mecanismo temporário explícito e rastreável):
- O código profissionalizado está nos PRs empilhados `ignis-orbital-api#9` / `ignis-fire-watch#8`, ainda sem merge.
- O merge em `main`/`master` não foi autorizado. Por isso, o branch `staging` foi criado no HEAD de `feat/ignis-admin-cockpit` e é avançado só por fast-forward (`git push origin feat/ignis-admin-cockpit:staging`, nunca `--force`).
- Depois do merge da pilha, o `staging` passa a seguir o branch padrão.
- O branch `production` não foi criado nem alterado: ele só pode nascer do `promote.yml`, a partir de um commit de `main` com CI verde.

## 3. Serviços

| Serviço | Exposição | Origem | Staging | Produção |
|---|---|---|---|---|
| `ignis-web` | **pública** (único serviço público) | `ignis-fire-watch` (Dockerfile; nginx sem root) | `https://ignis-web-staging.up.railway.app`, deploy `SUCCESS` | sem deploy (branch `production` inexistente); domínio oficial anexado |
| `ignis-api` | privada (sem domínio público, sem TCP proxy) | `ignis-orbital-api` (Dockerfile; usuário `ignis`) | `SUCCESS`, `/ready` 200 | sem deploy |
| `ignis-postgis` | privada (sem domínio, sem TCP proxy) | imagem `postgis/postgis:16-3.4` (PostgreSQL 16.4, PostGIS 3.4.3) | `SUCCESS` | `SUCCESS` (banco vazio, inicializado) |
| `ignis-ingest` | privada | mesma imagem da API, papel `ingest` | cron `*/15 * * * *`, ligado após as rodadas manuais | **não existe** em produção (sem cron) |

Configuração comum:
- **Uma réplica por serviço**, na região do §4.
- **A API roda com 1 worker** (`WEB_CONCURRENCY=1`): o rate limit em memória fica exato.
- **"Wait for CI"** (`checkSuites`) está ligado em `ignis-api`, `ignis-web` e `ignis-ingest`.
- **Migração no pre-deploy** da API, serializada por advisory lock.

**Comunicação same-origin:**
- `https://<web>/` serve o SPA.
- `/api/v1/*`, `/health` e `/ready` são encaminhados pelo nginx a `http://ignis-api.railway.internal:8000`, pela rede privada (o resolvedor DNS do contêiner é consultado por requisição).
- `/docs`, `/openapi.json` e qualquer outro caminho **não chegam à API**: retornam o SPA.
- API inacessível → `503` JSON `{"detail":"API temporariamente indisponível."}`, com os cabeçalhos de segurança.
- **Não existe um segundo domínio público para a API.**

## 4. Região

| | |
|---|---|
| Escolhida | **`us-east4-eqdc4a` (US East Metal, Virgínia)** para todos os serviços e volumes |
| Disponíveis | `us-west2` (Califórnia), `us-east4-eqdc4a` (Virgínia), `europe-west4-drams3a` (Amsterdã), `asia-southeast1-eqsg3a` (Singapura); **nenhuma na América do Sul** |
| Critérios | cabos submarinos diretos Fortaleza ↔ costa leste dos EUA; boa disponibilidade da região; o mesmo preço em todas as regiões |
| Risco LGPD | Os dados ficam nos EUA, o que é **transferência internacional** (LGPD art. 33). Nesta versão não há coleta de dados pessoais de cidadãos: o recebimento de denúncias está **fechado** em staging e produção (`PUBLIC_REPORTS_ENABLED=false`, §9). As contas de homologação usam `example.org`. Abrir denúncias em produção exige a análise LGPD e o registro da salvaguarda (decisão D-1 do proprietário) |

A latência do Ceará não foi medida de dentro da região. Foi medido o tempo de resposta do staging a partir desta estação, a máquina de desenvolvimento, sem localização confirmada: 0,48–0,58 s por requisição HTTPS, com conexão nova a cada vez.

**Incidente de região, corrigido:**
- O primeiro apply criou o volume de staging em `europe-west4`, porque o campo `deploy.region` do SDK não é aplicado. O IaC passou a usar `replicas: { "us-east4-eqdc4a": 1 }`.
- Ao migrar o volume com o Postgres em execução, o cluster copiado chegou **sem o banco `ignis`** (ainda não havia nenhum dado).
- Correção não destrutiva: `PGDATA` de staging aponta para `pgdata-2`, onde um cluster novo foi inicializado. O cluster antigo (`pgdata`) **foi mantido**, não apagado; ocupa espaço desprezível e pode ser removido pelo proprietário.
- Lição registrada: **nunca migrar a região de um volume com dados sem parar o banco e sem um backup lógico.**

## 5. Banco, volume e backup

| | Staging | Produção |
|---|---|---|
| Volume | `ignis-postgis-data` → instância `ff49f7f5-…` (`vol_0yovs0b9su4ibh2e`), 5 GB, `us-east4` | instância `96c7b0d8-…` (`vol_44gw5xn9a16v3apt`), 10 GB, `us-east4` |
| Credenciais | `POSTGRES_PASSWORD` aleatório (256 bits), só de staging | aleatório, distinto do de staging |
| `DATABASE_URL` | referência interna `ignis-postgis.railway.internal:5432` | idem, no próprio ambiente |
| Backups de volume (Railway) | diário (retenção de 6 dias), semanal (27 dias), mensal (89 dias) | idem |

Isolamento:
- Volume, senha e URL de conexão são **próprios de cada ambiente**.
- Os serviços têm instância própria em cada ambiente, e cada ambiente tem sua própria rede privada.

**Restauração:**
- **Backup de volume:** Railway → serviço `ignis-postgis` → *Backups* → *Restore*, ou a mutação `volumeInstanceBackupRestore`. A restauração substitui o conteúdo do volume. Antes de restaurar, crie um backup manual (`volumeInstanceBackupCreate`).
- **Backup lógico, recomendado antes de toda migração em produção:**
  1. Abra uma sessão com `railway ssh --service ignis-postgis --environment <amb>`.
  2. Dentro da sessão, rode `pg_dump -U ignis -d ignis -Fc > /var/lib/postgresql/data/dump-<data>.dump`.
  3. Copie o dump para fora do Railway.
- Os snapshots de volume são **consistentes como após uma queda** (*crash-consistent*). O teste de restauração (H-22) ainda **não foi executado**.

Monitoramento básico:
- healthchecks do Railway (`/ready` na API, `/healthz` no web);
- `exit_code≠0` da ingestão marca o deploy como falho;
- painel `/admin` com execuções e falhas.

Monitor externo e alertas por e-mail: ver §14.

## 6. Migrações e dados de referência

| Ambiente | Resultado |
|---|---|
| Staging | Pre-deploy: `alembic upgrade head` do zero até **`a015`** (`a014 → a015` incluída), seguido de `python -m seed.jurisdictions`: "184 municípios no arquivo; inseridas 185" (184 municípios + UF; dataset `b820e9ba-…`). Reexecuções nos deploys seguintes: sem alteração |
| Produção | **Nenhuma.** A API de produção não foi implantada. O banco está vazio e inicializado |

**Migração `a015`:**
- Plano SQL (`alembic upgrade a014:a015 --sql`): uma transação com 4 `ADD COLUMN` com default constante e `CREATE UNIQUE INDEX uq_users_email_lower`. Não reescreve dados.
- Duplicados de e-mail por caixa: zero no banco local de validação. Staging e produção nasceram vazios.
- *upgrade → downgrade → upgrade* testado num banco descartável.
- Duas migrações simultâneas serializam no advisory lock (`ignis:alembic-upgrade`).
- **Downgrade automático: nunca.**

Seed demonstrativo: bloqueado no código para `APP_ENV=staging|production`, e `SKIP_DEMO_SEED=true` no IaC. O log mostra "Seed demonstrativo ignorado".

## 7. Contas

| Ambiente | Contas | Como foram criadas |
|---|---|---|
| Staging | `admin.homologacao@example.org` (admin), `gestor.homologacao@example.org`, `campo.homologacao@example.org`, mais as contas `e2e.<ts>@example.org` criadas e **desativadas** pelo E2E | Ver o procedimento abaixo |
| Produção | **nenhuma** | Procedimento do §12 (proprietário) |

**Primeiro admin de staging**, sem acesso SSH:
1. Uma execução única no serviço privado `ignis-ingest`, com comando temporário `python -m seed.bootstrap_admin`. A senha aleatória foi passada por stdin, a partir de uma variável temporária.
2. A variável foi **apagada**, e o comando original foi restaurado pelo IaC.
3. A senha foi **trocada pela API** logo em seguida. A senha antiga agora recebe `401`.

Os papéis `gestor` e `campo` foram criados pelo próprio Admin Cockpit (API, auditado), com troca obrigatória no primeiro acesso, já feita.

As senhas atuais existem **só** em `deploy/local/.staging.env`, ignorado pelo Git, nesta estação.

## 8. Variáveis (nomes; nunca valores)

| Serviço | Variáveis |
|---|---|
| ignis-postgis | `POSTGRES_USER`, `POSTGRES_DB`, `POSTGRES_PASSWORD` (segredo), `PGDATA`, `DATABASE_URL` (referência) |
| ignis-api | `APP_ENV`, `PORT=8000`, `DATABASE_URL` (referência), `JWT_SECRET_KEY` (segredo), `CORS_ORIGINS`, `ORBITAL_ALERTS_DEMO_MODE=false`, `INPE_QUEIMADAS_ENABLED=true`, `MIGRATE_ON_START=false`, `SKIP_DEMO_SEED=true`, `PUBLIC_REPORTS_ENABLED=false`, `WEB_CONCURRENCY=1`, `TRUST_PROXY_HEADERS=true`, `CLIENT_IP_HEADER=x-real-ip`, `FORWARDED_ALLOW_IPS=*` |
| ignis-web | `VITE_API_URL=same-origin`, `IGNIS_API_UPSTREAM=http://${{ignis-api.RAILWAY_PRIVATE_DOMAIN}}:${{ignis-api.PORT}}` |
| ignis-ingest | `APP_ENV`, `DATABASE_URL`, `JWT_SECRET_KEY` (segredo próprio), `INPE_QUEIMADAS_ENABLED`, `CORS_ORIGINS`, `MIGRATE_ON_START`, `SKIP_DEMO_SEED` |

Como os segredos foram tratados:
- Gerados com `secrets.token_hex(32)`, por ambiente e por serviço, e gravados via `railway variable set --stdin`. **Nunca** apareceram em linha de comando, log, chat ou Git.
- **Não** reutilizam as senhas da pilha Docker local.
- A **selagem** (*Seal*) só existe no painel: fica como recomendação ao proprietário.

`CORS_ORIGINS`:
- staging: `https://${{ignis-web.RAILWAY_PUBLIC_DOMAIN}}`;
- produção: `https://ignis.andradesystems.com.br`.

Outras variáveis:
- `NASA_FIRMS_MAP_KEY` **não existe** em nenhum ambiente: a FIRMS fica `disabled` até a chave real ser homologada.
- `API_DOCS_PUBLIC` e `AURORA_EXPERIMENTAL` não estão definidas, e os dois recursos ficam desligados em ambientes operacionais.

## 9. Gates de produção implementados nesta missão

| Gate | Implementação | Evidência |
|---|---|---|
| Aurora experimental desativada | Rotas `/api/v1/aurora/*` não são montadas em staging/produção; `AURORA_EXPERIMENTAL=true` não as liga | Staging: `POST /api/v1/aurora/chat` → 404 (com e sem sessão); testes `test_aurora_is_not_mounted_in_operational_environments` |
| Denúncias reais bloqueadas | `PUBLIC_REPORTS_ENABLED` (falso por padrão em staging/produção). `POST /api/v1/reports` → 503, sem gravar nada; `GET /api/v1/reports/intake` informa o estado; o formulário só aparece com o recebimento confirmado (falha fechada) | Testes `test_operational_environments_do_not_accept_reports_by_default`; E2E "recebimento de denúncias fechado" |
| Despacho e comunicação institucional | Não existem no código: nenhum envio de SMS, e-mail, webhook ou acionamento externo. "Converter em incidente" é registro interno | Varredura de `app/` |
| Aviso de que foco de calor não confirma incêndio | Mapa e cartões de resumo ("anomalias térmicas … não confirmam incêndio"); página de denúncia fechada | E2E do mapa público |
| Docs públicas desligadas | `/docs`, `/redoc` e `/openapi.json` não montados; o proxy também não encaminha esses caminhos | Staging: `/docs` → SPA |
| Erros de configuração sem segredos | `hide_input_in_errors=True` no `Settings` (o 1º deploy de staging mostrou o dicionário de entrada truncado no log, sem segredo visível) | `test_configuration_errors_never_echo_secrets` |

## 10. Domínio oficial

| Etapa | Estado em 04/11/2026 |
|---|---|
| Configurado no Railway | **Sim.** `ignis.andradesystems.com.br` em `ignis-web`/production (`syncStatus ACTIVE`) |
| DNS | **Pendente.** Os servidores autoritativos são da GoDaddy (`ns05/ns06.domaincontrol.com`), sem acesso desta missão. Registros a criar abaixo |
| DNS propagado | Não (NXDOMAIN no autoritativo) |
| Verificação de propriedade | Não (`verified: false`) |
| SSL emitido | Não (`CERTIFICATE_STATUS_TYPE_VALIDATING_OWNERSHIP`) |
| Acessível com HTTPS | Não |
| Aplicação validada no domínio | Não (produção sem deploy) |

**Registros DNS a criar na zona `andradesystems.com.br`** (GoDaddy → DNS → *Add record*), exatamente como o Railway informou:

| Tipo | Host (nome) | Valor | TTL | Finalidade |
|---|---|---|---|---|
| `CNAME` | `ignis` | `bp2zkhvo.up.railway.app` | 600 (ou padrão) | Roteia `ignis.andradesystems.com.br` para o `ignis-web` de produção |
| `TXT` | `_railway-verify.ignis` | `railway-verify=354acfa06922a75dac1e52dfb1b25ede098f9c1a09be62b4931d21c9ee475c2e` | 600 (ou padrão) | Prova a posse do domínio para o Railway emitir o certificado |

**Conflitos:**
- Não há conflito: nenhum registro `ignis`, nenhum curinga `*` e nenhum `CAA` na zona; qualquer CA, incluindo a Let's Encrypt, pode emitir.
- **Não alterar** o apex, MX, SPF, DKIM, DMARC nem outros subdomínios.

**Verificação depois de criar os registros:**
1. Rode `railway domain status ignis.andradesystems.com.br --service ignis-web --environment production`. O esperado: `verified: true`, o certificado emitido e o CNAME `currentValue` igual ao `requiredValue`.
2. Depois do deploy de produção, rode `curl -sI https://ignis.andradesystems.com.br/healthz`.

O token de verificação é público por natureza, porque é publicado no DNS. Ele não é um segredo.

## 11. Homologação de staging (24 itens da missão)

| # | Item | Resultado |
|---|---|---|
| 1 | Build do frontend | OK (Dockerfile, `VITE_API_URL=same-origin`) |
| 2 | Build da API | OK |
| 3 | Inicialização PostGIS | OK (após a correção do §4) |
| 4 | Migrações | OK (`a015`) |
| 5 | Importação IBGE | OK: 184 municípios + UF; a API lista 184 |
| 6 | API `/ready` | 200 `{"status":"ready","database":"connected"}` |
| 7 | Frontend `/healthz` | 200 `ok` |
| 8 | Login administrativo | OK |
| 9 | Cockpit `/admin` | OK (métricas iguais à API; capturas em `evidence/railway-staging-2026-11-04/`) |
| 10 | Usuários de teste | OK (criação, troca obrigatória, papel, desativação, pelo E2E) |
| 11 | Permissões e auditoria | OK |
| 12 | OpenAPI administrativo | OK (somente admin; 401 sem sessão; nenhum token em URL) |
| 13 | Fontes e execuções | OK |
| 14 | Worker manual | OK (rodada única do `ignis-ingest`; depois, `POST /ingest` auditado → 202) |
| 15 | Ingestão INPE real | OK: 560 focos lidos, 320 do Ceará gravados, 240 fora do recorte, 0 rejeitados; reexecução: 0 novos (ETag/304); FIRMS `disabled` (`missing_api_key`) |
| 16 | Mapa do Ceará | OK (E2E do mapa público; malha comprimida: 1.026 KB → 338 KB) |
| 17 | Filtros geoespaciais | OK (E2E: filtro por município e período) |
| 18 | Portal público só com dados permitidos | OK (focos, municípios e fontes; denúncias fechadas) |
| 19 | Sem referência acadêmica | OK (varredura do bundle na CI + E2E) |
| 20 | Sem fallback fictício | OK (E2E) |
| 21 | Sem credenciais nos logs | OK: logs dos 4 serviços sem URL de banco, `password=`, Bearer, `access_token` nem as senhas de homologação |
| 22 | E2E | **29/29** contra o staging (ver ADMIN-VALIDATION-GUIDE §5) |
| 23 | URLs e comunicação entre serviços | OK (same-origin; CORS: origem do web → 200, origem estranha → 400; `/ingest` sem token → 401) |
| 24 | Recuperação após reinício | OK: reinício do PostGIS (pronto em 2 s) e da API (sem amostra fora do ar); 320 focos e 184 municípios preservados |
| — | Fonte indisponível | OK: com o INPE inalcançável, a execução fica `unavailable`/`connection_error`, exit 2 (deploy marcado como falho); o portal mostra "a fonte está indisponível" e mantém o último sucesso real; a rodada seguinte normaliza |
| — | Rate limit atrás do Railway | OK: a 11ª tentativa de login → 429, mesmo com `X-Real-IP`/`X-Forwarded-For` forjados (a borda sobrescreve) |
| — | Rollback | OK (§13) |

## 12. Primeiro administrador de produção (procedimento do proprietário)

Só depois do primeiro deploy de produção (§14, B1):

1. Registre uma chave SSH própria do IGNIS na conta Railway:
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/ignis-railway
   ```
   ```bash
   railway ssh keys add
   ```
2. Abra uma sessão no serviço da API de produção:
   ```bash
   railway ssh -i ~/.ssh/ignis-railway --service ignis-api --environment production
   ```
3. Dentro da sessão, crie o administrador com um **e-mail institucional real**:
   ```bash
   python -m seed.bootstrap_admin --email <e-mail> --name "<Nome>"
   ```
   A senha é digitada no prompt, duas vezes. Ela nunca vai para argumento, variável ou log, e a criação é auditada (`user.bootstrap_admin_created`).
4. Ainda na sessão, confirme que não há contas de risco:
   ```bash
   python -m seed.demo_users check
   ```
   O esperado é exit 0.

Não use o mecanismo de variável temporária do §7 em produção.

## 13. Rollback

| Situação | Procedimento | Verificado |
|---|---|---|
| Deploy reprovado no healthcheck ou no pre-deploy | Automático: a versão anterior continua no ar | Sim: o 1º deploy da API falhou no pre-deploy (banco indisponível) e não substituiu nada |
| CI vermelha | O Railway descarta o deploy (*Wait for CI*) | Sim: deploys `SKIPPED`/`WAITING` observados |
| Regressão | Railway → serviço → *Deployments* → deploy anterior → *Rollback*. Ou a mutação `deploymentRollback(id)` | Sim: `ignis-web` de volta ao deploy anterior em 8 s e de volta à versão atual em 8 s, com `/healthz` e `/ready` OK |
| Migração | Backup lógico antes; `alembic downgrade` só com backup e autorização | `a015` com downgrade testado num banco descartável |
| Domínio | Remover o CNAME devolve o domínio ao estado anterior; o staging não é afetado | — |

## 14. Bloqueios pendentes (dependem do proprietário)

| # | Bloqueio | Ação necessária |
|---|---|---|
| B1 | **Código fora dos branches de implantação.** A produção só implanta do branch `production`, que o `promote.yml` cria a partir de um commit de `main`/`master` com CI verde. A pilha de PRs (api #3→#5→#6→#7→#8→#9; web #4→#6→#7→#8) não está mergeada | Aprovar e mergear a pilha; depois rodar `promote.yml` nos dois repositórios |
| B2 | **DNS** na GoDaddy | Criar os 2 registros do §10 |
| B3 | **GitGuardian**: incidentes `39592651` (api) e `39592652` (web) mantêm o check vermelho nos PRs | Classificar no painel como *test credential / false positive* (evidência em ADMIN-SECURITY-REVIEW §11); os anteriores 33462092 e 39541748–39541751 seguem pendentes |
| B4 | **Primeiro admin de produção** | §12 (exige SSH com chave própria; esta missão não registrou chave na conta) |
| B5 | **D-1 LGPD** | Não bloqueia o portal somente leitura; bloqueia abrir as denúncias (`PUBLIC_REPORTS_ENABLED`) |
| B6 | Governança no GitHub | Environment `production` com revisores e rulesets em `production`/`main`/`master`/`staging` (RAILWAY-DEPLOYMENT §6) |
| B7 | Selar variáveis | Railway → *Variables* → *Seal* em `POSTGRES_PASSWORD` e `JWT_SECRET_KEY` (os dois ambientes) |
| B8 | Alertas | Configurar notificações de deploy/healthcheck no Railway e um monitor externo de `/healthz` |

Quando B1, B2, B3 e B4 estiverem resolvidos:
1. Rodar o `promote.yml`.
2. Acompanhar o deploy de produção.
3. Executar §12 e o HOMOLOGATION-CHECKLIST em produção.
4. Verificar o HTTPS no domínio oficial.

## 15. Custos (estimativa, sem compromisso)

Premissas:
- Preços Pro vigentes:
  - US$ 20/mês, com US$ 20 de uso incluído **por workspace**, compartilhado com os outros 8 projetos da conta;
  - US$ 10/GB-mês de RAM;
  - US$ 20/vCPU-mês;
  - US$ 0,15/GB-mês de volume;
  - US$ 0,05/GB de egress.
- Consumo medido em staging (30 min, com tráfego de teste):
  - API: 104 MB e < 0,01 vCPU;
  - PostGIS: 62 MB e < 0,01 vCPU; volume com 339 MB usados;
  - web: 41 MB;
  - ingestão: 95 MB e 0,14 vCPU só durante as rodadas (cerca de 30 s a cada 15 min).
- O custo dos backups de volume não está documentado pelo Railway (estimado como armazenamento).

| | RAM | CPU | Volume e backups | Egress | **Total estimado** |
|---|---|---|---|---|---|
| Staging (24 h/dia) | ≈ 0,25 GB → US$ 2,50 | ≈ 0,02 vCPU → US$ 0,40 | ≈ 1,5 GB → US$ 0,25 | < 5 GB → US$ 0,25 | **≈ US$ 3–5/mês** |
| Produção (validação, baixo tráfego, sem ingestão) | ≈ 0,2 GB → US$ 2 | ≈ US$ 0,30 | ≈ US$ 0,25 | < 10 GB → US$ 0,50 | **≈ US$ 3–5/mês** |
| Produção com ingestão a cada 15 min | + ≈ US$ 0,50 | | | | **≈ US$ 4–6/mês** |

**Total incremental: ≈ US$ 7–12/mês**, dentro do uso incluído se os demais projetos deixarem folga. Recomenda-se um limite de uso no workspace (`railway usage`).

Por padrão, os serviços podem escalar até o limite do plano (24 vCPU / 24 GB por serviço). Limitar por serviço (`limitOverride`) é a próxima melhoria de proteção de custo.

## 16. Expansão futura

Mais réplicas da API exigem:
- rate limit e cache fora da memória: um Redis do próprio ambiente, ou o próprio banco;
- então, `WEB_CONCURRENCY`/`replicas` > 1.

Outras expansões:
- **FIRMS:** chave real em `NASA_FIRMS_MAP_KEY` (staging primeiro), com `preserve()` acrescentado ao IaC, mais a homologação H-27/H-28.
- **Backup lógico fora do Railway:** `pg_dump` agendado para armazenamento externo (por exemplo, S3 `sa-east-1`).
- **Observabilidade:** drenagem de logs e métricas de requisição. Hoje elas aparecem no cockpit como "não coletadas".
