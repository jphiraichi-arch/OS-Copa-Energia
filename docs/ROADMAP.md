# Roadmap da Fase B (notas de desenho, prompt 40)

Nada aqui está construído. Para cada recurso: o que precisa, o que o código de hoje já
oferece, o que bloquearia ou pede migração, riscos e um tamanho estimado (pequeno,
médio, grande). Escopo continua sendo só manutenção (TI fora).

Estado de referência (commit do prompt 39): migrações até a `0018` (prompt 38), papéis
usuario / manutencao / admin, filiais permitidas (prompt 34), fila de e-mails
transacional (prompt 32), especialidade (prompt 37), SLA (prompt 38), guia rápido
(prompt 39). Os prompts 41 (motivos de cancelamento, Sem gasto na criação) e 42
(visualizações) chegaram depois e não estão refletidos aqui.

## Resumo

| Recurso | Precisa | Bloqueios / migração | Tamanho |
|---|---|---|---|
| B1 Fotos | tabela `os_fotos`, abstração de armazenamento, upload do Flet, tela | rota de upload, segredo de upload, limpeza EXIF no servidor (biblioteca nova), redimensionar no cliente não existe pronto no Flet | grande |
| B2 Comentários e notas internas | tabela `os_comentarios` (tipo comentario/nota), serviço, seção no Detalhe | nenhuma; modelo do usuario precisa excluir notas | médio |
| B3 Aviso ao solicitante | e-mail do usuario + consentimento, gatilho nas transições | regra do prompt 32 (só manutenção/admin) e LGPD | médio |
| B4 Confirmação do solicitante | status/transição de reabrir, tarefa de confirmação automática, taxa de reabertura | CONCLUIDA é final; `situacao_em` e o SLA não preveem reabertura | grande |
| B5 Planos preventivos | tabela `planos_preventivos`, origem 'preventiva', agendador | CHECK de `origem`, consultas que assumem 2 origens | grande |
| B6 QR codes | tabela de local/ativo primeiro | não há equipamento nem local desde 21/11 | médio (depois da tabela) |
| Especialidade nas notificações | filtro em `enfileirar_nova_solicitacao` | nenhum (tabela `usuario_especialidades` pronta) | pequeno |

## B1. Fotos opcionais

**Precisa**
- Tabela `os_fotos`: id, os_id, enviada_por_id, enviada_em, chave_armazenamento,
  tipo_mime (verificado), largura, altura, tamanho_bytes, sha256, excluida_em (exclusão
  lógica pelo administrador). No máximo 5 por OS (regra no serviço e contagem com trava).
- Abstração de armazenamento (`services/armazenamento.py`): `salvar(chave, arquivo)`,
  `abrir(chave)`, `apagar(chave)`, `url_temporaria(chave)`; implementações 'pasta local'
  e 'S3 compatível' (boto3, como no backup do prompt 36). Configurada por variáveis em
  `config.py` (prompt 33).
