# IGNIS — Pronto para validação humana?

Data: 04/11/2026. Missão "Autonomia total de desenvolvimento" (Sprints 1.3/1.4 necessárias à validação).
**Não houve merge, deploy, provisionamento no Railway, alteração de DNS ou segredos operacionais, nem acesso a banco de produção.**

Guia do avaliador: [HUMAN-VALIDATION-GUIDE.md](HUMAN-VALIDATION-GUIDE.md). Execuções e evidências: [HUMAN-VALIDATION-RESULTS.md](HUMAN-VALIDATION-RESULTS.md).

> O IGNIS **não** está pronto para uso oficial por Corpo de Bombeiros, Defesa Civil ou qualquer órgão. Não há isolamento multi-institucional nem integração com órgãos. O objetivo aqui é **validação humana supervisionada em ambiente de teste**.

## A. Estado geral

| Situação | Itens |
|---|---|
| **Pronto** | Focos persistidos no PostGIS servidos pela API (sem chamada a NASA/INPE na leitura); 184 municípios oficiais (IBGE 2025) e GeoJSON; mapa operacional do Ceará com filtros, detalhe, legenda e situação das fontes; painel e portal público com indicadores reais; pilha local reproduzível com um comando; E2E contra a pilha real; CI com o E2E integrado nos dois repositórios |
| **Parcial** | NASA FIRMS: código, testes e contrato prontos, mas **sem homologação com chave real**. Sala de Crise, equipes, recursos e missões funcionam contra a API, porém o banco de validação não tem dados demonstrativos (ficam vazios) e esses módulos não têm E2E desta missão |
| **Indisponível (identificado na interface)** | Camada de unidades de conservação (sem base oficial validada); correlação FIRMS × INPE; tempo médio de resposta ("n/d"); integração com órgãos (inexistente, avisada em toda tela) |

## B. Backend (`ignis-orbital-api`)

| Endpoint | Acesso | Comportamento real |
|---|---|---|
| `GET /api/v1/orbital-alerts` | público, 60/min/IP | Focos do PostGIS. Filtros `from`/`to` (≤ 92 dias; padrão 7), `source`, `satellite`, `jurisdiction` (IBGE), `bbox` (≤ 20°); `size` ≤ 5000 com `truncated`; coordenada persistida; `observed_at` e `ingested_at`; `persisted=true`; `sources` |
| `GET /api/v1/orbital-alerts/sources` | público | Estado por fonte e produto: `live`, `stale` (> 60 min, configurável), `degraded`, `unavailable`, `disabled`, `never_ingested`; última ingestão separada da observação mais recente; origem `live` ou `fixture` |
| `GET /api/v1/orbital-alerts/stats` | público | Totais, municípios com focos, por fonte, satélite e dia, top 10 (mesmos filtros) |
| `GET /api/v1/orbital-alerts/{id}` | público | Um foco, com a linha original do provedor |
| `GET /api/v1/jurisdictions/municipalities` | público | 184 municípios com contagem na janela e versão da malha; 503 sem malha |
| `GET /api/v1/jurisdictions/geojson` | público, 30/min/IP | Estado ou municípios (SRID 4326), simplificação só para exibição, ETag e cache |
| `POST /api/v1/orbital-alerts/ingest`, `GET /ingestion-runs[/{id}]` | admin | Sprint 1.2, sem mudança |

**Mudanças de infraestrutura e migrations:**
- Nenhuma migration nova nesta missão (`a014` continua a última).
- A medição com 50 mil focos não justificou índice novo.

**Removido:**
- a leitura ao vivo da FIRMS (`app/integrations/nasa_firms`);
- o modo de alertas demonstrativos.

**Novo:**
- worker `--inpe-fixture`, restrito a `data/samples/inpe/`;
- `seed.validation_accounts`, só em development/test e sem variáveis do Railway;
- `SKIP_DEMO_SEED`, que só desliga o seed demo, nunca o liga.

## C. Frontend (`ignis-fire-watch`)

| Tela | Integração |
|---|---|
| Mapa orbital (gestor `/gestor/map` e público `/public/map`) | Contorno do CE e limites municipais pela API. Focos pela coordenada persistida (renderização em canvas; até 5000 por janela, sem necessidade medida de agrupamento). Filtros de período (24 h, 48 h, 7 d, 30 d ou intervalo), fonte, satélite e município. Detalhe: fonte, produto/satélite, horários em Fortaleza e UTC, município, coordenadas, confiança/FRP/brilho só com semântica conhecida, proveniência e aviso "não é incêndio confirmado". Legenda por fonte, nunca gravidade. Estados de carregamento, vazio (diz se a ausência pode ser afirmada), erro e fonte desabilitada |
| Painel do gestor | Seção "Monitoramento orbital — dados persistidos" calculada por `/stats`. O gráfico ESG demonstrativo saiu. Cartões de incidentes e equipes mostram o que a API tem |
| Portal público | Só focos de satélite e malha IBGE. Glossário detecção × alerta × incidente × incêndio confirmado × simulação; 193 em emergência |
| Sala de Crise e Economia Espacial | Cartão orbital com dados persistidos. Ações sem incidente não ficam disponíveis; ativação de protocolo só grava no IGNIS, com confirmação, e nunca notifica órgãos |
| Modo API | Nenhum fallback demonstrativo em falha de consulta (listas vazias com a falha sinalizada; ESG "indisponível") |
| Sessão | Recarregar a página mantém a sessão (defeito corrigido); "Sair" limpa o token; token inválido volta ao login |

