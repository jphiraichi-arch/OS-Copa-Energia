# Checklist de entrada em produção (para a TI da empresa)

O Sistema de Ordens de Serviço é um app web (Flet, servidor Python ASGI/uvicorn) usado em
celulares e tablets pela internet (4G). Este documento lista o que precisa estar pronto
antes de abri-lo para uso. Marque cada item e guarde quem conferiu e quando.

Nenhum valor secreto aparece aqui: só os **nomes** das variáveis de ambiente.

---

## 1. HTTPS

- [ ] O app só é acessível por **HTTPS**, com certificado válido.
- [ ] Toda requisição HTTP (porta 80) é **redirecionada** para HTTPS (301/308).
- [ ] **HSTS** configurado no proxy, por exemplo
      `Strict-Transport-Security: max-age=31536000; includeSubDomains`.
      (O app não envia esse cabeçalho; ele deve vir do proxy.)
- [ ] O contêiner do app (porta 8000) **não** fica acessível diretamente pela internet:
      só o proxy chega nele.

## 2. Proxy reverso e WebSocket

Cada pessoa conectada mantém **um WebSocket aberto** com o servidor durante toda a sessão
(é assim que o Flet desenha as telas). Por isso:

- [ ] O proxy encaminha **WebSocket** (cabeçalhos `Upgrade` e `Connection`), no mesmo
      endereço do app (rota `/ws` e demais).
- [ ] O **tempo de ociosidade** do proxy para conexões (WebSocket e HTTP) é **pelo menos
      igual** ao tempo de sessão do app (`OS_SESSAO_TIMEOUT_MIN`, padrão 30 minutos), ou
      seja, 1800 s ou mais. Um tempo menor desconecta quem está preenchendo uma OS.
- [ ] **Uma única instância** do app (as sessões ficam na memória do processo). Se houver
      balanceador, ele precisa de afinidade de sessão; o recomendado é uma instância só.
- [ ] O proxy envia o IP real do cliente em **`X-Forwarded-For`** e o esquema em
      **`X-Forwarded-Proto`**. Ele deve **acrescentar** o IP de quem conectou nele (não
      repassar o cabeçalho do cliente sem acrescentar).

### Como o app descobre o IP do cliente

O próprio app resolve o IP (`osapp/rede.py`); o uvicorn roda com `--no-proxy-headers`.
Os cabeçalhos só são lidos quando a conexão direta vem de um endereço em
**`OS_PROXIES_CONFIAVEIS`** (padrão: `10.0.0.0/8`; loopback sempre incluído):

1. `True-Client-Ip` (Render, Cloudflare), se for um IP válido;
2. senão, `X-Forwarded-For` lido **da direita para a esquerda**, pulando os endereços
   confiáveis: o primeiro não confiável é o cliente. A entrada mais à esquerda nunca é
   usada só por ser a primeira (o cliente pode escrevê-la);
3. senão, o endereço da conexão direta.

- [ ] Se o proxy da empresa não estiver em `10.0.0.0/8`, colocar o endereço (ou rede) de
      onde ele se conecta ao app em `OS_PROXIES_CONFIAVEIS` (vários separados por vírgula).
      `*` é recusado.
- [ ] Se o proxy da empresa **não** sobrescreve `True-Client-Ip`, ele deve **remover** esse
      cabeçalho quando vier do cliente (senão o cliente escolhe o próprio IP).
- O cabeçalho `Forwarded` (RFC 7239) não é lido.
- Para conferir depois de implantar: `OS_DEPURAR_CABECALHOS_IP=1` grava no log, por
  pedido, os cabeçalhos de encaminhamento, o endereço direto e o IP escolhido. **Grava IPs
  crus**: ligar só por alguns minutos e desligar.

Se o IP do cliente não puder ser determinado, o app usa um limite comum chamado
`desconhecido` e registra um aviso no log ("IP do cliente desconhecido").

## 3. Variáveis de ambiente (nomes)

