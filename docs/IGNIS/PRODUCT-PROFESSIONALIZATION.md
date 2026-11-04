# IGNIS Orbital — profissionalização do produto

Branches: `feat/ignis-admin-cockpit` na API (empilhada sobre `feat/ignis-human-validation`, PR #8) e
no web (empilhada sobre `feat/ignis-human-validation`, PR #7). Identidade: **IGNIS Orbital by
Andrade Systems**. Nenhum vínculo com órgãos públicos (Bombeiros, Defesa Civil etc.) é afirmado.

## 1. Referências acadêmicas removidas

Histórico Git, licenças de terceiros e atribuições foram preservados. A documentação da entrega
acadêmica foi **arquivada** fora da navegação (`ignis-fire-watch/docs/archive/entrega-academica/`,
com aviso em `docs/archive/README.md`).

| Repositório | Onde | O que havia | Agora |
|---|---|---|---|
| API | `app/main.py` (Swagger/OpenAPI) | "Projeto acadêmico FIAP — Global Solution 2026", autores e RMs | Descrição profissional (autenticação, permissões, paginação, datas, erros), contato Andrade Systems, tags por domínio |
| API | `README.md` | FIAP/Global Solution, tabela de autores com RM, "fins acadêmicos", licença "uso educacional" | IGNIS Orbital by Andrade Systems; licença definida pelo proprietário |
| API | `pyproject.toml` | descrição genérica, autores acadêmicos | descrição do produto, autor Andrade Systems |
| API | User-Agent Nominatim/Open-Meteo | "FIAP GS 2026; academic project; contact: e-mail pessoal" | `IGNIS-Orbital/1.0 (Andrade Systems; +URL do repositório)` (a política do Nominatim pede identificação com contato) |
| Web | `index.html` | título "Plataforma Inteligente…", meta author com RMs, Twitter "FIAP GS 2026" | título, descrição, OG/Twitter e author Andrade Systems; `theme-color` |
| Web | `public/favicon.svg` | chama genérica | marca orbital (gradiente IGNIS) |
| Web | Login | rodapé "FIAP GS 2026 · nomes · RMs", "qualquer credencial é aceita" | marca + orientação de acesso; sem modo demonstrativo |
| Web | Splash | rodapé com FIAP/RMs, link "Ver Economia Espacial", "IA" | © Andrade Systems, fontes reais (INPE, NASA FIRMS, IBGE) |
| Web | Guard admin | comentário "pitch", "Protótipo demonstrativo FIAP GS 2026" | tela "Acesso não permitido" |
| Web | Topbar | "IGNIS Orbital · Protótipo" | removido (shell novo) |
| Web | Banner de integridade | "PROTÓTIPO NÃO OPERACIONAL" | só aparece com falha real de consulta |
| Web | Aurora, ESG, Economia Espacial, War Room, gráficos de economia espacial, portal público | menções a FIAP/RM/acadêmico/protótipo/pitch | removidas |
| Web | `README.md` | FIAP, turma, RMs, "vídeo de pitch e apresentação acadêmica" | reescrito para o produto |

Verificação automática: o CI do web reprova o build se o bundle contiver `FIAP`, `Global Solution`,
RMs, `MOCK_USERS` ou `FALLBACK_`; o teste `test_openapi_has_professional_metadata_and_no_academic_text`
faz o mesmo no OpenAPI; o E2E procura esses termos nas telas operacionais.

## 2. Mocks e fallbacks eliminados

A interface agora é **somente API**. Estados permitidos para qualquer dado: dado real, sem registros,
fonte não configurada, serviço temporariamente indisponível, não implementado.

| Fonte fictícia | Situação |
|---|---|
| `src/data/{areas,incidents,reports,operations,users,esg}.ts` e `src/data/fallback/index.ts` | **Excluídos** (nenhum teste precisava deles) |
| Modo demonstrativo `VITE_USE_API=false` (`isApiEnabled`, `isApiMode`) | **Removido** do código, `.env.example`, Dockerfile, `deploy/build-env.mjs` (agora exige `VITE_API_URL`) e CI (passo "build demonstrativo" removido). O IaC do Railway ainda passa `VITE_USE_API=true`, que é ignorado — não foi alterado para não mexer em infraestrutura. |
| `/select-profile` (escolher papel sem login) | **Removido**; a rota redireciona ao login |
| Login que aceitava qualquer credencial | **Removido** |
| `AdminPanelPage` com `FALLBACK_USERS`/`FALLBACK_AUDIT_LOG` | **Substituído** pelo Admin Cockpit (só API) |
| 16 hooks com ramo demonstrativo | Ramo removido; erro → estado de erro, nunca mock |
| `protectedAreaAdapter`: risco sempre `low`, confiança 75/85%, centro padrão e caixa de 0,08° inventados | Valores `null`; mapa usa o centróide real do polígono |
| `incidentAdapter`: texto "Aurora" e confiança fixos por severidade | Removidos |
| War Room: `PROTOCOL_INCENDIO` (protocolo inventado) e círculo de fogo fictício | "Protocolo operacional não configurado"; círculo removido; texto "Nenhum órgão externo é notificado" |
| `useWeatherRisk`: risco "moderado" de preenchimento | `null` |
| `dataSource` com estados `demo`/`fallback`/`mixed` | Só `loading`/`ok`/`empty`/`error` |
| Ações sem backend como "simulação" (`demonstrativo`) | Estado `nao-implementado`, botões desabilitados |

Teste de regressão: E2E "modo API: nenhuma tela operacional exibe dados fictícios ou textos
acadêmicos" e o passo de CI que inspeciona o bundle.

Pontos que ainda merecem revisão (dados reais, mas apresentação a melhorar):
- `incidentAdapter` converte `affected_hectares`/`confidence` ausentes em 0 ("0 ha"/"0%") em vez de "—".
- Contagem de membros das equipes não vem da API (o campo deixou de ser exibido).
- O card de clima do painel consulta um ponto de referência fixo e rotulado (dado real, ponto arbitrário).
- Orientações "ligue 193/199" no portal público são orientação de segurança pública, não integração.

## 3. Funcionalidades fora da navegação operacional (código preservado)

Removidas do roteador (não entram no bundle) por falta de fonte de dados ou metodologia validada:

| Funcionalidade | Motivo |
|---|---|
| Aurora IA (`/gestor/aurora`) | Não há modelo de IA integrado; respostas eram simuladas. O endpoint `POST /api/v1/aurora/chat` segue público na API — ver risco residual na revisão de segurança. |
| Relatório ESG (`/gestor/esg`) | Indicadores sem base validada |
| Economia Espacial (`/gestor/economia-espacial`) | Valores ilustrativos |
| Ranking de Risco (`/gestor/ranking`) | Classificação de risco sem metodologia validada |

Também marcados como "não implementado" dentro de telas operacionais: check-in/anexos/relatório na
operação de campo, blocos "Aurora" em incidentes e denúncias, risco calculado de área protegida.

## 4. Mapa de navegação

Shell único (sidebar agrupada, cabeçalho com trilha, menu em gaveta abaixo de 900 px, ícones
lucide, foco visível, `aria-current`, horários em Fortaleza):

```
Operação (gestor, órgão, admin)          Admin Cockpit (admin)
├─ Operação                              ├─ Visão geral
│  ├─ Painel            /gestor          │  └─ Painel              /admin
│  ├─ Mapa orbital      /gestor/map      ├─ Pessoas e acesso
│  ├─ Denúncias         /gestor/reports  │  ├─ Usuários            /admin/users
│  └─ Mobilização       /gestor/mobilization │  └─ Permissões     /admin/permissions
├─ Resposta                              ├─ Dados
│  ├─ Sala de crise     /gestor/war-room │  ├─ Fontes de dados     /admin/sources
│  └─ Operação de campo /gestor/field    │  └─ Execuções           /admin/jobs
└─ Administração (só admin)              ├─ Sistema
   └─ Admin Cockpit     /admin           │  ├─ API e diagnóstico   /admin/api
                                         │  ├─ Auditoria           /admin/audit
Conta: /login, /conta/senha              │  └─ Configuração        /admin/settings
Portal público: /public, /public/map,    └─ Atalhos
  /public/report, /public/report/status/:id  └─ Voltar à operação  /gestor
```

Destino após login: admin → `/admin`; gestor/órgão → `/gestor`; campo → `/gestor/field`;
troca de senha pendente → `/conta/senha` antes de qualquer outra tela.
