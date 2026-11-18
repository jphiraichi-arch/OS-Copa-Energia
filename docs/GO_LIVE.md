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

### Qual endereço o app deve considerar proxy confiável

- [ ] Descobrir o endereço IP (ou a rede) **de onde o proxy se conecta ao contêiner do
      app**, como o contêiner o vê (por exemplo `10.0.0.5` ou `10.0.0.0/24`).
- [ ] Colocar esse valor em **`OS_PROXIES_CONFIAVEIS`** (vários separados por vírgula).
- Só requisições vindas desses endereços podem informar o IP do cliente. Para qualquer
  outra origem, `X-Forwarded-For` é ignorado (não dá para forjar o IP).
- **Não usar `*`**: com `*`, o app confia em qualquer origem e usa o primeiro IP da lista,
  que o próprio cliente pode escrever. Isso anula o limite por IP do login.
- Sem a variável, só `127.0.0.1` é confiável (proxy na mesma máquina).
- O cabeçalho padronizado `Forwarded` (RFC 7239) **não** é lido: o servidor (uvicorn)
  só entende `X-Forwarded-For` / `X-Forwarded-Proto`.

Se o IP do cliente não puder ser determinado, o app usa um limite comum chamado
`desconhecido` para todos e registra um aviso no log ("IP do cliente desconhecido"). Se
esse aviso aparecer em produção, a configuração do proxy está errada.

## 3. Variáveis de ambiente (nomes)

| Variável | Obrigatória | Para quê |
|---|---|---|
| `OS_DATABASE_URL` | sim | Conexão com o PostgreSQL (contém senha: tratar como segredo). |
| `OS_HMAC_SEGREDO` | sim | Segredo do HMAC das tentativas de login. Mínimo de 32 caracteres aleatórios, diferente em cada ambiente. Sem ela o app não inicia. Trocá-la zera, na prática, os contadores de tentativas. |
| `OS_PROXIES_CONFIAVEIS` | sim, atrás de proxy | Endereço(s) do proxy reverso (item 2). |
| `OS_TZ` | não | Fuso das datas (padrão `America/Sao_Paulo`). |
| `OS_SESSAO_TIMEOUT_MIN` | não | Minutos de inatividade até sair (padrão 30). |
| `OS_LOG_LEVEL` | não | Nível do log (padrão `INFO`). |
| `OS_SEED_SENHA` | só na primeira subida | Senha inicial do `admin` criado pelo seed. Remover depois. |
| `OS_SEED_EXEMPLOS` | **não usar em produção** | Cria usuários fictícios de exemplo. |
| `PORT` | não | Porta do servidor no contêiner (padrão 8000). |

- [ ] Segredos guardados no cofre/gerenciador de segredos da plataforma, nunca no git.

## 4. Banco de dados

- [ ] **Backup automático** diário do PostgreSQL, com retenção definida pela empresa.
- [ ] **Restauração testada**: restaurar um backup em um banco separado, subir o app
      apontando para ele e conferir que login, lista e detalhe de uma OS funcionam.
      Anotar a data do teste.
- [ ] Antes de cada atualização do app: backup manual (as migrações rodam sozinhas ao
      iniciar o contêiner, em `docker/iniciar.sh`).
- [ ] Usuário do banco do app sem privilégios de superusuário.

## 5. Contas

- [ ] A senha do `admin` criada pelo seed foi **trocada** antes da entrada em produção
      (`python -m osapp.cli redefinir-senha --login admin`; a senha é pedida no terminal).
- [ ] `OS_SEED_SENHA` removida do ambiente depois da primeira subida.
- [ ] **Nenhum usuário de exemplo** em produção (`gerente.norte`, `marina.teste`,
      `joao.ficticio`): `OS_SEED_EXEMPLOS` não está definida; se existirem, desativar
      com `python -m osapp.cli desativar-usuario --login <login>`.
- [ ] Cada pessoa tem o próprio login (nada de login compartilhado).

## 6. Proteção do login (como funciona, para o suporte)

- Por login: as 3 primeiras senhas erradas não têm custo; a partir da 4ª, a próxima
  tentativa daquele login só é aceita depois de 2, 4, 8, 16... segundos, no máximo 15
  minutos. Acertar a senha zera a contagem. Não há bloqueio fixo da conta.
- Por IP: mais de 20 falhas do mesmo IP em 15 minutos colocam o IP na mesma regra, para
  qualquer login.
- Mensagem para o usuário: "Muitas tentativas. Aguarde alguns instantes e tente
  novamente." Para liberar alguém na hora: `redefinir-senha` daquele login.
- [ ] Agendar a limpeza diária: `python -m osapp.cli limpar-tentativas` (apaga contadores
      sem atividade há mais de 30 dias). Ela **não** roda sozinha.

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
| HMAC do login digitado e HMAC do IP, com contagem de falhas | tabela `tentativas_login`, por até 30 dias (com a limpeza agendada) | Proteção contra tentativa de senha. Não é possível obter o IP ou o login a partir do HMAC sem o segredo. |

Não há e-mail, telefone, CPF nem localização.

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
3. As entradas em `tentativas_login` somem sozinhas em até 30 dias com a limpeza
   agendada; para apagar antes, `redefinir-senha` do login remove a entrada do login.

## Pendências conhecidas

- O endereço do proxy do Render (hospedagem atual de teste) não foi confirmado; até lá o
  limite por IP pode tratar todos os acessos como vindos do mesmo endereço.
- Não há comando de anonimização de usuário (item 9).
- A limpeza de `tentativas_login` precisa de agendamento externo (item 6).
