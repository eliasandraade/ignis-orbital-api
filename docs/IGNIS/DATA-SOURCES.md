# IGNIS — Fontes de dados

Data: 03/11/2026. Classificação de cada informação que o IGNIS exibe ou poderá exibir.

## 1. Fontes reais em uso

| Fonte | O que fornece | Como o IGNIS acessa | Frequência / latência | Persistência | Estado |
|---|---|---|---|---|---|
| **Open-Meteo** (`api.open-meteo.com`) | Temperatura, umidade, vento e precipitação no ponto | `GET /api/v1/environment/weather-risk`; o backend calcula um score por regra fixa | Sob demanda, cache de 60 min por processo | Não | **Real**. O score de risco é uma **heurística própria, não oficial** |
| **NASA FIRMS** (VIIRS SNPP NRT) | Anomalias térmicas (lat, lng, data/hora, confiança, FRP) | `GET /api/v1/orbital-alerts` (sob demanda) e `POST …/ingest` (admin) | NRT, com latência típica de algumas horas após a passagem do satélite. Cache de 60 min | **Não** (só cache em memória) | **Real, mas desativada sem `NASA_FIRMS_MAP_KEY`**. Anomalia térmica **não** é incêndio confirmado |
| **OpenStreetMap / Nominatim** | Geocodificação reversa | `GET /api/v1/geocoding/reverse` | Sob demanda, cache por grade de cerca de 111 m | Não | Real, mas **sem consumidor na UI**. Uso institucional exige respeitar a política de uso (1 req/s, User-Agent) ou instância própria |
| **Tiles OSM** (`tile.openstreetmap.org`) | Cartografia base do mapa | Direto do navegador (Leaflet) | — | — | Real. **Inadequado para produção institucional** (política OSMF), ver ARCHITECTURE §4 |

## 2. Fontes demonstrativas

| Dado | Origem | Onde aparece | Como é sinalizado (pós Sprint 0) |
|---|---|---|---|
| Incidentes, timeline, equipes, recursos, missões, evidências, denúncias, áreas, ESG e usuários | **Seed do backend** (`seed/*.py`) quando a API está ativa | Todas as telas do gestor | Faixa global "PROTÓTIPO NÃO OPERACIONAL — dados da API podem ser de demonstração" |
| Os mesmos dados | **Mocks do frontend** (`src/data/*.ts`) quando `VITE_USE_API=false` | Todas as telas | Faixa global "MODO DEMONSTRATIVO — todos os dados são fictícios" + badges |
| Os mesmos dados, quando uma consulta da API falha | Mocks (hooks de área e war room) | Telas do gestor | Faixa "API indisponível em N consultas…". Incidente crítico e alertas FIRMS **não** são mais substituídos por mock |
| Alertas orbitais fictícios | Backend com `ORBITAL_ALERTS_DEMO_MODE=true` ou frontend em modo demo | Cards de alertas orbitais | `source_status=demo`, `is_demo=true`, fonte `DEMO` |
| Geometrias de áreas protegidas | Seed / mocks (polígonos aproximados) | Mapas | "Limites estimados/simulados"; fonte "Estimativa IGNIS (não oficial)" |
| Risco por área | Valor fixo `low` no adapter (API) ou mock | Ranking e cores do mapa | Aviso no ranking (F-12) |
| AURORA (análise e chat) | Regras fixas por severidade (`app/aurora/engine.py`, `incidentAdapter.ts`) | Dashboard, Sala de Crise, página AURORA | "Análise rule-based demonstrativa" |
| Indicadores de "Economia Espacial" (37 alertas simulados, R$ 184k etc.) | Hardcoded | `/gestor/economia-espacial` | Asterisco e nota de rodapé |

## 3. Fontes indisponíveis ou removidas

| Item | Situação |
|---|---|
| "Tempo médio de resposta", "Nível de alerta oficial" | Não existe fonte. A UI mostra **n/d** (antes: 18 min e "Crítico" hardcoded) |
| Telemetria de incidente ausente | Mostra "—" (antes: 28 °C / 50 % / 10 km/h NE inventados) |
| Notificação a SEMACE/IBAMA/Defesa Civil | **Não existe integração**. As alegações foram removidas dos mocks |
| Rotas de evacuação, abrigos, comunicação à população, despacho de viaturas | Não existem no código; nenhuma fonte |

## 4. Fontes planejadas

| Fonte | Uso previsto | Fase | Observações |
|---|---|---|---|
| NASA FIRMS, API de área: `VIIRS_SNPP_NRT`, `VIIRS_NOAA20_NRT`, `VIIRS_NOAA21_NRT`, `MODIS_NRT` | Focos por satélite, com FRP e confiança por sensor | 1 | **Integrado na Sprint 1.2** (`app/orbital/providers/firms.py`). Exige `NASA_FIRMS_MAP_KEY`; sem a chave, `disabled`. **Validado só com fixtures e resposta real de chave inválida**, nunca com chave real |
| **INPE — Programa Queimadas**: CSV diário de dados abertos (`dataserver-coids.inpe.br/.../focos/csv/diario/Brasil`) | Focos oficiais brasileiros | 1 | **Integrado na Sprint 1.2** (`app/orbital/providers/inpe.py`). Pública, sem chave, com ETag. O WFS foi preterido porque a camada do PR #2 deixou de existir (SPRINT-1.2-DELIVERY §2.2). Termos de uso e atribuição ainda não confirmados |
| Open-Meteo histórico / previsão | Correlação meteorológica e previsão de risco | 1–2 | |
| INMET (estações) | Validação meteorológica oficial | 2 | Avaliar API e licenciamento |
| FUNCEME (Ceará) | Dados meteorológicos estaduais | 2 | Depende de parceria |
| Limites oficiais de UCs (ICMBio/CNUC, SEMA-CE) | Geometrias reais das unidades de conservação | 1 | Substituir os polígonos estimados |
| **IBGE — Malha Municipal Digital 2025** (CE: 184 municípios + UF) | Jurisdições oficiais (código IBGE) | 1 | **Integrada na Sprint 1.1**: arquivos versionados com SHA-256 em `data/reference/ibge/`, referência 30/04/2025 |
| Sistemas de despacho do CBMCE / Defesa Civil | Equipes, viaturas e ocorrências reais | 4–5 | **Somente com parceria formal e autorização**. Nada disso existe hoje |

## 5. Regras de rastreabilidade (obrigatórias a partir da Fase 1)

Todo registro exibido precisa carregar:
1. `source`: provedor e produto (ex.: `NASA_FIRMS_VIIRS_SNPP_NRT`).
2. `observed_at`: horário da observação no provedor (passagem do satélite).
3. `ingested_at` / `fetched_at`: quando o IGNIS obteve o dado.
4. `is_demo`: sempre presente; nunca inferido pela UI.
5. Estado da fonte (`live`, `cached`, `unavailable`, `disabled`), exibido junto do dado.

Nenhum indicador "AO VIVO", "ONLINE" ou "TEMPO REAL" sem fonte com latência medida e documentada.
