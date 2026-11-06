# IGNIS Orbital: rascunho do aviso de privacidade

**Rascunho para aprovação do proprietário. Não está publicado e não é parecer jurídico.** O texto de trabalho agora está em `ignis-fire-watch/src/content/privacyNotice.ts` (PR web #9), e os fatos e os papéis, em [PRIVACY-DATA-MAP.md](PRIVACY-DATA-MAP.md). Corrigido em 06/11/2026: não há cookie em uso, e o Google Fonts também recebe o IP do visitante. Os campos entre colchetes dependem do proprietário.

## Lacunas a preencher antes de publicar

| Campo | Quem define |
|---|---|
| Controlador: razão social, CNPJ e endereço | Proprietário |
| Canal do titular e encarregado (DPO) | Proprietário |
| Bases legais por finalidade | Proprietário, com orientação jurídica |
| Prazos de retenção de contas e auditoria | Proprietário (hoje não há expurgo automático definido) |
| Transferência internacional (decisão D-1) | Proprietário |

## Texto proposto

**Quem somos.** O IGNIS Orbital é operado por [controlador], [CNPJ], [endereço].

**Mapa público.** O mapa público não exige conta. Os focos de calor exibidos vêm de fontes públicas (INPE) e não são dados pessoais.

**Contas administrativas.** Para quem recebe acesso, tratamos nome, e-mail, papel, senha em formato de hash e data do último acesso, com a finalidade de autenticar e controlar o acesso.

**Registros de auditoria.** Ações administrativas ficam registradas com o nome de quem agiu, a ação, o item afetado e detalhes técnicos, para segurança e rastreabilidade.

**Endereço IP.** O IP é usado para limitar tentativas de acesso e aparece nos registros técnicos da aplicação, guardados por até 30 dias no provedor de hospedagem.

**Armazenamento no navegador.** Depois do login, o navegador guarda o token de sessão e os dados básicos do usuário. A plataforma não usa cookies.

**Terceiros.**
- Railway hospeda a aplicação e o banco de dados, na região Leste dos Estados Unidos. [Texto sobre transferência internacional, conforme D-1.]
- OpenStreetMap fornece as imagens do mapa e Google Fonts, as fontes do site. O navegador as solicita diretamente, e esses serviços recebem o endereço IP do visitante.

**Denúncias.** O recebimento de denúncias está desativado. Em caso de incêndio, acione o Corpo de Bombeiros (193) ou a Defesa Civil (199).

**Comunicação com órgãos.** A plataforma não envia comunicações automáticas a órgãos públicos.

**Retenção.** [Prazos.]

**Direitos do titular.** Você pode solicitar confirmação, acesso, correção e eliminação pelo canal [canal], nos termos da LGPD.

**Atualização.** Versão de [data].

## Depois de aprovar

Preencher os campos e marcar a aprovação no PR web #9, que já traz a página `/privacidade` e os links. O texto deve ser revisto antes de abrir as denúncias, pois elas tratam dados pessoais que este rascunho não cobre.
