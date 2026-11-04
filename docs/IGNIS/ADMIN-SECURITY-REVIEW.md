# IGNIS Orbital — revisão de segurança do Admin Cockpit

Escopo: autenticação, autorização, sessões e operações administrativas introduzidas na branch
`feat/ignis-admin-cockpit` (API e web). Data: 04/11/2026. Ambiente avaliado: pilha local de
validação (`deploy/local`) e testes automatizados contra PostGIS real. Nada foi testado em
staging/produção (fora do escopo autorizado).

Legenda de situação: **Implementado** (código + teste), **Mitigado** (risco reduzido, residual
descrito), **Residual** (aceito/pendente, com recomendação).

## 1. Autenticação

| Item | Situação | Detalhe |
|---|---|---|
| Login | Implementado | `POST /api/v1/auth/login`, JWT HS256, validade `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` (480 min padrão). Segredo fraco é recusado em staging/produção (`config.py`). |
| Enumeração de usuários | Implementado | E-mail inexistente verifica um hash fictício (mesmo custo bcrypt); senha errada, conta inexistente e conta desativada recebem o **mesmo 401**. Teste: `test_deactivated_account_cannot_log_in_and_loses_its_session`. A criação de usuário (somente admin) responde 409 para e-mail repetido — aceitável, o ator já é administrador. |
| E-mail sem distinção de maiúsculas | Implementado | Índice único `uq_users_email_lower` (migração a015); login e criação normalizam. |
| Limite de tentativas | Mitigado | 10 logins/min/IP, 10 trocas de senha/min/IP, 20 ações sensíveis/min/IP, 10 exportações/min/IP. **Residual:** contadores em memória por processo; com várias réplicas o limite efetivo multiplica. Recomendação: limitador compartilhado (Redis) antes de escalar horizontalmente. |
| Política de senha | Implementado | ≥ 12 caracteres, ≥ 5 caracteres distintos, ≤ 72 bytes (limite bcrypt), recusa senhas publicadas/demonstrativas (inclusive como substring). Aplicada em criação, redefinição e troca. |
| Armazenamento | Implementado | bcrypt; hash nunca retorna em nenhuma resposta (`UserRead`/`UserAdminRead` não têm o campo; testes conferem). |
| MFA | Residual | Não há segundo fator. Recomendado para administradores antes de produção ampla. |
| Token no navegador | Residual | Token em `localStorage` (padrão herdado). Exposto a XSS; mitigado por CSP do nginx e ausência de HTML não confiável renderizado. Recomendação futura: cookie `HttpOnly` + `SameSite`. |

## 2. Sessões e revogação

- Claim `sv` no JWT comparado a `users.session_version` em **toda** requisição autenticada
  (`app/dependencies.get_current_user`). Divergência → 401.
- `session_version` é incrementado ao: alterar papel, desativar, reativar, redefinir senha (admin) e
  trocar a própria senha. Tokens antigos deixam de valer imediatamente (teste
  `test_role_change_requires_step_up_and_revokes_sessions`, `test_password_reset_forces_change_and_revokes`,
  E2E "criar, editar, mudar papel…").
- Tokens emitidos antes da a015 não têm `sv` e valem como 0 até expirarem — compatível com o
  `session_version` inicial 0. Revogação desses tokens antigos: qualquer ação acima no usuário.
- Senha provisória (`must_change_password`): a API só permite `/auth/me` e `/auth/change-password`
  até a troca (403 nas demais). A interface leva a `/conta/senha`.

## 3. Autorização (RBAC)

- Papéis fixos e hierárquicos: `publico` 0 < `campo` 1 < `gestor` 2 < `orgao` 3 < `admin` 4,
  verificados no servidor por `require_role(minimum)` em cada endpoint.
- Matriz em `/admin/permissions` é **derivada das dependências reais das rotas**
  (`app/core/permissions.py`); o teste `test_permission_matrix_matches_the_mounted_api` garante que
  ela cobre todas as operações do OpenAPI e que todo `/api/v1/admin/*` (exceto `stats`, órgão+) exige admin.
- Teste `test_admin_endpoints_deny_every_non_admin_role` (campo, gestor, órgão → 403 em 9 endpoints
  admin; anônimo → 401). E2E confirma gestor e campo bloqueados na tela **e** na API.
- Guards do frontend são só navegação; esconder um link não é a proteção.
- Endpoints públicos observados na matriz: login, denúncia pública, leitura de focos/estatísticas,
  malha IBGE, áreas protegidas, geocodificação, clima, saúde e **`POST /api/v1/aurora/chat`**
  (assistente experimental, fora da navegação). **Residual:** avaliar desligar/limitar o chat
  público antes de produção (não chama LLM externo, mas aceita entrada anônima).

## 4. Operações administrativas sensíveis

