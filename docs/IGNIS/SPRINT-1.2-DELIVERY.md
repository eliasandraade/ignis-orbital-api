# IGNIS — Sprint 1.2: ingestão real NASA FIRMS e INPE (entrega)

Data: 04/11/2026.
- **Branch:** `feat/sprint-1.2-real-ingestion`, criada a partir de `feat/sprint-1.1-geo-foundation` (`bd45b6c`).
- **PR:** empilhada sobre a da Sprint 1.1.
- **Não houve:** merge, deploy, provisionamento, banco operacional, nem uso de credencial real.

## 1. Resultado

| Entrega | Onde |
|---|---|
| Adaptador NASA FIRMS: VIIRS SNPP/NOAA-20/NOAA-21 NRT e MODIS NRT | `app/orbital/providers/firms.py` |
| Adaptador INPE: CSV diário oficial, com requisição condicional por ETag | `app/orbital/providers/inpe.py` |
| HTTP comum: retries com backoff, `Retry-After`, espaçamento entre requisições, erros só por código, filtro de segredos | `app/orbital/providers/_http.py` |
| Rodada completa: buscar → validar → normalizar → município → persistir → métricas → finalizar | `app/orbital/ingestion.py` |
| Recuperação por *lease*, não por relógio | `app/orbital/repository.py` (`acquire_lease`, `recover_abandoned_runs`) |
| Migration `a014`: confiança e brilho por sensor, id do provedor | `alembic/versions/a014_detection_provenance.py` |
| Worker agendado (`python -m app.orbital.worker`, papel `ingest`) | `app/orbital/worker.py`, `scripts/entrypoint.sh` |
| Cron do Railway pronto e **desligado** | `.railway/railway.ts` (`ENABLE_ORBITAL_INGEST_JOB = false`, `orbital-ingest`, `*/15`) |
| `POST /orbital-alerts/ingest` (admin) → 202 com as execuções reais; `GET /ingestion-runs[/{id}]` | `app/integrations/orbital_alerts_router.py`, `app/orbital/schemas.py` |
| Fixtures reais e públicas, com proveniência | `tests/fixtures/orbital/` |

## 2. Provedores e produtos

### 2.1 NASA FIRMS: API de área (CSV)