| Variável | Obrigatória | Para quê |
|---|---|---|
| `OS_DATABASE_URL` | sim | Conexão com o PostgreSQL (contém senha: tratar como segredo). |
| `OS_HMAC_SEGREDO` | sim | Segredo do HMAC das tentativas de login. Mínimo de 32 caracteres aleatórios, diferente em cada ambiente. Sem ela o app não inicia. Trocá-la zera, na prática, os contadores de tentativas. |
| `OS_PROXIES_CONFIAVEIS` | não (padrão `10.0.0.0/8`) | Endereço(s) do proxy reverso (item 2). |
| `OS_LIMITE_FALHAS_IP` | não (padrão 100) | Falhas de login de um mesmo IP em 15 min antes da espera por IP. |
| `OS_ATRASO_MAX_IP_SEGUNDOS` | não (padrão 60) | Teto da espera por IP. |
| `OS_DEPURAR_CABECALHOS_IP` | não (desligada) | `1` grava cabeçalhos de encaminhamento no log (temporário). |
| `OS_TZ` | não | Fuso das datas (padrão `America/Sao_Paulo`). |
| `OS_SESSAO_TIMEOUT_MIN` | não | Minutos de inatividade até sair (padrão 30). |
| `OS_LOG_LEVEL` | não | Nível do log (padrão `INFO`). |
| `OS_SEED_SENHA` | só na primeira subida | Senha inicial do `admin` criado pelo seed. Remover depois. |
| `OS_SEED_EXEMPLOS` | **não usar em produção** | Cria usuários fictícios de exemplo. |
| `PORT` | não | Porta do servidor no contêiner (padrão 8000). |
| `OS_DB_RECICLAR_CONEXAO_SEGUNDOS` | não (padrão 300) | Renovação das conexões do pool (prompt 33). |
| `OS_DB_TIMEOUT_CONEXAO_SEGUNDOS` | não (padrão 10) | Tempo máximo para abrir conexão com o banco (prompt 33). |
| `OS_CABECALHO_IP_CLIENTE` | não (vazio) | Cabeçalho com o IP do cliente que o proxy **sobrescreve** (ex.: `True-Client-Ip`). Antes do prompt 33 esse cabeçalho era usado sempre; agora só quando configurado. |
| `OS_ALERTAS_EMAIL` | não (padrão 1) | `0` deixa os alertas de erro grave só no log (prompt 33). |

Lista completa e única: docs/CONFIGURACAO.md (e `.env.example`).
| `OS_SMTP_HOST` | só para e-mail | Servidor SMTP da conta remetente (prompt 32). Sem as variáveis de SMTP o app funciona e os avisos ficam pendentes na fila (um aviso no log por hora). |
| `OS_SMTP_PORTA` | só para e-mail | 587 (STARTTLS) ou 465 (SSL). |
| `OS_SMTP_TLS` | só para e-mail | `starttls` ou `ssl`. (`nenhum` só é aceito com host `localhost`, para o coletor local de testes.) |
| `OS_SMTP_USUARIO` | só para e-mail | Usuário da conta remetente (vai junto com a senha). |
| `OS_SMTP_SENHA` | só para e-mail | Senha ou senha de aplicativo da conta remetente. **Segredo.** Nunca aparece em log. |
| `OS_SMTP_REMETENTE` | só para e-mail | Endereço do remetente (From), por exemplo uma caixa de serviço da empresa. |
| `OS_BASE_URL` | só para e-mail | Endereço público do app, para o link 'Abrir a OS' (ex.: `https://os.empresa.com.br`). Sem ela o e-mail diz só o número da OS. |
| `OS_EMAIL_MAX_TENTATIVAS` | não (padrão 6) | Tentativas de envio antes de a mensagem ficar como 'falhou'. |

- [ ] Segredos guardados no cofre/gerenciador de segredos da plataforma, nunca no git.

### E-mail (prompt 32): o que pedir à TI

- [ ] **Conta remetente** da empresa, só para o sistema (uma caixa de serviço, por exemplo
      `sistema-os@<domínio da empresa>`), com SMTP autenticado (porta 587 com STARTTLS ou 465
      com SSL). Nunca uma conta pessoal (Gmail ou outra).
- [ ] **SPF** do domínio do remetente incluindo o servidor que envia (o do provedor de
      e-mail da empresa).
- [ ] **DKIM** assinado pelo provedor para o domínio do remetente.
- [ ] **DMARC** publicado para o domínio (no mínimo `p=none` com relatórios no início;
      `quarantine`/`reject` depois de conferir que SPF e DKIM passam).
