# IGNIS Orbital — Guia de Integração Frontend

Este documento descreve como o frontend (ignis-fire-watch) deve consumir esta API, substituindo progressivamente os mocks em `src/data/`.

---

## URLs base

| Ambiente | URL |
|---|---|
| Desenvolvimento local (Vite) | `http://localhost:8000` |
| Desenvolvimento local (Docker) | `http://localhost:8000` |
| Produção (futuro) | a definir — variável `VITE_API_URL` |

Todos os endpoints de domínio usam o prefixo `/api/v1/`.

---

## Autenticação

### Login

```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "gestor@semace.ce.gov.br",
  "password": "gestor@123"
}
```

Resposta:
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 28800,
  "user": {
    "id": "...",
    "name": "Gestor SEMACE",
    "email": "gestor@semace.ce.gov.br",
    "role": "gestor",
    "team_id": null,
    "is_active": true,
    "created_at": "...",
    "updated_at": "..."
  }
}
```

### Como salvar o token

```ts
// src/services/auth.ts
const { access_token, user } = await login(email, password);
localStorage.setItem("ignis_token", access_token);
localStorage.setItem("ignis_user", JSON.stringify(user));
```

### Como enviar o token

```ts
const headers = {
  "Authorization": `Bearer ${localStorage.getItem("ignis_token")}`,
  "Content-Type": "application/json",
};
```

### Usuário corrente

```http
GET /api/v1/auth/me
Authorization: Bearer <token>
```

---

## Mapeamento src/data/ → API

### `areas.ts` → Protected Areas

| Ação | Endpoint |
|---|---|
| Listar áreas | `GET /api/v1/protected-areas?page=1&size=20&state=CE` |
| Detalhes de uma área | `GET /api/v1/protected-areas/{id}` |
| Incidentes de uma área | `GET /api/v1/protected-areas/{id}/incidents` |
| Denúncias de uma área | `GET /api/v1/protected-areas/{id}/reports` |
| Criar área | `POST /api/v1/protected-areas` (orgao+) |
| Editar área | `PATCH /api/v1/protected-areas/{id}` (orgao+) |
| Excluir área | `DELETE /api/v1/protected-areas/{id}` (admin) |

**Campos geoespaciais:** A API retorna `geometry_wkt` e `buffer_zone_wkt` como strings WKT (Well-Known Text), e `center_lat`/`center_lng` como floats para uso direto em mapas.

```ts
// Diferença de formato: mock retorna { lat, lng }, API retorna { center_lat, center_lng }
const center = { lat: area.center_lat, lng: area.center_lng };
```

---

### `reports.ts` → Public Reports

| Ação | Endpoint |
|---|---|
| Submeter denúncia (pública, sem auth) | `POST /api/v1/reports` |
| Consultar status por protocolo (pública) | `GET /api/v1/reports/lookup?protocol=RP-20260101-ABCD` |
| Listar denúncias | `GET /api/v1/reports` (gestor+) |
| Detalhes de uma denúncia | `GET /api/v1/reports/{id}` (gestor+) |
| Validar denúncia | `PATCH /api/v1/reports/{id}/validate` (gestor+) |
| Descartar denúncia | `PATCH /api/v1/reports/{id}/discard` (gestor+) |
| Converter em incidente | `POST /api/v1/reports/{id}/convert-to-incident` (gestor+) |
| Atualizar status (genérico) | `PATCH /api/v1/reports/{id}/status` (gestor+) |

**Protocolo:** O protocolo é retornado na resposta do `POST /api/v1/reports`. Salve e exiba para o usuário.

**Privacidade:** O endpoint público `/lookup` retorna apenas `protocol`, `type`, `urgency`, `status`, `is_anonymous`, `protected_area_id` e datas. Não expõe `contact` nem `reporter_name`.

```ts
// Submissão pública — sem token
const report = await fetch("/api/v1/reports", {
  method: "POST",
  body: JSON.stringify({ type: "fire", description: "...", urgency: "high", latitude: -3.7, longitude: -38.5 }),
});
// Guarda report.protocol para rastrear status
```

---

### `incidents.ts` → Incidents

| Ação | Endpoint |
|---|---|
| Listar incidentes | `GET /api/v1/incidents?page=1&size=20` |
| Listar críticos ativos | `GET /api/v1/incidents/active/critical` |
| Detalhes | `GET /api/v1/incidents/{id}` |
| Timeline | `GET /api/v1/incidents/{id}/timeline` |
| Criar incidente | `POST /api/v1/incidents` (gestor+) |
| Atualizar | `PATCH /api/v1/incidents/{id}` (gestor+) |
| Mudar status | `PATCH /api/v1/incidents/{id}/status` (gestor+) |
| Ativar protocolo emergência | `POST /api/v1/incidents/{id}/activate-protocol` (gestor+) |
| Adicionar evento | `POST /api/v1/incidents/{id}/events` (gestor+) |
| War Room | `GET /api/v1/war-room` (gestor+) |
| Detalhe no War Room | `GET /api/v1/war-room/{incident_id}` (gestor+) |

**Filtros disponíveis em `GET /incidents`:** `type`, `severity`, `status`, `area_id`

**Status válidos:** `detected`, `monitoring`, `active`, `contained`, `resolved`, `protocol_activated`

**Severity válidos:** `low`, `medium`, `high`, `critical`

---

### `teams.ts` → Field Teams

| Ação | Endpoint |
|---|---|
| Listar equipes | `GET /api/v1/teams?status=available` |
| Detalhes | `GET /api/v1/teams/{id}` |
| Criar equipe | `POST /api/v1/teams` (admin) |
| Atualizar | `PATCH /api/v1/teams/{id}` (gestor+) |

---

### `resources.ts` → Resources

| Ação | Endpoint |
|---|---|
| Listar recursos | `GET /api/v1/resources?type=vehicle&status=available` |
| Detalhes | `GET /api/v1/resources/{id}` |
| Criar recurso | `POST /api/v1/resources` (admin) |
| Atualizar | `PATCH /api/v1/resources/{id}` (gestor+) |

---

### Missions → Missions

| Ação | Endpoint |
|---|---|
| Listar missões | `GET /api/v1/missions?incident_id=...&status=active` |
| Detalhes | `GET /api/v1/missions/{id}` |
| Criar missão | `POST /api/v1/missions` (gestor+) |
| Atualizar | `PATCH /api/v1/missions/{id}` (gestor+) |
| Mudar status | `PATCH /api/v1/missions/{id}/status` (gestor+) |

---

### `esg.ts` → ESG Reports

| Ação | Endpoint |
|---|---|
| Listar relatórios ESG | `GET /api/v1/esg?area_id=...` (orgao+) |
| Detalhes | `GET /api/v1/esg/{id}` (orgao+) |
| Criar relatório | `POST /api/v1/esg` (orgao+) |

---

### `aurora-responses.ts` → Aurora IA

| Ação | Endpoint |
|---|---|
| Análise de risco | `POST /api/v1/aurora/analyze` (campo+) |
| Chat assistente | `POST /api/v1/aurora/chat` (público) |

**Aurora analyze:**
```json
{
  "incident_severity": "high",
  "incident_type": "fire",
  "area_hectares": 250,
  "wind_speed": 35,
  "humidity": 25
}
```

**Aurora chat:**
```json
{
  "message": "incêndio na reserva",
  "context": null
}
```

---

## RBAC — Controle de acesso

| Perfil | Nível | Acesso |
|---|---|---|
| `publico` | 0 | Somente endpoints sem auth (submeter denúncia, consultar protocolo, aurora chat) |
| `campo` | 1 | Missões, evidências, aurora analyze |
| `gestor` | 2 | Incidentes, denúncias, war room, equipes read, recursos read |
| `orgao` | 3 | ESG, criar/editar áreas |
| `admin` | 4 | Tudo, incluindo gestão de usuários e audit logs |

No frontend, use o `role` retornado em `/auth/me` (ou no objeto `user` do login) para mostrar/ocultar elementos de UI.

---

## Paginação

Todos os endpoints de listagem usam o formato:

```json
{
  "items": [...],
  "total": 42,
  "page": 1,
  "size": 20,
  "pages": 3
}
```

Parâmetros de query: `?page=1&size=20`

---

## Diferenças conhecidas entre mock e API

| Aspecto | Mock (`src/data/`) | API |
|---|---|---|
| Geometria de área | Objeto `{ lat, lng }` | WKT string + `center_lat`/`center_lng` |
| IDs | Strings fixas | UUIDs v4 |
| Protocolo | Fixo no mock | Gerado em `RP-YYYYMMDD-XXXX` |
| Código de incidente | Fixo | Gerado em `IGN-CE-2026-NNNN` |
| Paginação | Array direto | Objeto `Page<T>` com `items`, `total`, `pages` |
| Status de denúncia | Enum pt-BR | `pending`, `validated`, `discarded`, `converted` |
| Status de incidente | Enum pt-BR | `detected`, `monitoring`, `active`, `contained`, `resolved`, `protocol_activated` |
| Datas | Strings ISO | `datetime` com timezone UTC |

---

## Estratégia de integração recomendada

Substituir na seguinte ordem (menor risco → maior risco):

1. **`/health`** — sem auth, substitui verificação de disponibilidade
2. **`/api/v1/protected-areas`** — público, lista e detalhe de áreas
3. **`POST /api/v1/reports`** — submissão pública de denúncia
4. **`GET /api/v1/reports/lookup`** — rastrear denúncia por protocolo
5. **`POST /api/v1/auth/login`** — implementar login real
6. **`GET /api/v1/incidents`** + war-room — painel de incidentes
7. **`/api/v1/aurora/chat`** — assistente público
8. **Demais módulos** — teams, resources, missions, ESG, evidence

---

## Configuração do frontend

Em `ignis-fire-watch`, crie/atualize `.env`:

```env
VITE_API_URL=http://localhost:8000
```

Em `src/services/api.ts` (ou equivalente):

```ts
const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function apiFetch(path: string, options?: RequestInit) {
  const token = localStorage.getItem("ignis_token");
  return fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
  });
}
```
