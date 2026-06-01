# IGNIS Orbital API

**Backend REST para monitoramento ambiental e proteção de áreas naturais.**

Projeto acadêmico desenvolvido para a disciplina **Global Solution 2026** — FIAP.

| Autor | RM |
|---|---|
| Elias Sales de Freitas | RM561257 |
| João Vitor Bernardo | RM566427 |

---

## Sobre o projeto

A IGNIS Orbital API é o backend do sistema [IGNIS Orbital](https://ignis-fire-watch-main.vercel.app), uma plataforma de monitoramento ambiental focada em detecção e gestão de incidentes em áreas protegidas brasileiras.

A API oferece:

- Cadastro e consulta de áreas protegidas com dados geoespaciais (PostGIS)
- Registro público de denúncias ambientais com rastreamento por protocolo
- Gestão de incidentes com timeline de eventos
- Central tática (War Room) com visão consolidada de incidentes ativos
- Controle de equipes, recursos e missões de campo
- Análise rule-based via Aurora IA
- Relatórios ESG/técnicos com métricas de impacto
- Auditoria completa de ações

---

## Stack

| Camada | Tecnologia |
|---|---|
| Framework | FastAPI |
| Linguagem | Python 3.12 |
| Banco de dados | PostgreSQL 16 + PostGIS 3.4 |
| ORM | SQLAlchemy 2 (async) |
| Migrations | Alembic |
| Schemas | Pydantic v2 |
| Autenticação | JWT (PyJWT) |
| Servidor | Uvicorn |
| Testes | pytest + pytest-asyncio |
| Linter/Formatter | Ruff |
| Containers | Docker + Docker Compose |

---

## Rodando localmente

### Pré-requisitos

- [Docker](https://www.docker.com/) e Docker Compose
- Python 3.12+ (para desenvolvimento fora do container)
- [uv](https://github.com/astral-sh/uv) ou pip

### 1. Clone o repositório

```bash
git clone https://github.com/eliasandraade/ignis-orbital-api.git
cd ignis-orbital-api
```

### 2. Configure o ambiente

```bash
cp .env.example .env
# Edite .env com suas configurações locais
```

> **Importante:** Gere uma chave JWT segura para `JWT_SECRET_KEY`:
> ```bash
> python -c "import secrets; print(secrets.token_hex(32))"
> ```

### 3. Suba os containers

```bash
docker compose up
```

O entrypoint já executa `alembic upgrade head` automaticamente antes de subir o servidor.

A API ficará disponível em: **http://localhost:8000**

### 4. Documentação interativa

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### 5. Verificar saúde da API

```bash
curl http://localhost:8000/health
# {"status":"ok","service":"ignis-orbital-api","version":"0.1.0","environment":"development"}

curl http://localhost:8000/ready
# {"status":"ready","database":"connected"}
```

---

## Desenvolvimento sem Docker

```bash
# Criar ambiente virtual
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
.venv\Scripts\activate      # Windows

# Instalar dependências
pip install -e ".[dev]"

# Copiar .env e ajustar DATABASE_URL para apontar para banco local
cp .env.example .env

# Aplicar migrations (banco precisa estar rodando)
alembic upgrade head

# Subir servidor com hot reload
uvicorn app.main:app --reload --port 8000
```

---

## Migrations

```bash
# Aplicar todas as migrations pendentes
alembic upgrade head

# Criar nova migration (após alterar models)
alembic revision --autogenerate -m "descricao da mudanca"

# Reverter última migration
alembic downgrade -1

# Ver histórico
alembic history
```

---

## Testes

```bash
# Rodar todos os testes
pytest

# Com cobertura detalhada
pytest --cov=app --cov-report=html

# Testes sem banco (unitários)
pytest tests/test_health.py -v
```

> Testes de integração (banco real) requerem PostgreSQL+PostGIS disponível.
> Use `docker compose up db` para subir apenas o banco.

---

## Seed de dados demonstrativos

```bash
# Após migrations aplicadas:
python -m seed
```

> **Nota:** Os dados gerados pelo seed são exclusivamente demonstrativos para fins acadêmicos.
> Os campos `source = "base demonstrativa acadêmica"` e `data_quality = "estimated"` indicam
> que não representam dados oficiais de nenhum órgão ambiental.

### Credenciais de teste (seed)

| Perfil | Email | Senha | Acesso |
|--------|-------|-------|--------|
| Admin | admin@ignis-orbital.com | admin@123 | Total |
| Gestor | gestor@semace.ce.gov.br | gestor@123 | Incidentes, denúncias, war room |
| Órgão | operador@defesacivil.ce.gov.br | operador@123 | Visão operacional, ESG |
| Campo | campo@ibama.gov.br | campo@123 | Missões, evidências |

> ⚠️ Credenciais **exclusivamente para demonstração/testes locais**. Nunca use em produção.

---

## Lint e formatação

```bash
# Verificar
ruff check .

# Corrigir automaticamente
ruff check . --fix

# Formatar
ruff format .
```

---

## Integrações externas

| Fonte | Endpoint | Chave | Status padrão |
|---|---|---|---|
| Open-Meteo | `GET /api/v1/environment/weather-risk` | Não requerida | ✅ Sempre ativo |
| NASA FIRMS VIIRS | `GET /api/v1/orbital-alerts` | `NASA_FIRMS_MAP_KEY` | Desabilitado até habilitar |
| INPE TerraBrasilis WFS | `GET /api/v1/orbital-alerts` | Não requerida | Desabilitado até habilitar |
| OSM/Nominatim | `GET /api/v1/geocoding/reverse` | Não requerida | ✅ Sempre ativo |

### Habilitando NASA FIRMS

1. Cadastre-se em [firms.modaps.eosdis.nasa.gov](https://firms.modaps.eosdis.nasa.gov/api/map_key/)
2. Configure no ambiente: `NASA_FIRMS_MAP_KEY=<sua-chave>` e `NASA_FIRMS_ENABLED=true`
3. Nunca commite a chave — use variável de ambiente

### Habilitando INPE Queimadas (TerraBrasilis)

Apenas configure `INPE_QUEIMADAS_ENABLED=true` — sem chave necessária.

Fonte: layer `ams1h:active-fire-today` do GeoServer público do INPE.

### Comportamento de fallback

Quando todas as fontes estão desabilitadas ou falham, o endpoint retorna dados
demo (`source_status: "disabled_missing_api_key"`) com `fallback_used: true`.
O frontend sempre recebe uma resposta válida — nunca um erro 5xx.

---

## Variáveis de ambiente

Ver [.env.example](.env.example) para a lista completa com descrições.

Variáveis obrigatórias para produção:

| Variável | Descrição |
|---|---|
| `DATABASE_URL` | URL de conexão PostgreSQL async |
| `JWT_SECRET_KEY` | Chave secreta JWT (mínimo 32 chars) |

Variáveis opcionais para integrações externas:

| Variável | Padrão | Descrição |
|---|---|---|
| `NASA_FIRMS_ENABLED` | `false` | Habilitar NASA FIRMS (requer MAP_KEY) |
| `NASA_FIRMS_MAP_KEY` | vazio | Chave de acesso NASA FIRMS |
| `FIRE_BBOX` | `-45.0,-12.0,-34.5,2.5` | Bounding box CE/PI/MA/TO |
| `FIRE_LOOKBACK_DAYS` | `1` | Dias de lookback para VIIRS |
| `INPE_QUEIMADAS_ENABLED` | `false` | Habilitar INPE TerraBrasilis |
| `INPE_QUEIMADAS_URL` | `https://terrabrasilis.dpi.inpe.br/geoserver/ows` | URL do GeoServer INPE |
| `EXTERNAL_API_TIMEOUT_SECONDS` | `10` | Timeout HTTP para APIs externas |
| `EXTERNAL_API_CACHE_TTL_MINUTES` | `60` | TTL do cache in-memory |

---

## Estrutura do projeto

```
app/
├── main.py              # App factory, CORS, lifespan
├── config.py            # Pydantic Settings
├── database.py          # Engine async, Base ORM, get_db
├── health/              # GET /health, GET /ready
├── auth/                # POST /api/v1/auth/* (Fase 4)
├── users/               # /api/v1/admin/users (Fase 4)
├── protected_areas/     # /api/v1/protected-areas (Fase 5)
├── reports/             # /api/v1/public-reports + /reports (Fase 6)
├── incidents/           # /api/v1/incidents (Fase 7)
├── teams/               # /api/v1/teams + resources + missions (Fase 8)
├── war_room/            # /api/v1/war-room (Fase 9)
├── esg/                 # /api/v1/reports/esg (Fase 10)
├── aurora/              # /api/v1/aurora (Fase 10)
├── evidence/            # modelo compartilhado
└── audit/               # log_action() + /api/v1/admin/audit-logs (Fase 10)
```

---

## Roadmap de fases

| Fase | Status | Conteúdo |
|---|---|---|
| 0 | ✅ | Setup, Docker, FastAPI, health/ready |
| 1+2 | ✅ | Database, SQLAlchemy async, todos os models ORM + Alembic migrations |
| 3 | ✅ | Seed demonstrativo completo |
| 4 | ✅ | Auth JWT + RBAC 5 perfis |
| 5 | ✅ | Protected Areas API + PostGIS |
| 6 | ✅ | Public Reports + protocolos + workflow (validar, descartar, converter) |
| 7 | ✅ | Incidents + timeline + War Room |
| 8 | ✅ | Teams, Resources, Missions, Evidence |
| 9 | ✅ | Aurora rule-based + ESG reports |
| 10 | ✅ | Audit log API, admin stats, qualidade final |
| Auditoria | ✅ | Sub-recursos de área, activate-protocol, war-room alias, privacidade |
| Integrações v1 | ✅ | Open-Meteo, NASA FIRMS (stub), OSM/Nominatim — produção Railway |
| **Integrações v2** | 🔜 | NASA FIRMS real + cache, INPE TerraBrasilis WFS, agregação multi-fonte |
| Frontend | ✅ | Integração progressiva completa — 21 rotas, API real Railway/Vercel |

---

## Integração com o frontend

O frontend [IGNIS Orbital](https://github.com/eliasandraade/ignis-fire-watch) utiliza atualmente dados
mockados em `src/data/`. Esta API substituirá progressivamente esses mocks, módulo a módulo, via
`src/services/api.ts` com `VITE_API_URL` apontando para esta API.

CORS já configurado para:
- `http://localhost:8080` (dev)
- `http://localhost:5173` (Vite dev)
- `https://ignis-fire-watch-main.vercel.app` (produção)

---

## Licença

Projeto acadêmico — FIAP Global Solution 2026.
Uso educacional. Dados demonstrativos não representam informações oficiais.
