# IGNIS — Resultados da validação técnica (04/11/2026)

Registro do que foi **efetivamente executado** pela engenharia antes da avaliação humana. Nada aqui foi simulado.
Onde houve interceptação de rede, ela está declarada.

**Ambiente local:**
- Windows 11 com Docker 29.7.2 e Git Bash;
- PostGIS 16-3.4;
- imagens construídas a partir de `feat/ignis-human-validation` nos dois repositórios.

**Pilha:** `deploy/local/validate.sh up`, projeto `ignis-validation`, sem dados demonstrativos.

## 1. Dados usados

| Item | Valor |
|---|---|
| Malha oficial | IBGE Malha Municipal Digital 2025, 184 municípios + UF, importada e conferida por SHA-256 |
| Fonte real | INPE Programa Queimadas, CSV diário de dados abertos, ingestão **ao vivo** em 04/11/2026 às 06:27 UTC |
| Arquivos lidos | `focos_diario_br_20261103.csv` (2.192.102 bytes, SHA-256 `1767fe78…4701`, ETag `"2172e6-65f6d28de5f80"`, 14.938 linhas no Brasil, 532 dentro do envelope do CE) e `focos_diario_br_20261104.csv` (nenhuma linha no envelope) |
| Gravado | **299 focos** em **88 municípios**. Observados entre 03/11/2026 00:12 e 23:31 UTC; ingeridos em 04/11/2026 06:27 UTC. 233 focos fora do Ceará foram contados, não gravados |
| Satélites | NOAA-20 107 · NOAA-21 75 · AQUA_M-T 50 · GOES-19 35 · TERRA_M-M 11 · METOP-B 9 · TERRA_M-T 7 · METOP-C 4 · MSG-03 1 |
| NASA FIRMS | **Desabilitada**: sem chave; 4 execuções `disabled`/`missing_api_key`, 0 requisições |
| Amostra histórica | `data/samples/inpe/focos_diario_br_20261103.csv` (proveniência no README da pasta). Usada **só na CI**, por ser determinística. Na validação local, os dados foram ao vivo |

## 2. Execuções e resultados

| # | Verificação | Como | Resultado |
|---|---|---|---|
| R1 | Subida da pilha completa | `validate.sh up` (duas vezes, a segunda com os segredos reestruturados) | exit 0; API e web `ok`; 184 municípios |
| R2 | Ingestão real INPE | primeira rodada | `fetched 532`, `out_of_scope 233`, **`inserted 299`**, `duplicate 0` |
| R3 | Reprocessamento | `validate.sh ingest` (duas vezes) | os dois arquivos responderam `304`; `inserted 0`; `count(*) = count(DISTINCT dedup_key) = 299` |
| R4 | Persistência após reinício | `stop` e `up` | 299 focos e 184 municípios antes e depois |
| R5 | Integridade espacial | SQL do guia, §7 | 0 focos fora do município atribuído |
| R6 | Interface: mapa, filtros e detalhe | navegador (Chromium do app) e Playwright | contagens iguais às da API; detalhe com coordenada persistida; console sem erros |
| R7 | Sala de Crise sem incidente | `/gestor/war-room` como gestor | "Nenhum incidente crítico ativo", nenhuma ação disponível |
| R8 | E2E Playwright local | `validate.sh e2e` | **18 passando** (16 em desktop e 2 em mobile), 0 *skip* |
| R9 | E2E na CI | job "E2E (Playwright, pilha real FastAPI + PostGIS)" nos dois repositórios | passou nas duas primeiras execuções (api run `41790574960`, web run `41790578136`) |
| R10 | Backend completo (local) | `pytest` com PostGIS descartável | 404 passando, 1 pulado (SIGTERM, só fora do Windows); cobertura 85,10% |
| R11 | Frontend | typecheck, ESLint (0 erros), Vitest | Vitest: 40 passando |
| R12 | Medição de consultas | 50 mil focos sintéticos num banco descartável, `EXPLAIN ANALYZE` | 0,4 a 17 ms com os índices existentes; GeoJSON municipal em 0,99 MB, com ~330 ms para simplificar a geometria e cache em memória depois |

**Teste de mutação no E2E:** com o filtro de município propositalmente quebrado no frontend (o parâmetro deixava de ser enviado), o teste "filtro por município bate com a API" **falhou**. O código foi restaurado e verificado.