## D. Dados

| Fonte | Uso | Quantidade (validação local) | Horários |
|---|---|---|---|
| INPE, CSV diário de dados abertos (ao vivo) | Ingestão real em 04/11/2026 06:27 UTC | 532 no envelope, 233 fora do CE, **299 gravados**, em 88 municípios | Observados em 03/11/2026, 00:12–23:31 UTC |
| INPE, amostra histórica `data/samples/inpe/focos_diario_br_20261103.csv` | Só na CI (determinística); marcada `fixture` na interface | 498 no envelope do arquivo de 04/11 03:05 UTC | Os horários originais, nunca apresentados como de hoje |
| NASA FIRMS | Desabilitada (sem chave) | 0 requisições | — |
| IBGE Malha Municipal 2025 | Jurisdições | 184 municípios + UF | Referência 30/04/2025 |

## E. Segurança

**Riscos corrigidos nesta missão:**
- portal público consultava endpoint autenticado e exibia polígonos demonstrativos;
- painel e hooks recaíam em dados fictícios em modo API;
- `--inpe-fixture` aceitava qualquer caminho (*path traversal*, SonarCloud);
- instalação npm com scripts e `npx` sem versão na CI;
- padrões de senha no compose local (GitGuardian): agora há secret do Compose e senhas geradas por instalação, fora do Git;
- o procedimento local se recusa a rodar com variáveis do Railway, `DATABASE_URL` ou `APP_ENV` operacional.

**Riscos residuais:**

| # | Risco | Situação |
|---|---|---|
| RS-1 | Rate limit em memória por processo; com N réplicas, o limite efetivo é N vezes maior | Pendente (Fase 1, Sprint 1.4). A API segue com 1 réplica no IaC |
| RS-2 | Sem isolamento multi-institucional (organizações, escopo de dados) | Bloqueia uso por mais de um órgão |
| RS-3 | Mapa base OpenStreetMap padrão: política de uso de baixo volume | Trocar via `VITE_TILE_URL` antes de público amplo |
| RS-4 | CSP com `style-src 'unsafe-inline'` (Leaflet e estilos inline) | Pré-existente; aceito para o protótipo |
| RS-5 | Termos de uso e atribuição do INPE não publicados na página de dados abertos | Atribuição exibida no portal; confirmar com o INPE |

## F. Testes

| Suíte | Resultado |
|---|---|
| Backend `pytest` (local, PostGIS descartável) | 404 passando, 1 pulado (SIGTERM, só fora do Windows; roda na CI Linux); cobertura 85,10% |
| Backend na CI (run `41793767587`, commit `58e47eb`) | Ruff, Pytest + cobertura, Migrations, Docker, IaC, pip-audit, lockfile, **E2E** e SonarCloud: verdes (Quality Gate OK, 0 issues). **GitGuardian vermelho** pelos 5 alertas históricos do commit `8883c0c` (ver I-1) |
| Frontend na CI (run `41794753932`, commit `8b5080c`) | **Todos verdes**: typecheck, ESLint (0 erros), Vitest (40), build API e demo, imagem Railway, `npm audit` (0 vulnerabilidades), GitGuardian e **E2E**. A execução anterior tinha falhado porque o Vitest pegou o arquivo do Playwright, o que foi corrigido |
| E2E Playwright (pilha real) | Local: 18 passando (16 desktop + 2 mobile), 0 *skip*. CI: passou nas duas execuções de cada repositório |
| Mutação | O E2E de município falha com o filtro quebrado; o teste de GeoJSON pegou o defeito real da tolerância |
| Estabilidade | `test_killed_process_run_is_recovered_by_the_next_round` falhou 1 vez em 10 execuções locais sob carga (causa não reproduzida; a asserção agora registra o `error_code`); 9 sucessos seguidos depois |

**Cobertura E2E dos 15 cenários pedidos:**

| Cenário | Situação |
|---|---|
| 1 inicialização | ✓ |
| 2 login (pelo formulário) | ✓ |
| 3 painel com dados persistidos (comparado com a API) | ✓ |
| 4 mapa | ✓ |
| 5 detecções corretas | ✓ |
| 6 filtro por município | ✓ |
| 7 filtro por período | ✓ |
| 8 detalhe do foco | ✓ painel de detalhe; o popup do ponto no canvas não é clicado pelo teste |
| 9 estado vazio | ✓ |
| 10 falha da API | ✓ |
| 11 fonte desabilitada | ✓ |
| 12 portal público sem endpoints internos | ✓ |
| 13 logout e token inválido | ✓ |
| 14 bloqueio de rotas de admin e campo | ✓ |
| 15 nenhuma ação sem backend afirma sucesso | ✓ |

