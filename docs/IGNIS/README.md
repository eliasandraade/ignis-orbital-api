# IGNIS — Índice da documentação técnica

Documentação produzida na **Sprint 0 — Auditoria, Saneamento e Preparação para Produção** (03/11/2026).
A documentação de produto e arquitetura fica neste repositório (`ignis-orbital-api`, o futuro **IGNIS Core**).
O inventário de telas fica no repositório do frontend.

| # | Documento | Repositório | Conteúdo |
|---|---|---|---|
| 1 | [AUDIT-REPORT.md](AUDIT-REPORT.md) | backend | Diagnóstico completo: achados com evidência, arquivo e gravidade |
| 2 | [ARCHITECTURE.md](ARCHITECTURE.md) | backend | Arquitetura atual (as-is) e proposta (to-be) |
| 3 | [SECURITY-REVIEW.md](SECURITY-REVIEW.md) | backend | Ameaças, vulnerabilidades, controles, riscos residuais |
| 4 | [FRONTEND-INVENTORY.md](https://github.com/eliasandraade/ignis-fire-watch/blob/audit/ignis-sprint-0/docs/IGNIS/FRONTEND-INVENTORY.md) | frontend | Telas, rotas, matriz de rastreabilidade de dados, ações |
| 5 | [API-INVENTORY.md](API-INVENTORY.md) | backend | Endpoints, autenticação, contratos e estado de implementação |
| 6 | [DATA-SOURCES.md](DATA-SOURCES.md) | backend | Fontes reais, demonstrativas, indisponíveis e planejadas |
| 7 | [ORKENGOV-INTEGRATION.md](ORKENGOV-INTEGRATION.md) | backend | Arquitetura da integração futura com o OrkenGov |
| 8 | [ROADMAP.md](ROADMAP.md) | backend | Fases 1–5, dependências, prioridades e critérios de aceitação |
| 9 | [PHASE-1-BACKLOG.md](PHASE-1-BACKLOG.md) | backend | Backlog técnico executável da Fase 1 |
| 10 | [SPRINT-0-DELIVERY.md](SPRINT-0-DELIVERY.md) | backend | Correções, testes, evidências, PRs e pendências |
| 11 | [RAILWAY-RECOVERY.md](RAILWAY-RECOVERY.md) | backend | *Substituído pelos itens 13 e 14*; mantém o diagnóstico da Sprint 0.1 |
| 12 | [BRANCH-STRATEGY.md](https://github.com/eliasandraade/ignis-fire-watch/blob/infra/railway-only/docs/IGNIS/BRANCH-STRATEGY.md) | frontend | Divergência `main` × `master`, branches por ambiente Railway e promoção |
| 13 | [RAILWAY-DEPLOYMENT.md](RAILWAY-DEPLOYMENT.md) | backend | **Plano de implantação Railway-only**: ambientes, serviços, segredos, deploy condicionado à CI, rollback, evidências |
| 14 | [HOMOLOGATION-CHECKLIST.md](HOMOLOGATION-CHECKLIST.md) | backend | Checklist de homologação (staging → production) |
| 15 | [PHASE-1-EXECUTION-PLAN.md](PHASE-1-EXECUTION-PLAN.md) | backend | Plano de execução da Fase 1: INPE/FIRMS, PostGIS, mapa do Ceará |
| 16 | [SPRINT-1.1-DELIVERY.md](SPRINT-1.1-DELIVERY.md) | backend | Sprint 1.1: tabelas geoespaciais, malha oficial IBGE 2025 do Ceará, contratos de ingestão, evidências |
| 17 | [SPRINT-1.2-DELIVERY.md](SPRINT-1.2-DELIVERY.md) | backend | Sprint 1.2: ingestão real NASA FIRMS e INPE, worker agendado, recuperação por *lease*, API administrativa |
| 18 | [READY-FOR-HUMAN-VALIDATION.md](READY-FOR-HUMAN-VALIDATION.md) | backend | **Estado para validação humana** (Sprints 1.3/1.4): o que está pronto, parcial e indisponível; classificação final |
| 19 | [HUMAN-VALIDATION-GUIDE.md](HUMAN-VALIDATION-GUIDE.md) | backend | Guia do avaliador: subir a pilha local, jornada, falhas, integridade, E2E e checklist de aceitação |
| 20 | [HUMAN-VALIDATION-RESULTS.md](HUMAN-VALIDATION-RESULTS.md) | backend | Testes realmente executados, evidências, defeitos encontrados e corrigidos, limitações |

## Repositórios

| Repositório | Papel | Branch de trabalho da Sprint 0 | Base |
|---|---|---|---|
| [ignis-orbital-api](https://github.com/eliasandraade/ignis-orbital-api) | Backend FastAPI (IGNIS Core) | `audit/ignis-sprint-0` | `main` |
| [ignis-fire-watch](https://github.com/eliasandraade/ignis-fire-watch) | Frontend React/Vite (base do IGNIS Command) | `audit/ignis-sprint-0` | `master` (**não** `main`, ver AUDIT-REPORT X-01) |
| [orkengov](https://github.com/eliasandraade/orkengov) | Plataforma municipal | — (somente leitura) | `main` |

## Convenções

- Gravidade: **P0** bloqueia qualquer uso fora de demonstração; **P1** precisa ser resolvido antes de piloto; **P2** melhoria planejada.
- IDs de achados: `B-` backend, `F-` frontend, `X-` transversal/processo. Os mesmos IDs são usados em todos os documentos.
- Toda afirmação sobre código cita `arquivo:linha` na revisão auditada (backend `3e22ecb`, frontend `e56d02f`) ou o commit da correção.