**Interceptação declarada:**
- os tiles do OpenStreetMap são trocados por uma imagem em branco nos E2E, para não depender de serviço externo;
- os testes de falha derrubam a rota da API de propósito: indisponibilidade de focos e de indicadores, e envio de denúncia.

Nenhum teste de integração usa tela simulada.

## 3. Defeitos encontrados e corrigidos

| Defeito | Onde | Como foi descoberto | Correção |
|---|---|---|---|
| A simplificação do GeoJSON nunca acontecia: o asyncpg tipava a tolerância como inteiro, e 0,0005 virava 0 | backend, `queries.jurisdictions_geojson` | teste de integração (contagem de vértices) | `CAST(:tol AS float8)` |
| Recarregar qualquer tela do gestor mandava para o login: o perfil era restaurado só depois de `/auth/me`, quando os guardas de rota já tinham redirecionado | frontend, `UserContext` | E2E (7 testes falhando) | perfil salvo restaurado na inicialização; o token continua validado por `/auth/me` e pela API |
| O gráfico "Incidentes por semana (Jan–Mai 2026)" do painel mostrava dados ESG demonstrativos em modo API, sempre que o banco estava vazio | frontend, painel | revisão | substituído por focos por dia vindos da API |
| Em modo API, falhas de consulta recaíam em dados fictícios (denúncias, missões, áreas, recursos, equipes, ESG) | frontend, hooks | revisão | listas vazias, com a falha sinalizada; ESG "indisponível" |
| O portal público mostrava incidentes (endpoint autenticado, que recaía em demo) e polígonos demonstrativos de áreas protegidas | frontend, portal | revisão | portal só com focos de satélite e a malha IBGE; camada de UC "indisponível" |
| O CSP não liberava `tile.openstreetmap.org` (só `*.tile`) | frontend, nginx | revisão do mapa | host adicionado ao `img-src` |
| O botão de saída dizia "Trocar Perfil" em modo API | frontend | E2E de logout | "Sair" |
| `passlib` imprimia um *traceback* sobre `bcrypt.__about__` a cada boot | backend | log da pilha local | logger silenciado (o hash não era afetado) |
| GitGuardian (5 alertas "Generic Password" no commit `8883c0c`): interpolação `${…}` na URL do banco do compose e prefixos fixos das senhas geradas | backend, `deploy/local` | CI | senha via secret do Compose (`POSTGRES_PASSWORD_FILE`), URL montada pelo script, senhas sem prefixo literal. **Os alertas do commit já publicado continuam no histórico, que não foi reescrito** (ver §4) |
| SonarCloud no PR #8: segurança C (npm sem `--ignore-scripts`, `npx` sem versão, *path traversal* em `--inpe-fixture`) e *code smells* (complexidade, 503 não documentado, exceção derivada de `SystemExit`) | backend e CI | Quality Gate | todos tratados; `--inpe-fixture` restrito a `data/samples/inpe/` |

## 4. Limitações e falhas conhecidas

- **NASA FIRMS sem homologação com chave real.** Foi validada só com fixtures dos arquivos públicos e com a resposta real a uma chave inválida.
- **GitGuardian no PR #8:**
  - os 5 alertas do commit `8883c0c` são falsos positivos (nenhum valor secreto: interpolação de variável e prefixos de geração);
  - o código atual já não tem o padrão;
  - como não reescrevemos histórico, **o proprietário precisa marcar os 5 alertas no painel do GitGuardian**. Até lá, esse check pode continuar vermelho.
- **Teste de processo morto (`test_killed_process_run_is_recovered_by_the_next_round`):** falhou **uma vez** localmente sob carga (Windows, pilha Docker ativa) e passou em todas as reexecuções. A asserção agora registra o `error_code` para diagnóstico; o acompanhamento está no relatório final.
- **Sala de Crise, equipes, recursos e missões:** sem dados demonstrativos, ficam vazios. Há o fluxo real de denúncia → validação → incidente, mas esses módulos não foram exercitados ponta a ponta pelo E2E nesta missão.
- **Rate limit em memória, por processo:** com mais de uma réplica, o limite efetivo se multiplica. Continua pendente (Fase 1, Sprint 1.4).
- **Mapa base:** o OpenStreetMap padrão só serve para testes de baixo volume. Um provedor institucional é configurável (`VITE_TILE_URL`).
