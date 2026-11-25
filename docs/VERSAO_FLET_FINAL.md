# Versão final em Flet (tag `v-flet-final`, 25/11/2026)

Documento para a equipe da versão 2.0. A versão em Flet foi apresentada em 25/11/2026 e
fechada nesse dia (decisão da empresa). A 2.0 troca a interface por FastAPI + um frontend
web e reaproveita modelos, serviços, migrações e testes. As regras de negócio continuam
valendo: `docs/REGRAS.md` (obrigatório) e o histórico em `docs/ESTADO.md`.

## O que a versão contém

Papéis (só `papel`, um por usuário; regras em `services/permissoes.py` e
`services/ordens.py`):

| Papel | O que faz |
|---|---|
| `usuario` | Abre solicitações (título, descrição, urgência) na própria filial; acompanha as próprias e cancela a própria enquanto Aberta. Nunca recebe custo nem nada derivado de custo. |
| `manutencao` | Vê as OS das filiais permitidas; cria OS completa; assume, inicia, desfaz início, altera e conclui (itens previstos e realizados, tempo, nota para o solicitante). |
| `admin` | Tudo em todas as filiais; usuários (filiais permitidas, senha temporária, desativar), especialidades, SLA, motivos de cancelamento, Lixeira (excluir e restaurar), relatórios. |

Funcionalidades:

- Ordens de Serviço com ciclo Aberta -> Em execução -> Concluída (ou Cancelada), histórico
  de eventos (`os_eventos`) e trava otimista (`versao`).
- Itens de custo por fase (previsto, realizado) com categorias, ou 'Sem gasto' na fase;
  dinheiro em centavos inteiros e Decimal.
- Solicitações com urgência, especialidade, prazos de SLA gravados na abertura e o
  indicador 'Visualizada' (quem da manutenção abriu e quando).
- Busca sem acento e sem maiúsculas (texto, itens e número da OS); filtros por status,
  origem, especialidade e 'Não visualizadas'.
- Lixeira (exclusão lógica; nada é apagado do banco).
- Relatório mensal com mês selecionado e acumulado do ano, tempos (início e solução),
  SLA, visualização; relatório de tempos.
- Login com proteção por login e por IP, senha temporária com troca obrigatória (também
  conferida nos serviços desde este fechamento), 'Lembrar de mim por 7 dias' (token
  rotativo, guardado só como hash) e 'Aparelhos conectados'.
- Guia rápido por tela e papel (`docs/guia/guia.yaml`, botão '?').
- `/saude` para a hospedagem; alertas de erro grave (log; e-mail desligado, abaixo);
  backups criptografados (`scripts/backup.py`, `docs/BACKUP.md`).

## O que está escondido: e-mail

O e-mail (avisos de nova solicitação, códigos de confirmação, alertas de erro grave por
e-mail) está escondido na interface e desligado por configuração. Volta na 2.0 por uma
API HTTPS de e-mail.

- Interface: saíram a seção do Perfil, a linha e o cartão de e-mail na tela de usuário e
  a tela 'Fila de e-mails' (a rota `/perfil/fila-email` não existe mais: vai para o
  início, como qualquer rota desconhecida). O guia não fala de e-mail.
- Configuração: `OS_EMAIL_HABILITADO` (padrão `0`). Com `0` o trabalhador da fila não
  sobe (uma linha INFO na partida), nada entra em `email_fila` (avisos, códigos,
  alertas) e nenhuma conexão é tentada; os erros graves ficam no log do servidor.
- Continuam no código, com testes (que rodam com `OS_EMAIL_HABILITADO=1`):
  `models/notificacao.py`, `services/notificacoes.py`, `services/email_mensagem.py`,
  `services/fila_email.py` (fila transacional, tentativas, limpeza) e os alertas de
  `services/alertas.py`.

Como religar (na 2.0, depois de trocar o envio SMTP pela API HTTPS):

