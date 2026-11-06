# IGNIS Orbital — guia de validação do Admin Cockpit

Como atualizar a pilha local **preservando** o banco de validação (dados reais do INPE e malha
oficial do IBGE), validar o cockpit à mão e reproduzir os testes automatizados.

## 1. Atualizar o ambiente local sem perder dados

Pré-requisitos: Docker Desktop, os dois repositórios lado a lado
(`ignis/ignis-orbital-api` e `ignis/ignis-fire-watch`) nas branches `feat/ignis-admin-cockpit`.

```bash
cd ignis-orbital-api
git fetch && git switch feat/ignis-admin-cockpit && git pull
cd ../ignis-fire-watch
git fetch && git switch feat/ignis-admin-cockpit && git pull
cd ../ignis-orbital-api
bash deploy/local/validate.sh up
```

`up` reconstrói as imagens, roda `alembic upgrade head` (aplica só a migração nova, `a015`),
confere a malha IBGE (SHA-256, sem reimportar se igual), prepara as contas locais, faz uma ingestão
INPE ao vivo e sobe o web. **O volume `ignis-validation_pgdata` é mantido.**

Nunca use `validate.sh reset` para atualizar: ele apaga o volume, os dados ingeridos e as senhas
locais. Para conferir que nada se perdeu:

```bash
bash deploy/local/validate.sh status
```

Esperado: migração `a015`, 184 municípios + 1 UF, focos e execuções ≥ os de antes.

Credenciais locais: `bash deploy/local/validate.sh credentials` (geradas por instalação, só nesta
máquina; contas `admin|gestor|campo.validacao@example.org`).

## 2. Roteiro manual (≈ 15 min)

1. `http://localhost:8080/login` como **admin** → abre `/admin`. Confira: API "Respondendo", banco
   "Conectado" com latência, worker, focos persistidos e municípios monitorados batem com
   `GET /api/v1/admin/overview`; bloco "Métricas não disponíveis" presente.
2. **Usuários → Novo usuário**: nome, e-mail, papel "Equipe de campo", senha provisória (Gerar),
   motivo. A conta aparece com "Troca de senha pendente" e "Sem registro" de login.
3. Em outra janela anônima, entre com a conta nova → a tela pede a troca de senha → após trocar,
   cai em "Operação de campo".
4. De volta ao admin, na gaveta do usuário: edite o nome (salva), **Alterar papel** com senha errada
   (recusa, registrada) e depois correta. A sessão do usuário na janela anônima cai ao recarregar.
5. **Desativar** com motivo e sua senha. Na janela anônima, tente entrar: "E-mail ou senha
   incorretos, ou conta sem acesso." (mesma mensagem de senha errada).
6. Abra **a sua própria conta** em Usuários: aviso "Esta é a sua conta" e ações bloqueadas.
7. **Auditoria**: filtre por "Usuário criado", "Papel alterado", "Conta desativada"; abra um evento
   (ator, alvo, motivo, resultado); **Exportar CSV** e confira que a exportação aparece na trilha.
8. **Fontes de dados**: NASA FIRMS "Não configurada"/"Desativada" sem chave (nunca "Operando");
   INPE com último sucesso. **Executar** INPE → acompanhe em **Execuções**.
9. **API e diagnóstico**: "Executar" diagnóstico (HTTP 200), abra uma operação e execute um GET.
10. **Permissões** e **Configuração**: somente leitura, sem segredos.
11. Saia e entre como **gestor** e **campo**: `/admin` mostra "Acesso não permitido"; o menu não tem
    Admin Cockpit.
12. Celular (ou janela estreita): o menu vira gaveta (botão ☰), tabelas rolam na horizontal.

## 3. Testes automatizados

### Backend (pytest contra PostGIS real)

```bash
docker run -d --name ignis-test-pg -e POSTGRES_USER=ignis -e POSTGRES_PASSWORD=local-only \
  -e POSTGRES_DB=postgres -p 127.0.0.1:55434:5432 postgis/postgis:16-3.4
IGNIS_TEST_POSTGIS_URL=postgresql://ignis:local-only@127.0.0.1:55434/postgres \
IGNIS_REQUIRE_POSTGIS_TESTS=1 APP_ENV=test .venv/Scripts/python -m pytest -q
```

