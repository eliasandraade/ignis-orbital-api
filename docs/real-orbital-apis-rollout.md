# Rollout: Integrações Reais de Alertas Orbitais

**Branch:** `feature/real-orbital-apis`  
**Data:** 2026-06-01  
**Autores:** Elias Sales de Freitas (RM561257) · João Vitor Bernardo (RM566427)  
**Projeto:** IGNIS Orbital / Guardião da Caatinga — FIAP GS 2026

---

## Sumário

Este documento descreve o procedimento de rollout para habilitar as integrações
reais de focos de calor satelital (NASA FIRMS VIIRS e INPE TerraBrasilis WFS)
no ambiente de produção (Railway).

Ambas as integrações são **opt-in via variável de ambiente**. O backend continua
funcionando normalmente enquanto nenhuma está habilitada — dados demo são
retornados ao frontend sem nenhum erro.

---

## Fontes integradas

| Fonte | Provedor | Autenticação | Status padrão |
|---|---|---|---|
| NASA FIRMS VIIRS SNPP NRT | NASA EOSDIS | `NASA_FIRMS_MAP_KEY` (gratuita) | Desabilitado |
| INPE TerraBrasilis WFS | INPE / DPI | Nenhuma (pública) | Desabilitado |

---

## Comportamento por combinação de variáveis

| `NASA_FIRMS_ENABLED` | `NASA_FIRMS_MAP_KEY` | `INPE_QUEIMADAS_ENABLED` | `source_status` | `fallback_used` |
|---|---|---|---|---|
| `false` | vazio | `false` | `disabled_missing_api_key` | `true` |
| `true` | vazio | `false` | `disabled_missing_api_key` | `true` |
| `false` | qualquer | `true` | `live` | `false` |
| `true` | configurada | `false` | `live` | `false` |
| `true` | configurada | `true` | `live` | `false` |
| `true` | configurada | `true` (INPE falhou) | `live` (NASA ok) ou `unavailable` | conforme |

Em caso de falha de **todos** os provedores ativos, `source_status` retorna
`unavailable` e dados demo são usados como fallback (frontend nunca fica sem dados).

---

## Procedimento de ativação — INPE TerraBrasilis (recomendado primeiro)

A INPE não requer chave de API. Ativar é uma alteração de única variável.

### Railway — passos

1. Abra o dashboard Railway → serviço `ignis-orbital-api`.
2. Aba **Variables** → edite ou adicione:
   ```
   INPE_QUEIMADAS_ENABLED=true
   ```
3. Clique **Save** → Railway reinicia o container automaticamente.
4. Aguarde o deploy concluir (~30 s) e verifique:
   ```
   GET https://<seu-dominio>/api/v1/orbital-alerts
   ```
   Esperado: `source_status: "live"`, `providers_successful: ["inpe_queimadas"]`.

### Rollback imediato

Altere `INPE_QUEIMADAS_ENABLED=false` e salve. O serviço volta ao modo demo
sem reiniciar a aplicação (a variável é lida na próxima requisição após o TTL).

---

## Procedimento de ativação — NASA FIRMS VIIRS

### Obter MAP KEY (gratuita)

1. Acesse <https://firms.modaps.eosdis.nasa.gov/api/map_key/>.
2. Preencha nome, e-mail e organização → chave gerada instantaneamente.
3. A chave é do formato `abcdef1234567890...` (32 caracteres hex).

### Railway — passos

1. Abra o dashboard Railway → serviço `ignis-orbital-api`.
2. Aba **Variables** → adicione (nunca commitar estes valores):
   ```
   NASA_FIRMS_MAP_KEY=<sua-map-key>
   NASA_FIRMS_ENABLED=true
   ```
3. Opcionalmente ajuste o bbox se quiser cobrir outra região:
   ```
   FIRE_BBOX=-45.0,-12.0,-34.5,2.5
   ```
   Formato: `lng_min,lat_min,lng_max,lat_max` (EPSG:4326).
