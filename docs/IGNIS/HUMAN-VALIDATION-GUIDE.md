# IGNIS — Guia de validação humana

Para quem vai avaliar o IGNIS num computador local, sem nenhum serviço de produção.
Tudo roda em contêineres isolados (projeto Docker `ignis-validation`), em 127.0.0.1.
Resultados já obtidos pela engenharia: [HUMAN-VALIDATION-RESULTS.md](HUMAN-VALIDATION-RESULTS.md). Estado geral: [READY-FOR-HUMAN-VALIDATION.md](READY-FOR-HUMAN-VALIDATION.md).

> **O que é e o que não é.** É um protótipo em validação supervisionada.
> - Focos de calor são anomalias térmicas vistas por satélite, **não incêndios confirmados**.
> - Não há integração com Corpo de Bombeiros, Defesa Civil ou qualquer órgão.
> - Nenhuma ação na interface notifica alguém fora do sistema.

## 1. Pré-requisitos

| Item | Versão testada | Observação |
|---|---|---|
| Docker Desktop (ou Docker Engine) com Compose v2 | 29.7 | ~6 GB livres para imagens e banco |
| Bash | Git Bash no Windows, bash no Linux/macOS | o script usa `bash`, `curl` e `head /dev/urandom` |
| Node.js | 22 | só para rodar os testes E2E |
| Repositórios lado a lado | `ignis-orbital-api` e `ignis-fire-watch` na mesma pasta | ou defina `IGNIS_WEB_DIR` |
| Branches | `feat/ignis-human-validation` nos dois repositórios | PRs [api#8](https://github.com/eliasandraade/ignis-orbital-api/pull/8) e [web#7](https://github.com/eliasandraade/ignis-fire-watch/pull/7) |
| Portas livres | 8000 (API), 8080 (web), 55432 (PostGIS) | presas a 127.0.0.1 |

Abra um **shell limpo**. O script se recusa a rodar se encontrar no ambiente:
- `DATABASE_URL`;
- qualquer variável `RAILWAY_*`;
- `APP_ENV=staging` ou `APP_ENV=production`.

## 2. Iniciar

```bash
cd ignis-orbital-api
bash deploy/local/validate.sh up
```

**O que acontece, em ordem:**
1. Na primeira execução, o script gera segredos aleatórios em `deploy/local/.validation.env` e `.validation-db-secret`. Os dois ficam fora do Git e são só desta máquina.
2. Constrói as imagens da API e da web.
3. Sobe o PostGIS 16-3.4, aplica as migrations e importa a malha oficial do IBGE 2025 (184 municípios do Ceará). A importação confere o SHA-256 dos arquivos.
4. Sobe a API (FastAPI) **sem dados demonstrativos** (`SKIP_DEMO_SEED=true`).
5. Cria três contas locais (admin, gestor, campo) com senhas aleatórias.
6. Faz uma rodada de ingestão **real** do INPE.
   - Se o servidor do INPE não responder, usa a amostra histórica documentada de 03/11/2026. Essa amostra fica marcada como `fixture` na interface.
   - A NASA FIRMS fica **desabilitada**, a menos que você exporte `NASA_FIRMS_MAP_KEY` antes.
7. Sobe a web (nginx) e confere a saúde dos serviços.

Ao final, o script imprime a situação das fontes, as contagens no banco e as credenciais locais. Para ver as credenciais de novo:

```bash
bash deploy/local/validate.sh credentials
```

Endereços: interface em <http://localhost:8080>, API em <http://localhost:8000/docs>.

## 3. Conferir que o banco certo está em uso

```bash
bash deploy/local/validate.sh status
```

Espere ver:
- `{"status":"ready","database":"connected"}`;
- `municípios=184`, além das detecções e execuções desta pilha;
- `banco=ignis_validation (container db da pilha ignis-validation)`.

**Proteções contra apontar para outro banco:**
- a API recebe a URL do banco montada pelo script, sempre para o serviço `db` desta pilha;
- o arquivo `deploy/local/compose.yml` não aceita outra origem: sem o script, ele se recusa a interpolar.

## 4. Jornada sugerida

| # | Passo | Onde | Resultado esperado |
|---|---|---|---|
| 1 | Abrir o portal público | <http://localhost:8080/public> | Painel "Monitoramento orbital — dados persistidos" com totais; glossário detecção × alerta × incidente × incêndio confirmado × simulação |
| 2 | Abrir o mapa público | Mapa | Ceará centralizado, contorno laranja do estado, limites municipais e focos rosa (INPE). NASA FIRMS "Desabilitada" |
| 3 | Escolher o intervalo do dado | Período → "Intervalo de datas…" → o dia mostrado em "Observação mais recente no banco" | A contagem muda para os focos desse dia |
| 4 | Filtrar por município | Município → um com contagem > 0 | Só focos desse município; o limite fica destacado |
| 5 | Abrir um foco | Clique na lista ou no ponto | Fonte, produto/satélite, horário observado e de ingestão (Fortaleza e UTC), município IBGE, coordenadas e aviso "não é incêndio confirmado". Confiança, FRP e brilho só aparecem quando o sensor os informa (o INPE não informa) |
| 6 | Entrar como gestor | <http://localhost:8080/login> | Painel do gestor com os mesmos indicadores reais. Os cartões de incidentes e equipes mostram 0: banco sem dados demonstrativos |
| 7 | Mapa do gestor | Menu "Mapa Orbital" | Igual ao público, mais o id da execução de ingestão e o registro original do provedor |
| 8 | Sala de Crise | `/gestor/war-room` | Sem incidente no banco: "Nenhum incidente crítico ativo" e nenhuma ação disponível. Com incidente criado por um operador, a ativação de protocolo pede confirmação, só grava no IGNIS e diz que nenhum órgão foi notificado |
| 9 | Área administrativa como gestor | `/admin` | "Acesso Restrito" |
| 10 | Sair | botão "Sair" | Volta ao login; recarregar `/gestor` exige login de novo |

## 5. Ingestão controlada

```bash
bash deploy/local/validate.sh ingest           # rodada real (INPE; FIRMS se houver chave)
bash deploy/local/validate.sh ingest-fixture   # amostra histórica do INPE, sem rede
```

- A saída é uma linha JSON por execução: `records_fetched`, `records_inserted`, `records_duplicate` e `records_out_of_scope` (fora do Ceará).
- **Reprocessar não duplica:**
  - na segunda rodada real, o INPE responde `304` (arquivo inalterado), e `inserted` dá 0;
  - com um arquivo novo, os focos já gravados contam como `duplicate`.
- Com uma chave real da NASA, `export NASA_FIRMS_MAP_KEY=...` antes de `ingest` ativa os 4 produtos FIRMS. A chave não aparece em logs nem na saída.
- A ingestão manual também existe pela API, só para admin: `POST /api/v1/orbital-alerts/ingest`. A resposta 202 traz o `run_id`, e o estado fica em `GET /api/v1/orbital-alerts/ingestion-runs/{run_id}`.

## 6. Simular falhas

| Cenário | Como | Esperado |
|---|---|---|
| API indisponível | `docker stop ignis-validation-api-1` e recarregue o mapa | "Falha ao consultar a API de focos" e nenhum foco desenhado. O painel diz que não há valores. Volte com `docker start ignis-validation-api-1` |
| Fonte desatualizada | Espere mais de 60 min sem ingerir, ou ajuste `ORBITAL_STALE_AFTER_MINUTES` | INPE "Desatualizada"; o horário da observação segue separado do horário da ingestão |
| Fonte sem chave | Padrão (sem `NASA_FIRMS_MAP_KEY`) | NASA FIRMS "Desabilitada", nunca "Atualizada" |
| Período sem focos | Intervalo de datas antigo (por exemplo, 01/01/2025) | Mensagem de vazio que explica se a ausência pode ou não ser afirmada |

## 7. Integridade dos dados

```bash
docker exec ignis-validation-db-1 psql -U ignis -d ignis_validation -c \
 "SELECT count(*) total, count(DISTINCT dedup_key) distintos FROM orbital_detections"
docker exec ignis-validation-db-1 psql -U ignis -d ignis_validation -c \
 "SELECT count(*) FROM orbital_detections d JOIN jurisdictions j ON j.id=d.jurisdiction_id
  WHERE NOT ST_Covers(j.geom, d.location)"
```

Esperado:
- `total = distintos`;
- 0 focos fora do município atribuído.

Para conferir a persistência, rode `stop` e depois `up`: as contagens devem ser as mesmas.

## 8. Testes automatizados

```bash
bash deploy/local/validate.sh e2e
```

- **O que roda:** 18 testes Playwright (16 em desktop e 2 em mobile) contra a pilha real.
- **Antes da primeira vez,** no repositório web: `npm ci` e depois `npx playwright install chromium`.
- **Relatório:** `ignis-fire-watch/playwright-report/index.html`.

Testes do backend (exigem um PostGIS de testes descartável, ver `tests/postgis.py`):

```bash
IGNIS_TEST_POSTGIS_URL=postgresql://ignis:<senha>@localhost:<porta>/postgres APP_ENV=test python -m pytest
```

## 9. Parar, reiniciar e limpar

```bash
bash deploy/local/validate.sh stop    # para, mantém os dados
bash deploy/local/validate.sh up      # sobe de novo (reaproveita banco e senhas)
bash deploy/local/validate.sh reset   # apaga SÓ o volume ignis-validation_pgdata e os segredos locais
```

## 10. Checklist de aceitação

| # | Critério | Resultado esperado | OK? | Observações do avaliador |
|---|---|---|---|---|
| A1 | Pilha sobe com `validate.sh up` | API e web "ok"; 184 municípios | ☐ | |
| A2 | Portal público abre sem login | Indicadores reais e glossário | ☐ | |
| A3 | Mapa mostra o Ceará e os limites oficiais | Contorno do estado e 184 municípios | ☐ | |
| A4 | Focos persistidos no mapa | Contagem igual a `/api/v1/orbital-alerts` | ☐ | |
| A5 | Filtros de período, município, fonte e satélite | Contagens coerentes | ☐ | |
| A6 | Detalhe do foco | Origem, horários, coordenadas, aviso | ☐ | |
| A7 | Situação das fontes | INPE com estado e horários; FIRMS desabilitada sem chave | ☐ | |
| A8 | Painel sem números inventados | Valores iguais à API; vazio ou erro explícitos | ☐ | |
| A9 | Login, logout, recarga da página | Sessão mantida ao recarregar; logout exige login | ☐ | |
| A10 | Bloqueios de acesso | `/admin` restrito ao admin; campo vai para Operação de Campo | ☐ | |
| A11 | Sala de Crise sem ações reais | Sem incidente, nenhuma ação; nenhuma notificação externa em caso algum | ☐ | |
| A12 | Reinício mantém os dados | Contagens iguais após `stop` e `up` | ☐ | |
| A13 | Reprocessar não duplica | `inserted=0`; `total = distintos` | ☐ | |
| A14 | E2E reproduzível | `validate.sh e2e`: 18 passando | ☐ | |
| A15 | Telas no celular | Mapa e filtros utilizáveis | ☐ | |