Use `127.0.0.1`, não `localhost`: no Windows, `localhost` tenta `::1` primeiro e cada conexão espera
~2 s, deixando a suíte lenta.

`tests/test_postgis_admin.py` (23 testes) cobre: negação de todos os endpoints admin para campo,
gestor e órgão (401 anônimo); criação sem eco de senha e e-mail único sem distinção de caixa; troca
obrigatória de senha bloqueando a API e rotacionando a sessão; bloqueio otimista; step-up com falha
auditada; motivo obrigatório; auto-ações bloqueadas; último administrador legítimo; rebaixamento
mútuo concorrente (sobra 1 admin); edição concorrente (200 + 409); desativação com login recusado e
resposta idêntica à de conta inexistente; redefinição de senha; paginação/filtros/busca; auditoria
(filtros, envolvido, período, sanitização, CSV com proteção de fórmula, exportação auditada); métricas
do cockpit iguais ao SQL; fontes/configuração sem segredos; execuções com filtros e detalhe; matriz de
permissões = OpenAPI; `/docs` desligado em staging com especificação admin protegida; metadados
profissionais sem texto acadêmico.

### Frontend

```bash
npm ci --ignore-scripts
npm run typecheck && npm run lint && npm test && npm run build
```

Unitários: fuso de Fortaleza, conversão de filtros para UTC, espelho de permissões, gerador de senha
provisória, explorador OpenAPI, mensagens de erro 422/5xx, trilhas e menus (sem Aurora/ESG/Economia/
Ranking), destino por papel e troca pendente, rótulos de auditoria, estados de erro/vazio/paginação.

### E2E (Playwright contra a pilha real)

```bash
bash deploy/local/validate.sh e2e                       # tudo
bash deploy/local/validate.sh e2e e2e/admin.spec.ts     # só o cockpit
```

`e2e/admin.spec.ts`: login admin → cockpit com métricas iguais à API → fontes/execuções → criar
usuário → primeiro acesso com troca de senha → editar → papel com senha errada e certa → sessão do
usuário revogada → desativar → login da conta desativada recusado → histórico → própria conta
protegida (UI e API 409) → auditoria → API docs autorizada sem token em URL → gestor e campo negados
(tela e API 403) → nenhuma tela operacional com dados fictícios ou texto acadêmico; rotas removidas
dão 404. Cada execução cria uma conta `e2e.<timestamp>@example.org` que termina **desativada** (não
há exclusão física).

Capturas: `IGNIS_EVIDENCE_DIR=… node e2e/capture-admin-evidence.mjs` (com as variáveis
`IGNIS_E2E_PASSWORD_ADMIN` e `IGNIS_E2E_PASSWORD_GESTOR`), somente leitura.

## 4. Resultados desta entrega (04/11/2026, Windows 11 + Docker Desktop)

| Verificação | Resultado |
|---|---|
| pytest completo contra PostGIS real | **429 passed, 1 skipped**, cobertura total 87% (`app/users/*` 93–100%, `app/admin/router.py` 88%, `app/audit/*` 92–100%) |
| `tests/test_postgis_admin.py` | 23/23 |
| ruff | sem apontamentos |
| Frontend `typecheck` / `lint` | limpo / 0 erros (9 avisos react-refresh pré-existentes em `components/ui`, `UserContext`, `router`) |
| Vitest | 56/56 (6 arquivos) |
| Build + varredura do bundle | OK; nenhuma ocorrência de FIAP/Global Solution/RM/MOCK_USERS/FALLBACK_; nenhum chunk de Aurora/ESG/Economia/Ranking |
| Playwright (pilha local real) | **27/27** (9 do cockpit + 18 anteriores; desktop e mobile) |
| Pilha local | `a014 → a015` aplicada com `validate.sh up`; volume preservado; 185 jurisdições; focos e execuções acrescidos por ingestões INPE reais |
| Capturas | 16 em `evidence/admin-cockpit-2026-11-04/` |

Defeitos encontrados e corrigidos durante a validação:
- execuções presas em `running` por diferença de relógio API × banco (pré-existente; ver revisão de segurança §9);
- texto de ajuda dentro do `<label>` contaminava o nome acessível dos campos (o campo de senha respondia por "E-mail");
- `/health` público expunha versão e ambiente;
- índice "Risco meteorológico 0–100" sem metodologia validada aparecia no painel e na sala de crise (agora só medições);
- isolamento entre testes: a fixture de admin apagava o registro de importação do IBGE usado por outro módulo.