| Proteção | Situação | Como |
|---|---|---|
| Step-up | Implementado | Papel, desativação, reativação e redefinição de senha exigem `confirm_password` do **administrador que age**, verificado no servidor (bcrypt). Falha → 403, registrada na auditoria (`*.denied`, causa `step_up_failed`) e confirmada antes da resposta. |
| Motivo obrigatório | Implementado | `reason` 5–500 caracteres nas ações sensíveis; vai para a auditoria. |
| Auto-desativação / auto-rebaixamento / auto-redefinição | Implementado | 409 + auditoria (causa `self`). A própria senha usa `/auth/change-password`. |
| Último administrador | Implementado | Não é possível rebaixar nem desativar o último administrador **legítimo** ativo (contas do seed demonstrativo não contam). 409 + auditoria (causa `last_admin`). Teste `test_last_legitimate_admin_cannot_be_removed`. |
| Concorrência | Implementado | (1) Bloqueio consultivo de transação (`pg_advisory_xact_lock`) serializa toda mudança que pode reduzir o conjunto de admins; após obtê-lo, o ator é relido — quem perdeu o papel enquanto esperava recebe 403. (2) `FOR UPDATE` no alvo e nas linhas de admins. (3) Bloqueio otimista `row_version`/`expected_version` → 409 em edição concorrente. Testes `test_concurrent_mutual_demotion_keeps_one_admin` e `test_concurrent_edits_with_the_same_version_conflict`. |
| Exclusão física | Não existe | Rota DELETE removida; contas são desativadas. |
| Envio de senha | Não existe | Nenhuma senha é enviada por e-mail (não há canal seguro implementado). O admin define/gera a senha provisória e a comunica por canal próprio; a troca é obrigatória no primeiro acesso. A senha nunca é devolvida nem registrada. |

## 5. Auditoria

- Cada ação registra ator (id + nome), alvo (`entity_type`/`entity_id`), ação, horário (UTC),
  resultado (`success`/`denied`), causa da recusa e motivo.
- Metadados com chaves de aparência sensível (`password`, `senha`, `token`, `secret`, `hash`, `key`,
  `authorization`) são omitidos na leitura e na exportação, mesmo se algum gravador os incluir.
- Exportação CSV: até 10 000 linhas, proteção contra injeção de fórmula (`= + - @`), a própria
  exportação é auditada (`audit.exported`) e limitada a 10/min.
- A auditoria registra ações de pessoas; logs de infraestrutura (Railway) não são misturados.

## 6. Documentação da API (`/docs`, `/redoc`, `/openapi.json`)

- Configuração `API_DOCS_PUBLIC` (padrão automático): públicos só fora de staging/produção.
  Em staging/produção **as rotas não são montadas (404)** — e não podem ser religadas pela variável
  (`docs_public` força falso). Teste `test_operational_environment_hides_public_docs`.
- Administradores obtêm a especificação em `GET /api/v1/admin/openapi.json` com `Authorization: Bearer`
  (403 para outros papéis, 401 sem token). O Admin Cockpit renderiza um explorador próprio a partir
  desse JSON — sem iframe e **sem token na URL** (E2E verifica as URLs requisitadas).
- O explorador só executa `GET` sem parâmetros de caminho, com a sessão do admin; operações que
  alteram dados não são executadas pela tela.

## 7. Exposição de informação

- `/health` público deixou de expor versão e ambiente (agora só `status` e `service`).
- `/ready` não ecoa erros do driver.
- Cockpit não mostra segredos: chave NASA aparece como "configurada sim/não"; URL do banco, segredo
  JWT e senhas nunca são retornados (teste `test_sources_and_settings_never_expose_secrets`).
- Métricas não coletadas (CPU, memória, tráfego, latência de requisições, disponibilidade histórica)
  são declaradas como indisponíveis — nenhum número inventado.
- Proveniência das execuções (`params`) foi revisada: contém janela, bbox, worker, HTTP status, hash
  e nomes de arquivo — nunca URL com chave.

## 8. Bootstrap do administrador e recuperação de acesso

- Primeiro administrador: `python -m seed.bootstrap_admin --email … --name …` (senha lida da entrada
  padrão, política aplicada, auditado como `user.bootstrap_admin_created`). Com admins já existentes,
  exige `--additional`.
- Senha esquecida de um usuário: outro administrador redefine (senha provisória + troca obrigatória).
- **Todos os administradores sem acesso:** quem tem acesso operacional ao serviço da API (shell do
  Railway) executa `seed.bootstrap_admin --additional`. Não há recuperação self-service por e-mail
  (decisão consciente: sem canal de entrega seguro). Documentar quem detém esse acesso é pendência do
  proprietário.

## 9. Bug pré-existente corrigido nesta entrega

- **Execuções presas em `running` por diferença de relógio:** `started_at` vinha do relógio do banco e
  `finished_at` do relógio da aplicação; com o host da API ~70 ms atrás do banco, o CHECK
  `finished_at >= started_at` rejeitava a finalização. Agora `finished_at = GREATEST(clock_timestamp(),
  started_at)` no banco. Regressão: `test_finish_uses_the_database_clock_even_when_the_host_lags`.
  Relevante no Railway (API e banco em hosts distintos).

## 10. Riscos residuais (resumo)

1. Rate limit em memória por processo (multiplica com réplicas).
2. Sem MFA para administradores.
3. Token JWT em `localStorage`.
4. `POST /api/v1/aurora/chat` público (experimental).
5. Recuperação de acesso total depende de shell no serviço da API.
6. Sem renovação de token: sessão expira em 8 h e exige novo login.
7. `last_login_at` só existe para logins após a migração a015 ("Sem registro" antes disso).
