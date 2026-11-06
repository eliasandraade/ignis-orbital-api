# IGNIS Orbital — Admin Cockpit

Área administrativa em `/admin` (somente papel `admin`), com layout próprio: sidebar agrupada,
cabeçalho com trilha de navegação e selo do ambiente, estados de carregamento/vazio/erro em todas as
telas, gaveta de navegação no celular. Toda informação vem da API; horários em Fortaleza.

Capturas reais da pilha local: [`evidence/admin-cockpit-2026-11-04/`](evidence/admin-cockpit-2026-11-04/).

## Telas

| Rota | Conteúdo | Ações |
|---|---|---|
| `/admin` | API (versão, ambiente), banco (conectado + latência da consulta de verificação **medida agora**), evidência do worker (só execuções agendadas registradas), falhas de ingestão em 7 dias, focos persistidos e em 24 h, municípios monitorados e com focos em 7 dias, última gravação, usuários ativos/inativos/por papel/troca pendente, último sucesso por fonte, histórico de 30 dias, últimas execuções, eventos recentes. Bloco **"Métricas não disponíveis"** declara o que não é coletado (CPU, memória, tráfego, latência de requisições, uptime histórico). | atualização a cada 60 s |
| `/admin/users` | Lista paginada (20/página), busca por nome/e-mail, filtros por papel e situação, criação, data de criação real, último login real ("Sem registro" quando não há) | **Novo usuário** (senha provisória digitada ou gerada, troca obrigatória); gaveta com situação, **Alterar papel**, **Desativar/Reativar**, **Redefinir senha** (todas com senha do admin + motivo), edição de nome/e-mail/equipe (com controle de versão), histórico administrativo do usuário |
| `/admin/permissions` | Papéis e descrição; matriz somente leitura endpoint × papel derivada das rotas reais; filtro por domínio e texto | — (sem editor: RBAC estático) |
| `/admin/sources` | NASA FIRMS e INPE: estado, configuração (sem chave), homologação, último sucesso, observação mais recente, prazo de atualização, origem (ao vivo/fixture), por produto: estado, última execução, contadores, erro sanitizado. IBGE: dataset carregado (versão, data de referência, SHA-256) | **Executar** ingestão manual (endpoint existente `POST /orbital-alerts/ingest`, auditado, sem duplicar execução ativa) |
| `/admin/jobs` | `ingestion_runs`: fonte/produto, disparo, início, duração, situação, novos/lidos; filtros por fonte, situação, disparo e período (Fortaleza); paginação; gaveta com contadores, erro e proveniência. Aviso: a tela não observa nem controla o processo do worker no Railway | acompanhamento de execução em andamento (atualiza a cada 5 s) |
| `/admin/api` | Explorador OpenAPI a partir de `/api/v1/admin/openapi.json` (Bearer no cabeçalho): operações por domínio, parâmetros, respostas, cadeado nas autenticadas; diagnóstico rápido (`/health`, `/ready`, `/auth/me`, estado das fontes) com latência medida pelo navegador | executar `GET` sem parâmetros de caminho com a sessão; baixar o OpenAPI; link para `/docs` só quando o ambiente o expõe |
| `/admin/audit` | Trilha paginada (25/página), filtros por ação, entidade, ator e período; filtro "envolvendo usuário"; gaveta do evento com ator, alvo, resultado, motivo da recusa e metadados permitidos | **Exportar CSV** (auditado) |
| `/admin/settings` | Aplicação/build, fontes e atualização, segurança e sessão — tudo marcado como gerenciado pelo ambiente; nenhum segredo | — (somente leitura) |
| `/conta/senha` | Troca da própria senha (obrigatória com senha provisória) | — |

## Endpoints novos ou alterados (API)

| Método | Caminho | Acesso | Observação |
|---|---|---|---|
| GET | `/api/v1/admin/overview` | admin | métricas do cockpit |
| GET | `/api/v1/admin/sources` | admin | fontes + configuração sem segredos + IBGE |
| GET | `/api/v1/admin/ingestion-runs` | admin | `page`, `size≤100`, `source`, `product`, `status`, `trigger`, `from`, `to` |
| GET | `/api/v1/admin/ingestion-runs/{id}` | admin | detalhe |
| GET | `/api/v1/admin/permissions` | admin | matriz derivada das rotas |
| GET | `/api/v1/admin/settings` | admin | configuração efetiva sem segredos |
| GET | `/api/v1/admin/openapi.json` | admin | especificação completa, inclusive com `/docs` desligado |
| GET | `/api/v1/admin/users` | admin | `page`, `size`, `q`, `role`, `status=active\|inactive` |
| POST | `/api/v1/admin/users` | admin | `temporary_password` (política), `must_change_password=true` |
| GET | `/api/v1/admin/users/{id}` | admin | `UserAdminRead` (sem hash) |
| PATCH | `/api/v1/admin/users/{id}` | admin | nome/e-mail/equipe + `expected_version` |
| POST | `/api/v1/admin/users/{id}/role` | admin | step-up + motivo, revoga sessões, último admin protegido |
| POST | `/api/v1/admin/users/{id}/deactivate` | admin | idem; bloqueia a própria conta |
| POST | `/api/v1/admin/users/{id}/activate` | admin | step-up + motivo |
| POST | `/api/v1/admin/users/{id}/reset-password` | admin | step-up + motivo, troca obrigatória, revoga sessões |
| GET | `/api/v1/admin/users/{id}/audit` | admin | eventos em que o usuário é ator ou alvo |
| GET | `/api/v1/admin/audit-logs` | admin | filtros `action`, `entity_type`, `entity_id`, `user_id`, `involving_user`, `actor`, `from`, `to` |
| GET | `/api/v1/admin/audit-logs/export` | admin | CSV (≤ 10 000 linhas), auditado |
| POST | `/api/v1/auth/change-password` | autenticado | nova sessão; demais sessões revogadas |
| DELETE | `/api/v1/admin/users/{id}` | — | **removido** (sem exclusão física) |
| GET | `/health` | público | não expõe mais versão/ambiente |
| GET | `/docs`, `/redoc`, `/openapi.json` | público só fora de staging/produção | 404 em staging/produção |

OpenAPI: título, resumo, descrição (autenticação, permissões, paginação, datas, erros), contato
Andrade Systems, 19 tags de domínio descritas em pt-BR, resumos das operações a partir das docstrings,
códigos de erro documentados nas rotas administrativas.

## Migração

`a015_user_sessions_and_admin` (revisão `a015`, sobre `a014`), não destrutiva:
`users.session_version` (int, 0), `users.row_version` (int, 1), `users.last_login_at` (timestamptz,
nulo), `users.must_change_password` (bool, falso) e índice único `uq_users_email_lower` em
`lower(email)`. `downgrade` remove os campos e o índice. Testada em upgrade → downgrade → upgrade
(`test_migration_upgrade_downgrade_upgrade`) e aplicada na pilha local preservando os dados
(antes: 299 focos/185 jurisdições/15 execuções em `a014`; depois: `a015`, mesmas jurisdições, focos e
execuções acrescidos por ingestões INPE reais).

**Atenção para staging/produção:** se já existirem dois e-mails iguais com maiúsculas diferentes, a
criação do índice falha. Verificar antes do deploy:
`SELECT lower(email), count(*) FROM users GROUP BY 1 HAVING count(*) > 1;`

## Testes

Ver [ADMIN-VALIDATION-GUIDE.md](ADMIN-VALIDATION-GUIDE.md) para os resultados e como reproduzir.