Apontamento de CI: o GitGuardian marcou como "Generic Password" uma senha **de teste** literal no
primeiro commit do PR (`tests/test_postgis_admin.py`). As senhas de teste passaram a ser geradas por
execução (commit seguinte); o incidente já registrado no painel do GitGuardian precisa ser marcado
pelo proprietário (não há segredo real; o histórico não foi reescrito).

## 5. Staging no Railway (04/11/2026)

Endereço: **https://ignis-web-staging.up.railway.app**. Same-origin: a API responde em `/api/v1`; não
há domínio público para ela.

**Contas de homologação** (`admin|gestor|campo.homologacao@example.org`):
- as senhas existem só em `ignis-orbital-api/deploy/local/.staging.env`, ignorado pelo Git, na estação que
  provisionou;
- nenhuma conta usa senha publicada nem a mesma senha da pilha local;
- para entregar acesso a outra pessoa, crie uma conta para ela pelo cockpit (senha provisória + troca
  obrigatória), em vez de repassar essas.

### Roteiro manual

O mesmo do §2, trocando `http://localhost:8080` pelo endereço acima. Diferenças esperadas no staging:
- selo **"Homologação"** no cabeçalho do cockpit;
- **NASA FIRMS** "Não configurada / Não homologada" (sem chave);
- **INPE** "Operando" com focos reais do dia;
- **Denúncias:** `/public/report` mostra "O recebimento de denúncias está desativado nesta instalação" e
  **não** exibe formulário;
- **Aurora:** não existe (`POST /api/v1/aurora/chat` → 404);
- **API e diagnóstico:** o link `/docs` não aparece (documentação só pelo explorador autenticado).

### E2E contra o staging

```bash
cd ignis-fire-watch
set -a; . ../ignis-orbital-api/deploy/local/.staging.env; set +a
export IGNIS_WEB_URL=$STAGING_URL IGNIS_API_URL=$STAGING_URL \
  IGNIS_E2E_EMAIL_ADMIN=$STAGING_ADMIN_EMAIL IGNIS_E2E_PASSWORD_ADMIN=$STAGING_ADMIN_PASSWORD \
  IGNIS_E2E_EMAIL_GESTOR=$STAGING_GESTOR_EMAIL IGNIS_E2E_PASSWORD_GESTOR=$STAGING_GESTOR_PASSWORD \
  IGNIS_E2E_EMAIL_CAMPO=$STAGING_CAMPO_EMAIL IGNIS_E2E_PASSWORD_CAMPO=$STAGING_CAMPO_PASSWORD
npx playwright test
```

O login tem limite de 10 tentativas por minuto por IP. Não rode duas suítes seguidas sem um intervalo
de cerca de 1 minuto. Cada execução cria uma conta `e2e.<timestamp>@example.org`, que termina
desativada.

### Resultados de 04/11/2026

| Verificação | Resultado |
|---|---|
| E2E contra o staging, com as rotas de denúncia e aviso novas (web `c0089e4`, API `dc089bd`) | **29/29** (desktop + mobile), nenhum ignorado |
| E2E contra o staging, versão anterior (web `b6cf4a2`, API `2aed1f3`) | 27/27 |
| E2E na pilha local | 29/29 |
| pytest completo (PostGIS real) | 439 passed, 1 skipped, cobertura 88 % |
| Vitest / typecheck / lint | 56/56 / limpo / 0 erros |
| IaC (`npm run check`) | 28/28 |
| CI dos PRs (`staging` = `feat/ignis-admin-cockpit`) | API: todos os jobs verdes. Web: verde após reexecução (a 1ª execução do E2E usou a API anterior ao endpoint `/reports/intake`, corrida entre os dois repositórios) |
| Rollback do `ignis-web` (`deploymentRollback` para o deploy anterior e de volta) | 8 s para cada lado, com `/healthz` e `/ready` OK durante a troca |
| Capturas | 16 em `evidence/railway-staging-2026-11-04/` |

Detalhes, IDs e bloqueios: [RAILWAY-PROVISIONING-REPORT.md](RAILWAY-PROVISIONING-REPORT.md).
