# IGNIS — Sprint 1.1: fundação geoespacial (entrega)

Data: 03/11/2026. Branch `feat/sprint-1.1-geo-foundation`, empilhada sobre `infra/railway-only` (PR #5).
Escopo autorizado pelo proprietário: tabelas, malha oficial do IBGE, importador, contratos de ingestão e testes.
**Fora do escopo:** workers FIRMS/INPE (Sprint 1.2), merge, deploy e qualquer recurso no Railway.

## 1. Resultado

| Entrega | Onde |
|---|---|
| Migration reversível `a013` (4 tabelas, constraints, índices GiST) | `alembic/versions/a013_geo_foundation.py` |
| Modelos | `app/geo/model.py`, `app/orbital/model.py` |
| Malha oficial do IBGE versionada, com manifesto e SHA-256 | `data/reference/ibge/malha_municipal_2025/` |
| Importador idempotente, auditável e fail-closed | `app/geo/ibge_import.py`; CLI `python -m seed.jurisdictions` |
| Importação automática no pre-deploy (papel `migrate`) | `scripts/entrypoint.sh` |
| Contratos para os provedores FIRMS/INPE | `app/orbital/contracts.py` |
| Único caminho de escrita de detecções e execuções | `app/orbital/repository.py` |
| Testes: 29 unitários + 33 de integração com PostGIS real (311 na suíte toda) | `tests/test_geo_foundation_unit.py`, `tests/test_postgis_geo_foundation.py` |
| CI: PostGIS no job de cobertura; importação e contagem no job de migrations; malha conferida dentro da imagem | `.github/workflows/ci.yml` |

## 2. Fonte oficial

| Campo | Valor |
|---|---|
| Produto | IBGE, **Malha Municipal Digital**, versão **2025** (a mais recente publicada) |
| Data de referência | **30/04/2025**: quadro territorial vigente nessa data, conforme a página de Áreas dos Municípios do IBGE |
| Arquivos | `CE_Municipios_2025.zip` (3.410.139 bytes, SHA-256 `969c8b92…df8f526fd2d66`); `CE_UF_2025.zip` (121.027 bytes, SHA-256 `e71b3df6…f87e780aab`). Data dos dois no geoftp: 26/02/2026 |
| URL | `https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/municipio_2025/UFs/CE/` |
| Sistema de referência | SIRGAS 2000 (EPSG:4674), verificado no `.prj`; convertido no banco para WGS 84 (EPSG:4326) com `ST_Transform` |
| Codificação | UTF-8 (`.cpg`); nomes acentuados conferidos (Senador Sá, Graça, Ceará) |
| Ressalva legal | O IBGE não define nem demarca limites: a malha tem finalidade estatística. Litígios de divisa, como o CE × PI, seguem a linha publicada pelo IBGE, e não uma decisão do IGNIS |

**Decisão S1.1-D1:** o plano citava a malha de 2022. Adotamos a de **2025**, a última publicada, porque reflete os limites vigentes. A troca de versão no futuro é só um novo diretório com manifesto, e o importador registra um novo `reference_dataset`.

**Decisão S1.1-D2:** os zips oficiais são **versionados no repositório sem nenhuma alteração** (3,4 MB).
- Alternativa descartada: baixar na hora da importação.
  - O deploy passaria a depender da disponibilidade do geoftp.
  - O resultado poderia mudar sem aviso.
- O manifesto guarda URL, tamanho e SHA-256. Um arquivo diferente é recusado antes de qualquer leitura.

## 3. Estrutura das tabelas

### `reference_datasets`
Proveniência de cada conjunto oficial importado.
- Uma linha por conjunto de arquivos, identificada por `content_sha256`, o SHA-256 dos pares nome:hash.
- Guarda: `source`, `product`, `version`, `reference_date`, `source_crs`, `files` (jsonb com URL, SHA-256 e bytes), `feature_count`, `license_note`, `importer_version` e `imported_at` (timestamptz).

### `jurisdictions`
| Coluna | Tipo | Regra |
|---|---|---|
| `id` | uuid | `gen_random_uuid()` |
| `level` | varchar(16) | `state` \| `municipality` |
| `ibge_code` | varchar(7) | **único**: 2 dígitos para a UF e 7 para o município (CHECK por nível) |
| `name` | varchar(255) | nome oficial |
| `state_ibge_code`, `state_abbreviation` | varchar(2) | CHECK `left(ibge_code,2) = state_ibge_code` |
| `parent_id` | uuid FK → `jurisdictions` | **RESTRICT**. Obrigatório para município; nulo para a UF |
| `official_area_km2` | numeric(12,3) | `AREA_KM2` publicado pelo IBGE; > 0 |
| `geom` | geometry(MultiPolygon, **4326**) | CHECK `ST_IsValid AND NOT ST_IsEmpty`; índice **GiST** |
| `dataset_id` | uuid FK → `reference_datasets` | **RESTRICT** |
| `source_attributes` | jsonb | registro do DBF **sem nenhuma alteração** (CD_RGI, CD_RGINT etc.) |
| `created_at`, `updated_at` | timestamptz | |

### `ingestion_runs`
Uma execução por (fonte, produto).
- `source`: `NASA_FIRMS` \| `INPE_QUEIMADAS`.
- `product`, mais `trigger` (`schedule` \| `manual`) e `triggered_by_user_id` (FK users, SET NULL).
- `status`: `running|ok|partial|unavailable|disabled|error`.
- Timestamps, todos timestamptz: `started_at`, `finished_at`, `window_start/end`.
- `error_code` e `error_message` (500 caracteres, sem segredos).
- `params` (jsonb).

**Contadores:** `fetched`, `valid`, `rejected`, `out_of_scope`, `inserted`, `duplicate`. As constraints garantem a contabilidade:
- `records_fetched = valid + rejected`;
- `records_valid = inserted + duplicate + out_of_scope`;
- todos ≥ 0;
- `finished_at` é preenchido se, e somente se, o status for final;
- a janela é ordenada.

**Guarda de concorrência:** o índice único parcial `uq_ingestion_runs_one_running (source, product) WHERE status='running'` impede duas execuções sobrepostas, entre processos e réplicas.

### `orbital_detections`
Foco de calor, não incêndio confirmado.
- **Identificação:** `dedup_key` uuid **único** (UUIDv5 de fonte, satélite, instante UTC em segundos e lat/lon com 4 casas).
- **Origem e instante:** `source`, `product`, `satellite`, `instrument` e `observed_at` (timestamptz).
- **Posição:** `location` geometry(Point, **4326**) com CHECK de validade e de faixa lat/lon, e índice **GiST**.
- **Atributos do foco:** `confidence` (`low|nominal|high`), `frp_mw` (≥ 0), `brightness_k` (> 0) e `daynight` (`D|N`).
- **Vínculos:**
  - `jurisdiction_id`: FK RESTRICT, **obrigatório**;
  - `ingestion_run_id`: FK RESTRICT, a execução que gravou o registro primeiro.
- **Registro bruto e ingestão:** `raw` (jsonb) e `ingested_at`.
- **Índices:** `observed_at`; `(source, observed_at)`; `(jurisdiction_id, observed_at)`; `ingestion_run_id`.

## 4. Garantias e decisões

- **Contadores refletem o que foi gravado.**
  - `persist_batch` grava o lote com `INSERT … ON CONFLICT (dedup_key) DO NOTHING RETURNING` e atualiza os contadores da execução na **mesma transação**.
  - `inserted` vem do `RETURNING`. A cada commit, `records_inserted = count(*) WHERE ingestion_run_id = run` (verificado em teste, inclusive sob concorrência).
- **Recorte pelo polígono oficial.**
  - O município é atribuído no banco por `ST_Covers`. Um ponto na divisa fica com o menor código IBGE, para ser determinístico.
  - Fora dos 184 municípios (outro estado, mar), o registro não é gravado e conta como `out_of_scope`.
  - O bbox só limita a consulta ao provedor.
- **Deadlock encontrado e corrigido.** O teste de concorrência expôs um *deadlock* real:
  - dois gravadores com lotes sobrepostos em ordens diferentes travavam o índice único;
  - correção: os lotes são inseridos em ordem de `dedup_key`, uma ordem global de locks;
  - o teste força a sobreposição (trigger de teste com `pg_sleep`): **sem a correção falha 3/3, com a correção passa 9/9**.
- **Importação concorrente.** Duas importações simultâneas se serializam por `pg_advisory_xact_lock`. Uma grava 185 linhas; a outra encontra tudo e não altera nada (teste).
- **Idempotência e correção de deriva.**
  - O UPSERT só reescreve a linha se algum campo ou a geometria (`ST_OrderingEquals`) mudou.
  - Uma linha adulterada no banco é restaurada na reexecução (`updated=1`, teste). Os `id` nunca mudam.
  - Município ausente de uma malha nova é **reportado, não apagado**, porque detecções o referenciam.
- **Fail-closed.** O importador aborta a transação inteira se:
  - o hash não confere;
  - o CRS não é SIRGAS 2000;
  - a contagem não é 184;
  - há código repetido ou fora da UF;
  - a `SIGLA_UF` diverge;
  - a geometria é inválida.
  Nenhuma geometria é "consertada" (`ST_MakeValid` não é usado). Na malha 2025 do CE, as 185 geometrias são válidas na origem.
- **Auditoria:** cada execução grava `audit_logs` com a ação `jurisdictions.imported` (dataset, hash e contagens).
- **Sem dados demonstrativos:**
  - os focos não são ligados a `protected_areas`, cujos polígonos atuais são demonstrativos ("base demonstrativa acadêmica");
  - o vínculo com UC fica para quando houver a base oficial (CNUC/ICMBio, SEMA-CE).
- **Contratos (sem workers):**
  - `DetectionProvider.fetch(product, window, bbox) → ProviderResult`;
  - `NormalizedDetection` valida fuso, faixas e enums;
  - um resultado sem sucesso não pode carregar detecções;
  - o worker (papel `ingest` no entrypoint e o job `orbital-ingest` do Railway) foi entregue na Sprint 1.2.
- **Ambientes:** `python -m seed.jurisdictions` roda em **todos** os ambientes, staging e production inclusive. São dados oficiais, ao contrário do seed demo, que continua bloqueado. Ele roda no pre-deploy logo após `alembic upgrade head`.

## 5. Evidências

**Testes locais:** Windows, PostGIS 16-3.4 em contêiner descartável, porta 55432, senha local de uso único.

| Verificação | Resultado |
|---|---|
| `alembic upgrade head` → `downgrade 438a82832b4f` → `upgrade head` | ok (também no teste `test_migration_upgrade_downgrade_upgrade`) |
| Esquema × modelos (equivalente a `alembic check` nas 4 tabelas) | sem diferença. O teste de mutação (índice renomeado no modelo) falha, como esperado |
| `python -m seed.jurisdictions` (1ª execução) | `inseridas 185` (184 municípios + UF) |
| `python -m seed.jurisdictions` (2ª execução) | `inseridas 0, atualizadas 0, sem alteração 185` |
| Contagem por nível | `municipality 184`, `state 1`; todas `ST_IsValid`, SRID 4326 |
| Soma das áreas oficiais | municípios 148.894,433 km² × UF 148.894,440 km² |
| União dos 184 municípios × polígono da UF | diferença simétrica **0,000 km²** |
| Ponto da Praça do Ferreira | Fortaleza (2304400); Teresina-PI → nenhum município |
| Imagem Docker: `seed.jurisdictions --verify-files` | arquivos conferem (SHA-256 do conjunto `b12b2f26…a4eff`) |
| Imagem Docker: papel `migrate` com `APP_ENV=staging`, 2× | 1ª: `inseridas 185`; 2ª: `sem alteração 185`; `alembic_version = a013` |
| Suíte completa local (com PostGIS) | 311 testes passando; cobertura 81,8% (módulos novos: 98%) |
| CI do PR, run `41760828977` (commit `db8c4d6`) | todos os checks verdes: Ruff, Pytest (311 passando, 0 *skip*, cobertura 81,75%), Migrations (`a013 (head)`; 1ª importação `inseridas 185`, 2ª `sem alteração 185`; `{'municipality': 184, 'state': 1}`), Docker (malha conferida na imagem), IaC, pip-audit, lockfile, GitGuardian e SonarCloud (Quality Gate OK, 0 issues abertas) |
| 1ª execução do Sonar no PR | Quality Gate **falhou** (confiabilidade C, por uma asserção que comparava a mesma expressão) e acusou 16 *code smells*. Todos foram corrigidos em `db8c4d6`, sem mudar o comportamento |

## 6. Pendências

| # | Item | Dono |
|---|---|---|
| S1.1-P1 | `alembic check` global falha por **deriva anterior a esta sprint**: modelos antigos com `DateTime` sem fuso × migrations `timezone=True`; índices GiST antigos fora dos modelos; tabelas do schema `tiger`. A verificação desta sprint é restrita às 4 tabelas novas. Corrigir a deriva antiga é uma tarefa própria (B-13) | Backlog |
| S1.1-P2 | Base oficial de unidades de conservação (CNUC/ICMBio, SEMA-CE) para preencher o vínculo foco → UC | Fase 1 (antes da Sprint 1.3) |
| S1.1-P3 | Sprint 1.2: provedores FIRMS/INPE sobre estes contratos, papel `ingest`, job no Railway | **Entregue** (SPRINT-1.2-DELIVERY) |
| S1.1-P4 | Confirmar em staging, após o deploy autorizado, os itens H-25 e H-26 do checklist | Proprietário |
| S1.1-P5 | Ler a Nota Metodológica da MMD 2025 (Biblioteca do IBGE, **id 2102268**, nota metodológica 01/2026, `liv102268.pdf`; verificada na Sprint 1.2, ver SPRINT-1.2-DELIVERY §7) e registrar eventuais restrições adicionais de uso | Proprietário/jurídico |