- Fluxo no Flet 1.1 (https://flet.dev/docs/services/filepicker,
  https://flet.dev/docs/types/filepickerfile, https://flet.dev/docs/types/filepickeruploadfile,
  https://flet.dev/docs/fastapi/app):
  - `FilePicker.pick_files(file_type=IMAGE, allow_multiple=True, ...)`; na web o
    navegador só abre o seletor dentro do clique: usar a ação `ft.PickFiles(...)` no
    botão e tratar `on_result` (a doc avisa que chamar `pick_files()` no `on_click`
    falha no Safari).
  - Na web `FilePickerFile.path` é sempre `None`; o arquivo chega ao servidor por
    `FilePicker.upload([FilePickerUploadFile(name, upload_url=page.get_upload_url(...))])`
    (PUT para o endpoint `/upload` do app Flet), com eventos `on_upload` de progresso.
  - O app montado precisa de `upload_dir` (pasta temporária do servidor),
    `max_upload_size` e `secret_key` em `flet.fastapi.app(...)` (ou `FLET_SECRET_KEY`)
    para assinar as URLs de upload. Hoje `osapp/asgi.py` não passa nenhum dos três:
    o endpoint de upload existe mas não está configurado.
  - Redimensionar no cliente para ~1600 px: não há recurso documentado para isso; o
    mais perto é `compression_quality` em `pick_files` (a doc não diz se age no
    navegador). Sem confirmação, o caminho seguro é redimensionar NO SERVIDOR depois do
    upload (o limite `max_upload_size` evita arquivos enormes). Câmera: a doc lista um
    controle Camera; não verificado para web.
- No servidor, depois do upload: conferir o tipo pelo conteúdo (assinatura JPEG/PNG/
  WebP/HEIC), decodificar e regravar a imagem (isso remove EXIF, inclusive GPS) e
  redimensionar; biblioteca nova (Pillow, e `pillow-heif` para fotos de iPhone). Mover
  do `upload_dir` para o armazenamento e apagar o temporário.
- Visível a todos os papéis (inclusive usuario): servir por URL temporária ou por uma
  rota que confere a permissão de ver a OS (o mesmo `_carregar_visivel`).

**Apoio no código atual**: camada de serviço com permissão por OS, exclusão lógica
(prompt 24) como modelo para excluir foto, config central (prompt 33), boto3 já usado no
backup.

**Bloqueios / riscos**: armazenamento de dados pessoais (rostos, placas) e LGPD;
custo de armazenamento; fotos HEIC; o upload do Flet passa pelo mesmo processo (um só
worker): limitar tamanho e quantidade; o modelo reduzido do usuario passa a ter um campo
novo (lista de fotos) — testar a serialização.

**Tamanho**: grande.

## B2. Comentários e notas internas

**Precisa**: tabela `os_comentarios` (id, os_id, autor_id, criado_em, tipo
'comentario' | 'nota_interna', texto, excluido_em, excluido_por_id); só inserção (sem
edição); exclusão lógica só pelo administrador. Serviço com `listar_comentarios` que,
para o papel usuario, filtra `tipo = 'comentario'` NA CONSULTA (como hoje
`_consulta_solicitante` só lê as colunas permitidas), e `listar_comentarios_internos`
só para manutenção da filial e administrador. Seção 'Comentários' no Detalhe e no
modelo reduzido do usuario.

**Apoio**: `OsVisaoSolicitante` / `ResumoSolicitante` já separam o que o usuario recebe;
os_eventos já é só inserção; rótulos e histórico (prompt 26).

**Bloqueios / riscos**: as notas internas nunca podem entrar em `OsVisaoSolicitante`
(teste de serialização como o do prompt 37); notificação de comentário é outro recurso
(B3). Texto livre: limite de tamanho e o mesmo tratamento de caracteres.

**Tamanho**: médio.

## B3. Aviso ao solicitante na mudança de status

**Precisa**: e-mail para o papel usuario (hoje proibido pela regra do prompt 32), com o
mesmo fluxo de consentimento (código de confirmação, opt-in, remover), e um gatilho em
`_mudar_status` gravando na fila (`email_fila`, tipo novo `mudanca_status`, CHECK do tipo
alterado por migração). Conteúdo sem custo, previsto, realizado, prioridade nem executor
(o mesmo cuidado do corpo da nova solicitação).

**Apoio**: fila transacional, trabalhador e limites prontos (prompts 32/33); o serviço de
consentimento já existe, só restrito por papel (`PAPEIS_COM_EMAIL`).

**Bloqueios / riscos**: LGPD — o usuario é outra população (muitas pessoas, de várias
áreas); a empresa precisa decidir a base legal (consentimento opt-in, como hoje) e
atualizar o aviso de privacidade; o SMTP precisa funcionar na hospedagem (o plano
gratuito do Render bloqueia, prompt 32); volume de e-mails maior.

**Tamanho**: médio.

## B4. Confirmação do solicitante depois de Concluída

**Precisa**: depois de CONCLUIDA, o solicitante responde Sim (fica concluída) ou Não com
motivo (volta para EM_EXECUCAO); sem resposta em 3 dias, confirmação automática;
taxa de reabertura no relatório. Novas colunas (confirmada_em, confirmacao_automatica)
ou eventos novos (CONFIRMACAO, REABERTURA), uma transição nova em `status.TRANSICOES`
(`REABRIR: CONCLUIDA -> EM_EXECUCAO, SOMENTE_SOLICITANTE`) e uma tarefa agendada (pode ser
o trabalhador da fila do prompt 32, com uma rodada a cada hora).

**Bloqueios / migração**:
- Hoje CONCLUIDA é final (`status.FINAIS`): só o administrador edita. Reabrir muda essa
  regra e a de 'Sem gasto' (prompt 31: o realizado foi gravado na conclusão; ao reabrir,
  o realizado volta a ser editável? os itens realizados ficam?).
- `linha_do_tempo.situacao_em` (prompt 25) não prevê saída de CONCLUIDA: com uma
  reabertura, o `inicio` passaria a ser o da reabertura e `concluida_em` ficaria com a
  conclusão antiga. Precisa de regra explícita (última conclusão válida; início = o
  primeiro início não desfeito) e testes com meses passados, para os relatórios antigos
  não mudarem.
- SLA (prompt 38): o prazo de solução é medido até a conclusão; com reabertura, decidir
  se vale a primeira conclusão ou a última (recomendação: a última, e contar reaberturas
  à parte).

**Tamanho**: grande.

## B5. Planos preventivos

**Precisa**: tabela `planos_preventivos` (titulo, descricao, filial_id, especialidade_id,
itens previstos padrão, tempo previsto, frequencia_dias, antecedencia_dias, base
'ultima_conclusao' | 'calendario', proxima_data, ativo); gerador que cria a OS com
`origem = 'preventiva'` na data (próxima data pela última conclusão do plano ou por um
calendário fixo); só calendário corrido (sem dias úteis). Tela de planos (administrador).

**Bloqueios / migração**:
- CHECK `origem IN ('solicitacao', 'manutencao')` em `ordens_servico` (migração) e
  `ordens.ORIGENS`, `ui/rotulos.ORIGEM` (há um assert que exige o mesmo conjunto), o
  argumento `reclassificar-origem` da CLI.
- Relatórios filtram `origem == "solicitacao"` em `ordem_servico_repo.py`
  (`tempos_de_solicitacoes`, `solicitacoes_ate`, `marcos_ate`, `abertas_de_solicitacoes`):
  preventivas ficam fora sem mudança — o que é o desejado; só incluir sob pedido.
- SLA (prompt 38): preventivas não têm urgência: ficam sem prazo, como as de manutenção.
- Agendador: reaproveitar o trabalhador por processo (prompt 32) com uma trava no banco
  (como a reserva com SKIP LOCKED) para dois processos não gerarem a mesma OS; ou um
  job agendado separado (como o backup do prompt 36).
- Numeração (`OsSequencia`) já é por filial e ano: serve.

**Tamanho**: grande.

## B6. QR codes (depois da TI)

QR codes costumam identificar um ativo ou um local. O cadastro de equipamento saiu em
21/11 (prompt 21: os itens de custo descrevem o que foi atendido). Antes do QR precisa
existir uma tabela de locais ou ativos (filial, código, nome, ativo), um campo opcional
na OS e a tela de cadastro; o QR só codifica um link para '/os/nova?local=<código>'
(a guarda de rotas já pede login). O app ainda não lê parâmetros de rota com '?'
(`rotas._caminho` descarta a query).

**Tamanho**: médio, depois da tabela de locais.

## Especialidade nas notificações (depois)

`usuario_especialidades` (prompt 37) já existe. Basta um filtro em
`notificacoes.enfileirar_nova_solicitacao`: um usuário com especialidades só recebe a
OS dessas especialidades. Mas a especialidade da OS é escolhida pela manutenção ao
assumir, DEPOIS da abertura: na hora do aviso de nova solicitação ela ainda não existe.
Precisaria que o solicitante escolha a especialidade (hoje ele não a vê) ou um aviso
novo quando a especialidade é definida.

**Tamanho**: pequeno a médio, conforme essa decisão.

## Acoplamentos que dificultam (refatorações propostas, NÃO aplicadas)

| # | Onde | Problema | Menor refatoração proposta |
|---|---|---|---|
| R1 | `ordem_servico_repo.py` (4 consultas) | `OrdemServico.origem == "solicitacao"` escrito à mão | Uma constante (`ORIGEM_SOLICITACAO`) e uma função `_e_solicitacao()` no repositório. |
| R2 | `models/ordem_servico.py` | CHECK de origem com a lista fixa | Gerar o CHECK a partir de uma tupla única (como `notificacao._lista`), para B5 mudar num lugar só (a migração continua necessária). |
| R3 | `ui/theme.py` `cores_status` e `ordem_servico_repo.py:105/165` | status como texto ('ABERTA', 'CANCELADA') fora de `services/status.py` | Usar as constantes de `services/status.py`. |
| R4 | `services/linha_do_tempo.situacao_em` | supõe que CONCLUIDA nunca é deixada | Antes de B4: explicitar 'última conclusão vale; reabertura apaga a conclusão anterior' com testes. |
| R5 | `cli.py` `reclassificar-origem` | `choices=("solicitacao","manutencao")` fixo | Usar `ordens.ORIGENS`. |
| R6 | `osapp/asgi.py` | o app Flet é montado sem `upload_dir`/`secret_key`/`max_upload_size` | Ao fazer B1: configurar os três por `config.py` (sem isso, o endpoint `/upload` do Flet está ativo e sem limite). |

Paro aqui: nenhuma dessas mudanças foi aplicada.

## Perguntas para a empresa

1. Fotos: onde guardar (provedor S3 de quem? servidor da empresa?), por quanto tempo, e
   quem pode apagar? Fotos com pessoas exigem aviso de privacidade?
2. Avisos ao solicitante: base legal e texto do consentimento (LGPD); e-mail
   corporativo de todos os solicitantes existe?
3. Confirmação: 3 dias corridos ou úteis? Quem pode reabrir depois da confirmação
   automática? A reabertura conta no SLA de solução?
4. Preventivas: entram nos indicadores (taxa de conclusão, SLA) ou ficam só num
   relatório próprio?
5. QR: o que o código identifica (sala, máquina, área)? Quem cadastra e imprime?
6. Notificação por especialidade: o solicitante escolheria a especialidade ao abrir?
