# IGNIS Core — Recuperação da API no Railway

> **Substituído em 03/11/2026 por [RAILWAY-DEPLOYMENT.md](RAILWAY-DEPLOYMENT.md)** (plano de implantação Railway-only) e [HOMOLOGATION-CHECKLIST.md](HOMOLOGATION-CHECKLIST.md).
> A versão anterior deste checklist (Sprint 0.1) continua no histórico do Git.

## Diagnóstico da Sprint 0.1 (somente leitura, ainda válido)

| Verificação | Resultado |
|---|---|
| `curl https://ignis-api-production.up.railway.app/health` | `404 {"message":"Application not found"}`: nenhum serviço ligado ao domínio |
| `railway list` (conta do proprietário) | Nenhum projeto ou serviço IGNIS |
| Deploys no GitHub (`/deployments`) | Nenhum deploy registrado para `ignis-orbital-api` |

**Conclusão:**
- não há o que "religar": a API precisa de um novo provisionamento, descrito em RAILWAY-DEPLOYMENT §7;
- os dados do banco antigo, se existiam, não estão acessíveis.

## Onde cada parte do checklist antigo foi parar

| Tema | Agora em |
|---|---|
| Variáveis de ambiente e segredos | RAILWAY-DEPLOYMENT §4 (e `.railway/railway.ts`) |
| Provisionamento, primeiro admin | RAILWAY-DEPLOYMENT §7 |
| Smoke pós-deploy | RAILWAY-DEPLOYMENT §8 e HOMOLOGATION-CHECKLIST B |
| Usuários demonstrativos | RAILWAY-DEPLOYMENT §10 |
| Rollback | RAILWAY-DEPLOYMENT §9 |
| Frontend | RAILWAY-DEPLOYMENT §3 (serviço `web` no Railway; a Vercel não é mais usada) |
| Backups e operação | RAILWAY-DEPLOYMENT §10 |