4. Clique **Save** → aguarde deploy.
5. Dispare uma ingestão manual para popular o cache:
   ```
   POST https://<seu-dominio>/api/v1/orbital-alerts/ingest
   ```
6. Verifique:
   ```
   GET https://<seu-dominio>/api/v1/orbital-alerts
   ```
   Esperado: `source_status: "live"`, `providers_successful: ["nasa_firms"]`
   (ou `["nasa_firms", "inpe_queimadas"]` se INPE também estiver ativo).

### Rollback imediato

Altere `NASA_FIRMS_ENABLED=false` ou remova `NASA_FIRMS_MAP_KEY`. A chave
**nunca** aparece em logs, respostas de API ou mensagens de erro.

---

## Variáveis de ambiente (referência completa)

| Variável | Padrão | Descrição |
|---|---|---|
| `NASA_FIRMS_ENABLED` | `false` | Habilita ingestão NASA FIRMS VIIRS |
| `NASA_FIRMS_MAP_KEY` | `` | Chave de acesso (obter em firms.modaps.eosdis.nasa.gov) |
| `NASA_FIRMS_BASE_URL` | `https://firms.modaps.eosdis.nasa.gov/api` | URL base da API (não alterar) |
| `FIRE_BBOX` | `-45.0,-12.0,-34.5,2.5` | Bounding box de busca (CE/PI/MA/TO) |
| `FIRE_LOOKBACK_DAYS` | `1` | Dias de lookback para fetch VIIRS |
| `INPE_QUEIMADAS_ENABLED` | `false` | Habilita fonte INPE TerraBrasilis WFS |
| `INPE_QUEIMADAS_URL` | `https://terrabrasilis.dpi.inpe.br/geoserver/ows` | URL WFS INPE (não alterar) |
| `EXTERNAL_API_TIMEOUT_SECONDS` | `10` | Timeout HTTP para chamadas externas |
| `EXTERNAL_API_CACHE_TTL_MINUTES` | `60` | TTL do cache in-memory (minutos) |

---

## Endpoints afetados

| Método | Path | Comportamento |
|---|---|---|
| `GET` | `/api/v1/orbital-alerts` | Retorna alertas agregados (cache-first). Nunca falha — demo se todos desabilitados. |
| `POST` | `/api/v1/orbital-alerts/ingest` | Dispara ingestão de todos os provedores ativos e invalida o cache. |

### Campos de resposta v2 (backwards-compatible)

Os seguintes campos foram adicionados ao schema `OrbitalAlertListResponse` e
`IngestResponse`. São opcionais e têm valores padrão — clientes existentes não
precisam alterar nada.

```json
{
  "providers_attempted": ["inpe_queimadas"],
  "providers_successful": ["inpe_queimadas"],
  "fallback_used": false,
  "errors": []
}
```

---

## Notas de segurança

- `NASA_FIRMS_MAP_KEY` **nunca** é logada, nem inclusa em respostas de API ou
  mensagens de erro. Erros HTTP da NASA FIRMS reportam apenas o tipo da exceção
  (ex.: `ConnectTimeout`).
- O campo `errors` em respostas HTTP nunca expõe a chave.
- INPE TerraBrasilis é pública e não requer segredo.

---

## Cache e workers Railway

O cache é **in-memory por processo**. Com `--workers 2` (Railway padrão),
cada worker tem cache independente — no máximo 2 chamadas externas por TTL
por fonte. Isso é aceitável para o volume atual do projeto.

Para cache compartilhado entre workers utilize Redis (evolução futura, fora
do escopo desta fase).

---

## Validação local confirmada — 2026-06-01

| Cenário | `source_status` | `providers_successful` | `total` | `fallback_used` |
|---|---|---|---|---|
| INPE ativo, NASA desabilitado | `live` | `["inpe_queimadas"]` | 34 (dados reais) | `false` |
| Ambos desabilitados | `disabled_missing_api_key` | `[]` | 3 (demo) | `true` |

Testes automatizados: **121 passed** — `pytest` + `ruff check .` (exit 0).