1. Trocar o envio em `services/fila_email.py` (hoje `smtplib`) pelo cliente da API.
2. Refazer as telas: e-mail e notificações no Perfil, cartão no usuário, fila para o
   administrador (as regras estão nos serviços e em `docs/REGRAS.md`, 'Notificações por
   e-mail').
3. `OS_EMAIL_HABILITADO=1` e as variáveis do provedor no ambiente.

## O que deliberadamente NÃO foi executado

- O reinício do banco ('banco limpo', prompts 44 e 45) NÃO foi executado e o código
  desses prompts NÃO está nesta versão.
  - O prompt 44 (número da OS = código da filial + sequencial, ex. `10070001`; remoção do
    código antigo) está pronto num ramo local, `prompt-44-banco-limpo` (commit
    `d47617f`), sem migração: ele só funciona com o reinício do banco do prompt 45.
  - O prompt 45 (uma migração base, comando `resetar-banco`, seed novo) não foi feito.
  - Por isso esta versão continua com a numeração `{filial}-{ano}-{sequência}` e com as
    20 migrações (`alembic current` em produção: `0020`).
- Nenhum deploy foi feito por este trabalho; o responsável implanta.
- O contêiner não roda migrações na partida (desde 25/11/2026): `alembic upgrade head` é
  feito à mão, depois de um backup (`docs/NUVEM.md`).

## Camadas: o que reaproveitar e o que trocar

| Camada | Pasta | Na 2.0 |
|---|---|---|
| Modelos (SQLAlchemy 2, ORM) | `src/osapp/models/` | Reaproveitar. |
| Repositórios | `src/osapp/repositories/` | Reaproveitar. |
| Serviços (regras e permissões; DTOs sem custo para `usuario`) | `src/osapp/services/` | Reaproveitar. Os endpoints FastAPI chamam estas funções; nenhuma regra no endpoint. |
| Migrações (Alembic) | `migrations/` | Reaproveitar (ou a migração base do prompt 45, se o reinício for feito). |
| Configuração, banco, busca, formatação, saúde, CLI, seed | `src/osapp/config.py`, `db.py`, `busca.py`, `formatacao.py`, `saude.py`, `cli.py`, `seed.py` | Reaproveitar. |
| Testes | `tests/` | Reaproveitar os de serviço, modelo e regra; os de `ui/` servem de especificação do comportamento das telas. |
| Interface Flet | `src/osapp/ui/`, `src/osapp/main.py`, `src/osapp/asgi.py` (montagem do Flet) | Trocar. Funções puras úteis como referência: `ui/rotas.py`, `ui/secoes.py`, `ui/rotulos*.py`, `ui/historico.py`, `ui/leitura.py`, `ui/navegacao.py`. |

## Limites conhecidos

- Sessões de interface ficam na memória de um único processo (um uvicorn): sem várias
  instâncias até a 2.0 (API sem estado).
- Plano gratuito do Render: sem SMTP, sem pre-deploy, sem cron; tarefas de limpeza
  (`limpar-tentativas`, `limpar-sessoes-lembradas`) precisam ser agendadas fora do app.
- Testado em Chromium (Playwright) a 390, 800 e 1280 px; não em aparelhos reais.
- Sem exportação PDF/Excel; sem integração SAP (`numero_sap` existe, sem uso).
- `flet test` (testes de integração do Flet) não roda aqui (precisa de numpy e do app de
  teste do Flutter); a interface foi conferida no navegador.

## Erros abertos (para a 2.0)

- Se o administrador mudar a filial de uma OS em execução, o executor (da filial antiga)
  deixa de vê-la; só o administrador consegue concluí-la ou desfazer o início. É
  comportamento das regras atuais; precisa de decisão de negócio.
- `inicio_realizado` pode ser anterior à criação da OS (não há regra); precisa de
  decisão de negócio sobre ordens registradas depois do serviço.
- O layout de Custos (tabela ou cartões) é escolhido ao abrir o Detalhe; girar o celular
  só muda ao recarregar. Específico do Flet: a interface será trocada.
- Se a sessão expirar com um formulário aberto, o que foi digitado é perdido. Específico
  da interface Flet (sessão na memória).
- O teclado numérico de alguns celulares pode não ter vírgula (o tipo de teclado é só
  uma sugestão ao navegador). Específico da interface.
