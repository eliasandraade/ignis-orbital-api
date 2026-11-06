# IGNIS Orbital: rascunho do aviso de privacidade

**Rascunho para aprovação do proprietário. Não está publicado e não é parecer jurídico.** Os fatos abaixo foram conferidos no código e na infraestrutura em 05/11/2026. Os campos entre colchetes dependem do proprietário.

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

**Endereço IP.** O IP é usado para limitar tentativas de acesso. O provedor de hospedagem também pode registrá-lo em logs técnicos.

**Armazenamento no navegador.** Depois do login, o navegador guarda o token de sessão e os dados básicos do usuário. Um cookie guarda a preferência de exibição da barra lateral. Não usamos cookies de publicidade.

**Terceiros.**
- Railway hospeda a aplicação e o banco de dados, na região Leste dos Estados Unidos. [Texto sobre transferência internacional, conforme D-1.]
- OpenStreetMap fornece as imagens do mapa. O navegador as solicita diretamente, e o serviço recebe o endereço IP do visitante.

**Denúncias.** O recebimento de denúncias está desativado. Em caso de incêndio, acione o Corpo de Bombeiros (193) ou a Defesa Civil (199).

**Comunicação com órgãos.** A plataforma não envia comunicações automáticas a órgãos públicos.

**Retenção.** [Prazos.]

**Direitos do titular.** Você pode solicitar confirmação, acesso, correção e eliminação pelo canal [canal], nos termos da LGPD.

**Atualização.** Versão de [data].

## Depois de aprovar

Publicar como página estática `/privacidade`, com link no rodapé e na tela de login, em um PR próprio do `ignis-fire-watch`. O texto deve ser revisto antes de abrir as denúncias, pois elas tratam dados pessoais que este rascunho não cobre.