`GET {base}/area/csv/{MAP_KEY}/{SOURCE}/{oeste,sul,leste,norte}/{DAY_RANGE}/{DATE}`. A resposta traz os dados de `DATE` até `DATE + DAY_RANGE − 1`, com `DAY_RANGE` de 1 a 5 ([documentação da API de área](https://firms.modaps.eosdis.nasa.gov/api/area/)).

| Produto | Satélite (código → nome) | Confiança | Brilho | FRP |
|---|---|---|---|---|
| `VIIRS_SNPP_NRT` | `N` → Suomi NPP | classe `low/nominal/high` (`l/n/h` aceitos) | `bright_ti4`, canal **I-4** (K) | MW |
| `VIIRS_NOAA20_NRT` | `N20` → NOAA-20 | idem | idem | MW |
| `VIIRS_NOAA21_NRT` | `N21` → NOAA-21 | idem | idem | MW |
| `MODIS_NRT` | `T`/`A` (ou `Terra`/`Aqua`) → Terra/Aqua | **0–100 %**, gravado em `confidence_pct` | `brightness`, canais **21/22** (K) | MW |

Os significados seguem a [tabela oficial de atributos da FIRMS](https://earthdata.nasa.gov/data/tools/firms/active-fire-data-attributes-modis-viirs).

**Nada é equiparado entre sensores:**
- A FIRMS não publica limites de classe para a confiança do MODIS, então ela nunca é convertida em `low/nominal/high`.
- O brilho guarda o canal de origem (`brightness_channel`). Um CHECK no banco proíbe brilho sem canal e confiança de dois tipos ao mesmo tempo.
- `scan`, `track`, `version`, `bright_ti5`/`bright_t31` e o resto da linha ficam em `raw`, sem alteração.

Observação: a página da FIRMS diz que o Suomi NPP "não entrega mais dados novos", mas o arquivo público de 24 h ainda trazia 851 focos em 04/11/2026. O produto foi mantido; ele simplesmente devolve o que existir.

**Comportamento em falhas:**

| Situação | Resultado |
|---|---|
| Sem `NASA_FIRMS_MAP_KEY` | `disabled` / `missing_api_key`, **sem nenhuma requisição** e sem mock |
| Chave recusada (observado em 04/11/2026: HTTP 400 `Invalid MAP_KEY.`) | `unavailable` / `auth_rejected` |
| HTTP 429 | até 3 tentativas, respeitando `Retry-After` (limite de 60 s); depois `rate_limited` |
| HTTP 5xx, timeout, conexão | até 3 tentativas com backoff de 2 s e 4 s; depois `http_5xx`, `timeout` ou `connection_error` |
| HTTP 200 com corpo que não é CSV (HTML, texto, colunas faltando) | `unavailable` / `invalid_csv`. **Nunca vira "zero focos"** |
| Linha inválida (satélite de outro produto, hora inexistente, coordenada não numérica, confiança fora do domínio, número de campos errado) | contada em `records_rejected`; o resto do arquivo segue |

### 2.2 INPE Programa Queimadas: CSV diário

`GET https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/diario/Brasil/focos_diario_br_AAAAMMDD.csv`, um arquivo por dia UTC da janela.

**Por que o CSV e não o WFS** (comparação feita em 04/11/2026):

| Critério | CSV diário | WFS TerraBrasilis |
|---|---|---|
| Documentação | É o produto listado na página de dados abertos do INPE (10 min, diário, mensal, anual) | Não aparece na página de dados abertos |
| Estabilidade | URLs datadas no mesmo servidor | A camada usada pelo PR #2 (`ams1h:active-fire-today`) **não existe mais** (`Feature type … unknown`) |
| Rastreabilidade | Nome do arquivo + `ETag` + `Last-Modified` + SHA-256 por execução | Resposta sem identidade de versão |
| Identificador do foco | `id` (UUID) | `foco_id`, o **mesmo UUID** |
| Filtro espacial | No cliente (o arquivo cobre o Brasil) | No servidor |
| Volume | 2,1 MB em 03/11/2026. O ETag evita baixar de novo um arquivo que não mudou | Pequeno |

**Formato aceito.** As colunas obrigatórias são `id, lat, lon, data_hora_gmt, satelite`. As demais (município, estado, bioma, `frp`, risco de fogo…) ficam em `raw`.
- **Coordenadas:** com espaços à esquerda, como o INPE publica.
- **Horário:** `AAAA-MM-DD HH:MM:SS`, em GMT.
- **Instrumento:** vem de uma tabela explícita por satélite (MODIS, VIIRS, ABI, AVHRR, SEVIRI). Satélite desconhecido é gravado como `UNSPECIFIED`; o sensor não é adivinhado.
- **Campos sem documentação de unidade:** o INPE não publica confiança nem brilho neste arquivo, e não documenta a unidade do `frp`. Por isso `confidence`, `brightness_k` e `frp_mw` ficam vazios, e o valor original fica em `raw`.

**Falhas:**

| Situação | Resultado |
|---|---|
| `INPE_QUEIMADAS_ENABLED=false` | `disabled`, sem requisição |
| Arquivo inalterado | `304`; nada é baixado nem regravado. O ETag só é usado a partir de uma execução `ok` |
| Arquivo do dia corrente ainda não existe | 404 tolerado, porque ele é criado ao longo do dia |
| Arquivo de dia passado 404 ou 5xx, timeout, conexão | `unavailable` com o código |
| CSV sem as colunas, HTML ou bytes que não são UTF-8 | `unavailable` / `invalid_csv` |
| Linha inválida | `records_rejected` |
| Linha fora do envelope do CE | Não entra na execução; registrada em `params.provenance.files[].rows_outside_bbox` |

## 3. Pipeline, deduplicação e concorrência

- **Município pelo polígono oficial:** a atribuição continua no `INSERT` por `ST_Covers` sobre a malha IBGE 2025.
- **Fora do Ceará:** o registro não é gravado e entra em `records_out_of_scope`.
- **Contadores:** o banco garante `fetched = valid + rejected` e `valid = inserted + duplicate + out_of_scope`.
- **Deduplicação:** a chave UUIDv5 é formada por (fonte, satélite, instante UTC em segundos, lat/lon com 4 casas). Testes cobrem a estabilidade da chave:
  - `-3.12485` e `-3.124850` geram a mesma chave;
  - `acq_time` `412` e `0412` geram a mesma chave;
  - `nominal` e `n`, `2.0NRT` e `2.0URT` não mudam a identidade.
- **Gravação em ordem de `dedup_key`:** a ordem da Sprint 1.1 foi mantida e continua evitando deadlocks.
- **Uma execução ativa por (fonte, produto):** garantido pelo índice parcial da Sprint 1.1. Uma rodada concorrente recebe `skipped_active` e não cria execução.

**Sem transação durante HTTP.** Cada rodada usa uma conexão dedicada.
- Cada execução segura um *advisory lock* de sessão com chave derivada do seu id (o *lease*).
- As transações são curtas: criar a execução, cada lote, finalizar.
- Durante a chamada à NASA/INPE, a conexão fica `idle`, e não `idle in transaction`. Um teste verifica isso no `pg_stat_activity` durante o fetch.

**Recuperação confiável**, sem prazo arbitrário. Uma execução só é considerada abandonada se o seu *lease* puder ser adquirido, ou seja, se nenhuma conexão viva o segura. O PostgreSQL libera o lock quando o processo dono encerra, morre (SIGKILL), ou quando o servidor derruba a conexão. A próxima rodada recupera essas execuções como `error`/`abandoned`, mantendo intactos os contadores do que foi gravado.

| Cenário (testado) | Resultado |
|---|---|
| Execução viva iniciada "há 2 dias" | **Não** é recuperada |
| Processo filho morto com SIGKILL/TerminateProcess durante o fetch | Outra rodada recebe `skipped_active` enquanto ele vive; depois da morte, a execução é recuperada como `abandoned` e a rodada seguinte roda normalmente |
| Conexão do dono derrubada (`pg_terminate_backend`) | A rodada reconecta e registra `error`/`internal_error`. Nada fica `running` |
| Timeout do produto (`INGEST_PRODUCT_TIMEOUT_SECONDS`) | `error`/`timeout`, ou `partial` se já havia lote gravado; *lease* liberado |
| Rodada cancelada (SIGTERM/SIGINT ou timeout da rodada) | Execução corrente e pendentes fechadas como `error`/`interrupted`; worker sai com 143 (sinal) ou 1 (timeout) |
| Falha no 2º lote | `partial`, com os contadores exatamente iguais ao 1º lote gravado |

**Observações semelhantes entre provedores.** Um mesmo foco visto pelo NOAA-20 na FIRMS e pelo NOAA-20 no INPE gera **dois registros**, cada um com sua fonte, porque a fonte entra na chave. Nenhum dado original é apagado.

**Sem agrupamento nesta sprint.** Não implementei agrupamento espacial ou temporal (`cluster_id`). Fazer isso exige metodologia e teste de precisão próprios; ficou como pendência S1.2-P4.

**Incidentes:** nenhum incidente é criado a partir de uma detecção.

## 4. Worker e Railway

- **Execução:** `python -m app.orbital.worker [--source firms|inpe] [--window-hours N]` faz uma rodada e termina.
- **Códigos de saída:**
  - 0: tudo `ok`, `disabled` ou `skipped_active`;
  - 2: provedor `unavailable` ou execução `partial`;
  - 1: timeout ou erro interno;
  - 3: configuração inválida;
  - 143: sinal.
- **Saída:** uma linha JSON por rodada, sem URL, sem chave.
- **Janela padrão:** 26 h (`INGEST_WINDOW_HOURS`). A sobreposição com a rodada anterior não custa nada por causa da deduplicação.
- **Timeout:** 780 s por rodada, abaixo dos 15 min do cron.
- **No Railway:** o serviço `orbital-ingest` está descrito em `ingestJob()` (mesma imagem, `entrypoint.sh ingest`, cron `*/15 * * * *`, `restartPolicyType NEVER`, *Wait for CI*). Ele fica atrás de `ENABLE_ORBITAL_INGEST_JOB = false`.
- **Checagens na CI:** o contrato do IaC verifica o job mesmo desligado (2 checagens novas, 22 no total) e falha se a flag for ligada sem revisão.

**Credenciais.** A `MAP_KEY` só existe na URL da requisição.
- Os erros carregam apenas códigos e não encadeiam a exceção do httpx, cujo texto contém a URL.
- Os loggers `httpx`/`httpcore` ficam em WARNING.
- O worker aplica um filtro que mascara o valor da chave em qualquer log.
- Testes procuram a chave falsa em proveniência, códigos, `repr` do resultado, logs DEBUG, stdout/stderr do worker e `ingestion_runs.params`.

## 5. API administrativa

- **`POST /api/v1/orbital-alerts/ingest`** (admin; corpo opcional `{"sources": ["firms", "inpe"]}`) responde **202** com `round_id` e as execuções reais (`run_id`, `running`) já gravadas.
  - O processamento continua em segundo plano.
  - A resposta **não afirma nenhum resultado**: o estado verificável está em `GET /api/v1/orbital-alerts/ingestion-runs/{run_id}` (e na listagem `/ingestion-runs`), ambos só para admin.
  - Se todos os produtos já estão rodando em outro processo, a resposta é `nothing_started`, com `skipped_active`.
  - A auditoria `orbital_ingest.requested` registra o `user_id` do solicitante, o `round_id` e as execuções. Cada execução guarda `triggered_by_user_id`.
- **Escopo:** `GET /api/v1/orbital-alerts`, que é público, **não** inicia ingestão (teste dedicado). Ele continua lendo a FIRMS com cache como na Sprint 0 e passa a ler o banco na Sprint 1.3 (risco R-S12-2).
- **Código removido:** o caminho antigo `ingest_viirs` (cache em memória, `processed_not_persisted`) saiu.

## 6. Evidências

### 6.1 Acesso real às fontes públicas (sem credencial)

| Verificação | Resultado |
|---|---|
| INPE CSV diário (04/11/2026 ~03:30 UTC) | 200; arquivo `focos_diario_br_20261103.csv` com 2.129.985 bytes, `ETag "208041-65f6aa5237380"` e 14.516 focos |
| INPE WFS, camada do PR #2 | `ServiceException … Feature type ams1h:active-fire-today unknown` |
| INPE WFS, camada atual `dados_abertos:focos_48h_br_todosats` | 200, GeoJSON com `foco_id` igual ao `id` do CSV |
| FIRMS API com chave inválida | HTTP 400, corpo `Invalid MAP_KEY.` |
| FIRMS arquivos públicos de 24 h (sem chave) | 200 nos 4 produtos; mesmas colunas da API, sem `instrument` |

**Ponta a ponta real, só do INPE.** Imagem Docker `ignis-orbital-api:s12`, banco PostGIS isolado e descartável, papel `migrate` seguido do papel `ingest`, com `APP_ENV=staging` e sem chave FIRMS:

| Rodada | Resultado |
|---|---|
| 1ª (04:00:35 UTC) | FIRMS: 4 execuções `disabled`/`missing_api_key`. INPE: `ok`, 2 arquivos (`…20261103.csv`: 14.516 linhas, 14.018 fora do envelope; `…20261104.csv`: 573 linhas, todas fora), `fetched 498`, `out_of_scope 215`, **`inserted 283`**. Exit 0 |
| 2ª (04:00:48 UTC) | INPE: os dois arquivos responderam **304**; `inserted 0`. Exit 0 |

**Focos gravados por município.** Os 283 focos ficaram distribuídos por municípios do CE: Santana do Cariri 13, Monsenhor Tabosa 12, Várzea Alegre 12, Mauriti 11, Coreaú 11, entre outros.

**Satélites.** NOAA-20 (107), NOAA-21 (75), AQUA_M-T (50), GOES-19 (19), TERRA_M-M (11), METOP-B (9), TERRA_M-T (7), METOP-C (4), MSG-03 (1).

> **NASA FIRMS não foi validada ponta a ponta.** Nenhuma chave real foi usada.
>
> O que foi validado:
> - o formato real, por fixtures dos arquivos públicos;
> - a resposta real a uma chave inválida;
> - todo o processamento com transporte simulado.
>
> A validação com chave fica para a homologação (H-27).

### 6.2 Testes e CI (local, PostGIS 16-3.4 descartável)

| Verificação | Resultado |
|---|---|
| Suíte completa | **381 testes passando**, cobertura **84,05%**. Módulos novos entre 88% e 96% |
| Testes da sprint | 47 de provedores e contrato (sem banco); 27 de integração PostGIS (rodadas, recuperação, concorrência, endpoint, worker); 2 de contrato da API |
| Migrations | `upgrade head` termina em `a014`. `downgrade` e `upgrade` foram cobertos pelo teste de migration da Sprint 1.1 (agora até `a014`). Esquema igual aos modelos nas tabelas da Fase 1 |
| Ruff | sem apontamentos |
| actionlint 1.7.7 (`ci.yml`, `promote.yml`, com shellcheck) | sem apontamentos |
| IaC (`tsc` + contrato) | 22 checagens |
| Docker | imagem construída; papéis `migrate` e `ingest` executados contra o banco isolado (6.1) |
| Medição de cobertura | corrigida: `concurrency = ["thread", "greenlet"]`. Sem isso, o coverage perdia as linhas executadas depois de cada chamada ao banco (o roteador aparecia com 70% mesmo com os testes passando) |

## 7. Correção documental: Nota Metodológica do IBGE

O documento oficial é o **id 2102268** da Biblioteca do IBGE. A referência anterior ao id 2102169 estava errada.

| Campo | Valor |
|---|---|
| Título | *Malha Municipal Digital e Áreas Territoriais 2025: nota metodológica 01/2026, Informações técnicas e legais para a utilização dos dados publicados* |
| Edição | IBGE, 2026, 47 p., Coleção Ibgeana |
| PDF | `liv102268.pdf`, SHA-256 `bc88c44624c8852b4796b72b525f9092cd770415403c1a3486a8d48bcefc9e89`, verificado em 04/11/2026 |
| Conteúdo pertinente | Cobre as atualizações de limites comunicadas pelos estados "entre 1 de maio de 2024 e 30 de abril de 2025", o que confirma a data de referência registrada. O sistema de referência é o SIRGAS2000 (EPSG 4674) |

O manifesto da malha e o relatório da Sprint 1.1 foram corrigidos.

## 8. Riscos

| # | Risco | Mitigação |
|---|---|---|
| R-S12-1 | A FIRMS não foi exercitada com chave real (formato da API com chave e cota) | H-27 em staging com uma chave própria de staging |
| R-S12-2 | `GET /orbital-alerts` público ainda consulta a FIRMS com a mesma chave (cache de 60 min, backoff de falha de 5 min) e consome a cota | Sprint 1.3: leitura do banco |
| R-S12-3 | O CSV diário do INPE cobre o Brasil; na temporada, os arquivos ficam maiores | O ETag evita baixar arquivo inalterado. Medir em staging; se necessário, usar os arquivos de 10 min |
| R-S12-4 | Unidade do `frp` do INPE não documentada | Mantido só em `raw` até haver documentação oficial |
| R-S12-5 | Tabela satélite → instrumento do INPE é manual | Satélite novo vira `UNSPECIFIED`, sem palpite; revisar a tabela quando aparecer |
| R-S12-6 | Termos de uso e atribuição do INPE não estão publicados na página de dados abertos | Confirmar com o INPE antes da exibição pública (Sprint 1.3) |

## 9. Pendências

| # | Item | Dono |
|---|---|---|
| S1.2-P1 | Chaves FIRMS distintas para staging e produção (seladas no Railway) | Proprietário |
| S1.2-P2 | Autorizar a homologação: ligar `ENABLE_ORBITAL_INGEST_JOB` em staging (`railway config plan/apply`) | Proprietário |
| S1.2-P3 | Leitura do banco em `GET /orbital-alerts` e o mapa (Sprint 1.3) | Aguarda autorização |
| S1.2-P4 | Correlação FIRMS × INPE (`cluster_id`) com metodologia e teste de precisão | Backlog (opcional) |
| S1.2-P5 | Fechar o PR #2 com referência a este PR (nada dele foi reaproveitado: camada WFS inexistente, horário `now()` como fallback, confiança fixa 70 rotulada como "confirmada", fallback demonstrativo) | Proprietário |

## 10. Homologação em staging (após autorização)

1. Merge dos PRs na ordem #3 → #5 → #6 (Sprint 1.1) → Sprint 1.2. O deploy de staging roda `migrate`, que aplica `a014`.
2. Gravar `NASA_FIRMS_MAP_KEY` de staging, selada, no serviço `api`.
3. **H-27:**
   ```
   railway ssh --service api
   python -m app.orbital.worker --window-hours 26
   ```
   Esperado:
   - exit 0;
   - 5 execuções `ok`;
   - `records_inserted > 0` na FIRMS;
   - a chave não aparece na saída.
4. **H-28:** repetir o comando. Esperado: `records_inserted = 0` em todas as execuções; o INPE responde `304` ou reprocessa sem inserir.
5. **H-29:** com o token de admin, chamar `POST $API/api/v1/orbital-alerts/ingest`. Esperado:
   - 202 com `run_id`;
   - `GET …/ingestion-runs/{id}` termina com estado final;
   - `audit_logs` tem `orbital_ingest.requested` com o seu `user_id`.
6. **H-30:** ligar `ENABLE_ORBITAL_INGEST_JOB=true` só no IaC de staging, rodar `railway config plan` e depois `apply`. Acompanhar 48 h. Esperado: nenhuma execução `error`, e nenhuma `running` com mais de 15 min.
7. **H-31:** derrubar o worker no meio de uma rodada (*Restart* do serviço). Esperado: a rodada seguinte registra a recuperação `abandoned` no log e roda normalmente.