- [ ] **A hospedagem permite SMTP de saída.** No Render, serviços web do plano **gratuito**
      não podem abrir conexões de saída nas portas 25, 465 e 587 (documentação
      https://render.com/docs/free, em vigor desde 26/09/2025); a porta 25 é bloqueada em todos
      os planos. Ou seja: no `render.yaml` atual (`plan: free`) nenhum e-mail sai; é preciso um
      plano pago, ou outra hospedagem que permita 587/465. Conferir na hospedagem definitiva
      antes de configurar as variáveis.
- [ ] Teste: cadastrar e confirmar um e-mail no Perfil, abrir uma solicitação com outro
      usuário e ver a mensagem chegar; em Perfil > 'Fila de e-mails' (administrador) as
      contagens e os erros.
- [ ] **Retenção** (dados pessoais e texto das OS): agendar uma vez por dia
      `python -m osapp.cli limpar-fila-email` (apaga enviados e cancelados com mais de 30 dias
      e falhos com mais de 90).

## 4. Banco de dados

- [ ] **Backup automático** diário do PostgreSQL, com retenção definida pela empresa.
- [ ] **Restauração testada**: restaurar um backup em um banco separado, subir o app
      apontando para ele e conferir que login, lista e detalhe de uma OS funcionam.
      Anotar a data do teste.
- [ ] Antes de cada atualização do app com migração nova: backup manual e, depois,
      `alembic upgrade head` à mão (o contêiner não roda migrações; docs/NUVEM.md,
      "Migrações").
- [ ] Usuário do banco do app sem privilégios de superusuário.

## 5. Contas

- [ ] A senha do `admin` criada pelo seed foi **trocada** antes da entrada em produção
      (no app: Configurações > Alterar senha; ou `python -m osapp.cli redefinir-senha
      --login admin`, que cria uma senha temporária a ser trocada no primeiro login).
- [ ] Senhas: pelo menos 10 caracteres e diferentes do login (regra do sistema). Usuários
      novos e senhas redefinidas pelo administrador são temporários.
- [ ] `OS_SEED_SENHA` removida do ambiente depois da primeira subida.
- [ ] **Nenhum usuário de exemplo** em produção (`gerente.norte`, `marina.teste`,
      `joao.ficticio`): `OS_SEED_EXEMPLOS` não está definida; se existirem, desativar
      com `python -m osapp.cli desativar-usuario --login <login>`.
- [ ] Cada pessoa tem o próprio login (nada de login compartilhado). Usuários são criados,
      alterados e desativados pelo administrador em Configurações > Usuários (o histórico
      fica em `usuarios_eventos`).

## 6. Proteção do login (como funciona, para o suporte)

- **Por login (a proteção principal):** as 3 primeiras senhas erradas não têm custo; a
  partir da 4ª, a próxima tentativa daquele login só é aceita depois de 2, 4, 8, 16...
  segundos, no máximo 15 minutos. Acertar a senha zera a contagem. Não há bloqueio fixo.
- **Por IP (complemento):** operadoras de celular usam CGNAT, então muita gente divide o
  mesmo IP. Por isso o limite é alto (`OS_LIMITE_FALHAS_IP`, padrão 100 falhas em 15
  minutos) e a espera é curta (até `OS_ATRASO_MAX_IP_SEGUNDOS`, padrão 60 s). O IP nunca
  fica bloqueado.
- Mensagem para o usuário: "Muitas tentativas. Aguarde alguns instantes e tente
  novamente." Para liberar alguém na hora: `redefinir-senha` daquele login.
- **Limpeza automática, sem tarefa agendada:** contadores expirados (IP: 15 minutos sem
  falha; login: 30 dias sem atividade) não contam, são apagados quando a mesma chave tenta
  de novo e numa varredura a cada início do app. `python -m osapp.cli limpar-tentativas`
  faz a mesma limpeza à mão.

## 7. Auditoria de dependências

- [ ] `pip-audit` sem vulnerabilidades conhecidas (ou cada exceção justificada aqui).
      Resultado em 18/11/2026: 69 pacotes, **0 vulnerabilidades conhecidas**
      (`pip-audit --skip-editable`, ambiente com as dependências do app e de
      desenvolvimento). Repetir a cada atualização da imagem: o `Dockerfile` instala as
      versões mais novas permitidas no momento do build.

## 8. Logs

- O app não grava senha, hash, IP nem o login digitado: os eventos de login registram só
  o id do usuário (quando o login dá certo) e chaves HMAC.
- O log de acesso do uvicorn está desligado (`--no-access-log`), porque ele gravaria o IP
  de cada requisição.
- [ ] Os logs do **proxy** e da plataforma de hospedagem normalmente gravam IPs: definir a
      retenção deles conforme a política de privacidade da empresa.

## 9. LGPD: dados pessoais

**O que o sistema guarda**

| Dado | Onde | Por quê |
|---|---|---|
| Nome, login, filial, perfil, hash da senha (Argon2id) | tabela `usuarios` | Identificar quem usa o sistema e o que pode ver. |
| Nome de quem criou, executou, concluiu ou alterou cada OS | tabelas `ordens_servico` e `os_eventos` (pelo id do usuário) | Histórico/auditoria das ordens. |
| HMAC do login digitado e HMAC do IP, com contagem de falhas | tabela `tentativas_login`: IP até 15 min, login até 30 dias sem atividade (apagados ao tentar de novo ou ao iniciar o app) | Proteção contra tentativa de senha. Não é possível obter o IP ou o login a partir do HMAC sem o segredo. |

| E-mail (opcional, só manutenção e administrador), data da confirmação, preferências, HMAC do código de confirmação | tabela `usuario_notificacao` (prompt 32) | Avisar de novas solicitações, só com o consentimento do próprio usuário (ele cadastra, confirma, liga e remove). |
| Endereço copiado, assunto e texto da mensagem (título, descrição, solicitante da OS) | tabela `email_fila` até o envio; apagada pela retenção (`limpar-fila-email`: 30 dias enviadas/canceladas, 90 falhas) | Entrega dos avisos. O texto do código de confirmação é apagado assim que enviado. |

Não há telefone, CPF nem localização. O e-mail é opcional e só existe para quem o cadastra
no Perfil; o usuário o remove em 'Remover e-mail' (os envios pendentes dele são cancelados).

**Quem vê**

- Usuário comum: o próprio nome e os nomes ligados às OS da própria filial.
- Gerente: o mesmo, mais o relatório completo da própria filial.
- Administrador: todas as filiais.
- `tentativas_login` e a tabela de usuários completa: só quem tem acesso ao banco (TI).

**Como remover os dados de uma pessoa**

1. Desativar o acesso na hora: `python -m osapp.cli desativar-usuario --login <login>`.
2. O nome continua no histórico das OS (registro de quem fez cada coisa). Se a empresa
   decidir anonimizar, um DBA, **depois de um backup**, troca nome e login no banco:
   `UPDATE usuarios SET nome = 'Usuário removido', login = 'removido-' || id WHERE login = '<login>';`
   (o sistema ainda não tem comando para isso; ver pendências).
3. E-mail: o próprio usuário remove em Perfil > 'Remover e-mail'. Pela TI, depois de um
   backup: `DELETE FROM usuario_notificacao WHERE usuario_id = <id>;` e
   `DELETE FROM email_fila WHERE usuario_id = <id>;`.
4. As entradas em `tentativas_login` expiram em até 30 dias e são apagadas na próxima
   tentativa ou no próximo início do app; para apagar antes, `redefinir-senha` do login
   remove a entrada do login.

## 10. Hospedagem

- O Render (`render.yaml`) é **só ambiente de teste, com dados fictícios**, até a TI da
  empresa aprovar a hospedagem definitiva.
- [ ] Produção usa **PostgreSQL**. SQLite num contêiner perde os dados a cada reinício: o
      `docker/iniciar.sh` se recusa a iniciar com `OS_DATABASE_URL` em SQLite.

## 11. Saúde, monitor externo e alertas (prompt 33)

- [ ] Health check da hospedagem apontando para `/saude` (no Render: Settings > Health
      Check Path = `/saude`; hoje o `render.yaml` diz `/`).
- [ ] Monitor externo de disponibilidade (qualquer serviço de uptime, ou o da TI): HTTP
      GET `https://<endereço>/saude` a cada 1 a 5 minutos, esperando código 200 e o texto
      `"ok"`, alerta depois de 2 falhas seguidas para o e-mail/telefone do responsável.
      Nota: em plano gratuito que adormece o serviço, a primeira verificação depois de
      parado demora (o serviço acorda).
- [ ] Alertas de erro grave: chegam aos administradores com e-mail confirmado no Perfil
      (no máximo 1 por erro por hora e 20 por dia). Dependem do SMTP (item 3, E-mail).
- [ ] Mudança para servidor próprio: docs/IMPLANTACAO_LOCAL.md.

## 12. 'Lembrar de mim por 7 dias' (prompt 35)

- [ ] Orientar os usuários: marcar só no próprio celular; nunca em aparelho
      compartilhado (a tela avisa).
- [ ] Agendar uma vez por semana `python -m osapp.cli limpar-sessoes-lembradas`
      (apaga tokens expirados ou revogados há mais de 30 dias).
- [ ] Aparelho perdido: o usuário (Perfil > Aparelhos conectados > 'Sair de todos os
      aparelhos') ou o administrador (tela do usuário > 'Desconectar aparelhos').

## 13. Backup (prompt 36)

- [ ] Chaves do age geradas no computador do responsável; chave privada offline em dois
      lugares; chave pública em `OS_BACKUP_CHAVE_PUBLICA` (docs/BACKUP.md, item 1).
- [ ] Bucket S3 de OUTRO provedor (ou pasta num servidor da empresa) e chave de acesso só
      desse bucket.
- [ ] Job diário agendado (Render Cron Job pago, ou timer do systemd no servidor).
- [ ] Primeira execução manual conferida.
- [ ] **Teste de restauração feito e registrado em docs/BACKUP.md antes do piloto.**

## Pendências conhecidas

- Confirmar no Render (com `OS_DEPURAR_CABECALHOS_IP=1` por alguns minutos) de onde vem a
  conexão e quais cabeçalhos chegam, e se o Render sobrescreve `True-Client-Ip`.
- Não há comando de anonimização de usuário (item 9).
- E-mail: no plano gratuito do Render o SMTP de saída é bloqueado (item 3, E-mail).