**Checagens transversais:** console sem erros em todos os testes que não provocam falha de propósito; dimensões desktop e mobile.

## G. Pull requests

Todas empilhadas, sem merge:

| PR | Branch → base | Commits desta missão |
|---|---|---|
| [ignis-orbital-api#8](https://github.com/eliasandraade/ignis-orbital-api/pull/8) | `feat/ignis-human-validation` → `feat/sprint-1.2-real-ingestion` (#7 → #6 → #5 → #3) | `44f848a` leitura PostGIS e malha; `8883c0c` pilha local, contas e E2E na CI; `58e47eb` Sonar, GitGuardian e docs; mais o commit deste relatório |
| [ignis-fire-watch#7](https://github.com/eliasandraade/ignis-fire-watch/pull/7) | `feat/ignis-human-validation` → `infra/railway-only` (#6 → #4) | `aa3e5e3` mapa, painel e portal; `227e5ad` E2E e sessão; `9c26a78` lint, responsivo e evidências; `8b5080c` Vitest só em `src/` |

**Checks:** web #7 todos verdes. api #8 todos verdes, exceto o GitGuardian (I-1); o commit deste relatório só altera documentação.

## H. Execução local

```bash
# pastas lado a lado: ignis-orbital-api/ e ignis-fire-watch/, ambas em feat/ignis-human-validation
cd ignis-orbital-api
bash deploy/local/validate.sh up            # tudo: banco, IBGE, API, web, contas, ingestão INPE
bash deploy/local/validate.sh credentials   # contas locais
# abra http://localhost:8080
bash deploy/local/validate.sh ingest        # reprocessar (não duplica)
bash deploy/local/validate.sh e2e           # 18 testes Playwright (antes: npm ci + npx playwright install chromium no web)
bash deploy/local/validate.sh reset         # apaga só o volume desta pilha
```

Opcional: `export NASA_FIRMS_MAP_KEY=...` antes do `up` ou do `ingest` ativa a FIRMS.

## I. Pendências reais

| # | Prioridade | Pendência | Impacto | Dono |
|---|---|---|---|---|
| I-1 | P0 administrativo | Marcar no painel do GitGuardian os 5 alertas do commit `8883c0c` (incidentes 39541748 a 39541751) como falso positivo: interpolação `${…}` e prefixos de senha gerada, sem nenhum valor secreto. O código atual já não tem o padrão, e o histórico não foi reescrito | O check do PR #8 continua vermelho até a marcação | Proprietário |
| I-2 | P0 operacional | Homologar a NASA FIRMS com chave real (H-27/H-28) | O mapa só tem INPE sem a chave | Proprietário (chave) |
| I-3 | P1 | Rate limit e cache compartilhados antes de mais de 1 réplica (RS-1) | Proteção contra abuso | Engenharia |
| I-4 | P1 | E2E dos fluxos de incidente (denúncia → validação → incidente → protocolo) com dados criados no próprio teste | Cobertura da Sala de Crise | Engenharia |
| I-5 | P2 | Base oficial de unidades de conservação (CNUC/ICMBio, SEMA-CE) | Camada de UC segue indisponível | Engenharia + fonte oficial |
| I-6 | P2 | Provedor institucional de tiles (RS-3) | Uso público amplo | Proprietário |
| I-7 | P2 | Correlação FIRMS × INPE com metodologia documentada | Leitura de focos duplicados entre fontes | Engenharia |
| I-8 | — | Merges na ordem: api #3 → #5 → #6 → #7 → #8; web #4 → #6 → #7. Depois, as variáveis `IGNIS_API_REF`/`IGNIS_WEB_REF` da CI passam a apontar para as branches principais | Nada do trabalho está nas branches principais | Proprietário |

## J. Avaliação final

### READY FOR HUMAN VALIDATION

**Os fluxos P0 estão completos e reproduzíveis:**
- leitura do PostGIS, malha oficial, mapa, painel sem números inventados e integração ponta a ponta;
- pilha local com um comando;
- E2E automatizado contra a API e o PostGIS reais, verde local e na CI;
- documentação de validação.

**Ressalvas, todas registradas acima, nenhuma das quais impede a jornada do avaliador:**
1. **NASA FIRMS não homologada:** a fonte aparece corretamente como desabilitada, e o INPE fornece dados reais.
2. **GitGuardian vermelho no PR #8:** depende de uma marcação administrativa de falsos positivos já corrigidos no código.
3. **Escopo:** o IGNIS segue um **protótipo para validação supervisionada**, não um sistema operacional.
