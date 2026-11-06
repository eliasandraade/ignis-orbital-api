# IGNIS Orbital: mapa de dados e papéis (LGPD)

Levantado em 06/11/2026 no código, nos logs de staging e na configuração do Railway. Este documento registra fatos técnicos e **propostas a confirmar**. Não é parecer jurídico, e nenhuma classificação abaixo está aprovada.

## 1. Dados efetivamente armazenados

| Dado | Onde | Finalidade técnica | Prazo tecnicamente existente | Evidência |
|---|---|---|---|---|
| Nome, e-mail, papel, equipe, hash da senha, datas de criação, atualização e último acesso | Tabela `users` | Autenticação e controle de acesso | **Sem expurgo.** A conta é desativada; não há função de exclusão no código | `app/users/model.py` |
| ID e nome de quem agiu, ação, item, detalhes (motivo informado, campos alterados) | Tabela `audit_logs` | Rastreabilidade | **Sem expurgo** | `app/audit/model.py`, `app/core/audit.py` |
| IP e rota; no nginx, também o navegador | Logs de `ignis-api` e `ignis-web` | Operação e investigação | 30 dias no plano Pro, conforme a documentação do Railway | Logs de staging; [documentação de logs](https://docs.railway.com/observability/logs) |
| IP como chave do limitador | Memória do processo | Limitar tentativas | Janela curta; some ao reiniciar | `app/core/rate_limit.py` |
| Token, nome, e-mail e papel | `localStorage` do navegador (`ignis_token`, `ignis_user`) | Manter a sessão | Até sair ou a sessão ser recusada; token de até 8 h (`jwt_access_token_expire_minutes`, padrão 480, sem sobreposição em produção) | `src/services/api/authService.ts`, `app/config.py` |
| Cópias do banco, incluindo `users` e `audit_logs` | Backups de volume do Railway | Recuperação | Diário 6 dias, semanal 27 dias, mensal 89 dias | Agendamentos conferidos em 05/11/2026 |
| Focos de calor | `orbital_detections`, `ingestion_runs` | Consulta ambiental | Sem expurgo | Dados públicos do INPE; sem dado pessoal |

**Sem coleta nesta versão:** denúncias (`public_reports`, com nome, contato e localização no esquema) seguem fechadas, e as tabelas de evidências e incidentes estavam vazias em staging. Abrir qualquer um desses fluxos exige revisar este mapa e o aviso.

**Sem cookies:** o único `document.cookie` do frontend está em `components/ui/sidebar.tsx`, que nenhuma tela usa. A API não define cookies. O rascunho anterior citava esse cookie por engano.

## 2. Quem recebe dados

| Destinatário | O que recebe | Como | Situação |
|---|---|---|---|
| Railway | Todos os dados acima, exceto o `localStorage` | Hospedagem nos EUA (`us-east4`) | [DPA publicado](https://railway.com/legal/dpa): cliente como controlador e Railway como operador; Railway é controlador independente dos dados de conta e de uso. **Falta confirmar se o DPA foi assinado** |
| OpenStreetMap | IP do visitante | Navegador pede as imagens do mapa | Sem contrato; proposta: tratamento próprio do serviço |
| Google Fonts | IP do visitante | Navegador pede as fontes (`index.html`) | Sem contrato. **Evitável:** hospedar as fontes no próprio site eliminaria esse envio |
| Open-Meteo e Nominatim (OpenStreetMap) | Coordenadas e nomes de lugar enviados pela API | Chamadas do servidor | Sem dado pessoal identificado no código; revisar se os fluxos de incidente forem abertos |

## 3. Papéis: proposta a confirmar

"Operada pela Andrade Systems" descreve quem mantém a plataforma. Na LGPD, **operador** tem sentido próprio: quem trata dados em nome de um controlador, que decide as finalidades (art. 5º, VI e VII). Os dois sentidos não devem ser confundidos, por isso a página não afirma o papel jurídico.

| Fluxo | Quem decide hoje, pelo que está no repositório | Proposta a confirmar |
|---|---|---|
| Contas e auditoria da área restrita | Andrade Systems | Andrade Systems como **controladora**, enquanto não houver cliente institucional |
| Logs técnicos e backups | Andrade Systems | Andrade Systems como controladora; Railway como operador |
| Dados de conta e uso da Railway | Railway | Railway como controlador independente (DPA, seção 13) |
| Futuro uso por um órgão ou cliente | Não existe contrato | Cliente como controlador e Andrade Systems como operadora, **somente** com contrato e instruções formais |

**Decisão do proprietário:** se a Andrade Systems deve figurar como operadora em sentido jurídico, é preciso identificar o controlador e o instrumento que o sustenta. Nada no repositório indica que exista.

## 4. Transferência internacional

**Fatos:**
- A região do Railway é nos Estados Unidos, e o Railway não oferece região na América do Sul.
- O DPA prevê cláusulas contratuais da União Europeia, do Reino Unido e da Suíça, além do Data Privacy Framework. **Não menciona Brasil nem LGPD.**
- A [Resolução CD/ANPD nº 19/2024](https://www.mattosfilho.com.br/?p=115485) aprovou o regulamento e as cláusulas-padrão brasileiras, com adequação até [23/08/2025](https://www.mayerbrown.com/pt/insights/publications/2025/08/end-of-grace-period-implementation-of-brazils-standard-contractual-clauses-in-international-transfers-of-personal-data).

**A avaliar com orientação jurídica:**
1. Se a hospedagem caracteriza transferência internacional neste caso, e quem é o exportador.
2. Qual mecanismo do art. 33 da LGPD se aplica. As cláusulas do DPA não equivalem automaticamente às cláusulas da ANPD.
3. Se o Railway aceita incorporar as cláusulas-padrão da ANPD.
4. Se a alternativa é hospedar os dados pessoais no Brasil.

Nenhum mecanismo foi escolhido, e o aviso não afirma nenhum.

## 5. Lacunas técnicas que afetam o aviso

- **Eliminação de dados:** não há função de exclusão de conta. Um pedido de eliminação hoje exigiria operação manual no banco, e os dados permaneceriam nos backups por até 89 dias.
- **Retenção:** não há rotina de expurgo para contas, auditoria ou focos. Um prazo definido juridicamente precisará de implementação.
- **Sessão:** o token fica no `localStorage`, acessível a scripts da própria página. A CSP limita scripts à própria origem.

## 6. Campos pendentes do proprietário

Definidos em `ignis-fire-watch/src/content/privacyNotice.ts`:

1. Controlador: identificação e papéis confirmados.
2. Encarregado (DPO).
3. Hipóteses legais por finalidade.
4. Prazos de retenção.
5. Mecanismo de transferência internacional.
6. Data de vigência.

**Definido pelo proprietário em 06/11/2026:** o canal institucional de contato e privacidade é `contato@andradesystems.com.br`, também usado para o exercício dos direitos do titular. Esse canal **não** é a indicação formal de um encarregado.

Depois de preenchê-los, é preciso marcar `PRIVACY_NOTICE_APPROVED = true`. Antes disso, o build de produção não exibe a página.
