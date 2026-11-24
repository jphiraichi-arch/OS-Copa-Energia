# Mudança para um servidor Linux da empresa

Guia passo a passo para tirar o Sistema de OS da hospedagem atual e rodá-lo num servidor
próprio (Debian/Ubuntu; em outras distribuições mudam só os comandos de pacote). Nada no
código depende da hospedagem atual: tudo o que muda está nas variáveis de ambiente
(docs/CONFIGURACAO.md) e na configuração do servidor descrita aqui.

Convenções usadas abaixo (troque à vontade):
- usuário do sistema operacional que roda o app: `osapp` (sem login, sem sudo);
- pasta do app: `/opt/sistema-os`; arquivo de ambiente: `/etc/sistema-os/ambiente`;
- banco `sistema_os`; papéis `os_dono` (dono do esquema, usado só nas migrações) e
  `os_app` (o app no dia a dia, só leitura e escrita de dados);
- endereço público `https://os.empresa.com.br`.

## 1. PostgreSQL

1. Descubra a versão do banco atual (rodar no banco atual, só leitura):
   `psql "$URL_ATUAL" -c "SHOW server_version;"`. Instale a **mesma versão principal ou
   mais nova** (ex.: 16 -> 16 ou 17), pelo repositório oficial do PostgreSQL
   (https://www.postgresql.org/download/linux/).
2. Crie os papéis e o banco (como `postgres`):

   ```sql
   CREATE ROLE os_dono LOGIN PASSWORD 'troque-esta-senha-1';
   CREATE ROLE os_app  LOGIN PASSWORD 'troque-esta-senha-2';
   CREATE DATABASE sistema_os OWNER os_dono ENCODING 'UTF8' TEMPLATE template0;
   \c sistema_os
   REVOKE ALL ON SCHEMA public FROM PUBLIC;
   GRANT USAGE ON SCHEMA public TO os_app;
   -- Tudo o que os_dono criar (migrações) fica utilizável pelo app, sem DDL:
   ALTER DEFAULT PRIVILEGES FOR ROLE os_dono IN SCHEMA public
       GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO os_app;
   ALTER DEFAULT PRIVILEGES FOR ROLE os_dono IN SCHEMA public
       GRANT USAGE, SELECT ON SEQUENCES TO os_app;
   ```

   O app usa uma trava consultiva (`pg_advisory_lock`) na partida; não precisa de
   privilégio extra.
3. Em `pg_hba.conf`, aceite só conexões locais (`host sistema_os os_app 127.0.0.1/32
   scram-sha-256`, idem para `os_dono`). Se o banco ficar em outra máquina, use TLS e
   libere só o IP do servidor do app no firewall.

## 2. Python e o app

```bash
sudo apt install -y python3.12 python3.12-venv postgresql-client-16   # cliente = versão do servidor ou mais nova
sudo useradd --system --home /opt/sistema-os --shell /usr/sbin/nologin osapp
sudo mkdir -p /opt/sistema-os /etc/sistema-os
sudo git clone <repositório> /opt/sistema-os/app      # ou copie a versão aprovada
sudo python3.12 -m venv /opt/sistema-os/venv
sudo /opt/sistema-os/venv/bin/pip install '/opt/sistema-os/app[postgres]'
sudo chown -R osapp:osapp /opt/sistema-os
```

Arquivo de ambiente `/etc/sistema-os/ambiente` (só o usuário do serviço lê):

```
OS_DATABASE_URL=postgresql://os_app:troque-esta-senha-2@127.0.0.1:5432/sistema_os
OS_HMAC_SEGREDO=<o MESMO valor da hospedagem atual, para não zerar os contadores; ou um novo>
OS_TZ=America/Sao_Paulo
OS_PROXIES_CONFIAVEIS=127.0.0.1
OS_CABECALHO_IP_CLIENTE=
OS_BASE_URL=https://os.empresa.com.br
# E-mail (se houver): OS_SMTP_HOST, OS_SMTP_PORTA, OS_SMTP_TLS, OS_SMTP_USUARIO,
# OS_SMTP_SENHA, OS_SMTP_REMETENTE
```

```bash
sudo chown osapp:osapp /etc/sistema-os/ambiente
sudo chmod 600 /etc/sistema-os/ambiente
```

As migrações usam o papel dono (`os_dono`), num arquivo separado que só o administrador
lê (`/etc/sistema-os/migracao`, mode 600, com `OS_DATABASE_URL` do `os_dono` e
`OS_HMAC_SEGREDO`):

```bash
cd /opt/sistema-os/app
sudo -u osapp env $(sudo cat /etc/sistema-os/migracao | xargs) /opt/sistema-os/venv/bin/alembic upgrade head
```

## 3. Serviço systemd

`/etc/systemd/system/sistema-os.service`:

```ini
[Unit]
Description=Sistema de OS
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
User=osapp
Group=osapp
WorkingDirectory=/opt/sistema-os/app
EnvironmentFile=/etc/sistema-os/ambiente
# Um processo só: as sessões do Flet ficam na memória do processo.
ExecStart=/opt/sistema-os/venv/bin/uvicorn osapp.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers --no-access-log
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/tmp

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now sistema-os
journalctl -u sistema-os -f        # o log do app
curl -s http://127.0.0.1:8000/saude  # {"status": "ok", "banco": "ok"}
```

O app ouve só em 127.0.0.1: quem fala com a internet é o nginx.

## 4. nginx com TLS e WebSocket

```nginx
map $http_upgrade $connection_upgrade { default upgrade; '' close; }

server {
    listen 80;
    server_name os.empresa.com.br;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name os.empresa.com.br;
    ssl_certificate     /etc/ssl/os/fullchain.pem;   # certificado da empresa ou Let's Encrypt
    ssl_certificate_key /etc/ssl/os/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    add_header Strict-Transport-Security "max-age=31536000" always;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;               # WebSocket do Flet
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        # O IP do cliente é o que o PRÓPRIO nginx viu: sobrescreve (não acrescenta) o
        # X-Forwarded-For e apaga cabeçalhos que o cliente poderia forjar.
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header True-Client-Ip "";
        proxy_set_header X-Real-Ip "";
        proxy_set_header Forwarded "";
        # Sessões longas no WebSocket (celular parado na tela).
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        proxy_buffering off;
    }
}
```

Variáveis do app que combinam com esta configuração: `OS_PROXIES_CONFIAVEIS=127.0.0.1`
(só o nginx local é confiável) e `OS_CABECALHO_IP_CLIENTE` vazio (o IP vem do
`X-Forwarded-For` que o nginx escreveu: a única entrada da lista). O prompt 30 (ainda não
recebido) vai trazer `OS_PROXY_SALTOS`; com esta configuração o valor será `1` (um proxy:
o nginx). Para conferir, deixe `OS_DEPURAR_CABECALHOS_IP=1` por alguns minutos, entre
pelo celular e veja no log o IP escolhido; depois volte a `0`.

## 5. Mover os dados

O `pg_dump` precisa ser da mesma versão principal do servidor de **origem** ou mais nova
(`pg_dump --version`).

1. Teste antes (sem congelar nada): faça os passos 2 a 5 num banco de ensaio, abra o app
   apontando para ele e confira.
2. Dump do banco atual (só leitura):

   ```bash
   pg_dump -Fc --no-owner --no-acl -d "$URL_ATUAL" -f os-$(date -u +%Y%m%dT%H%M%SZ).dump
   ```

3. Restaure no banco novo, como `os_dono` (o banco precisa estar vazio):

   ```bash
   pg_restore --no-owner --no-acl --exit-on-error -d "postgresql://os_dono:...@127.0.0.1/sistema_os" os-....dump
   ```

   Como o restore cria as tabelas com o papel `os_dono`, os privilégios padrão do passo 1
   dão ao `os_app` o acesso aos dados. Confira com
   `psql ... -c "\dp ordens_servico"`.
4. `alembic upgrade head` (com o arquivo de migração do passo 2): deve dizer que já está
   na versão mais nova, ou aplicar só as que faltarem.
5. Conferências:
   - `curl -s http://127.0.0.1:8000/saude` -> `{"status": "ok", "banco": "ok"}`;
   - `alembic current` igual ao da hospedagem atual;
   - contagem das tabelas principais igual nos dois bancos (`usuarios`,
     `ordens_servico`, `os_eventos`, `os_itens_custo`, `filiais`), por exemplo
     `SELECT count(*) FROM ordens_servico;` em cada um;
   - `python -m osapp.cli verificar-eventos-status` e `verificar-rotulos-eventos`;
   - entrar com um usuário de cada papel e abrir uma OS.

## 6. Virada e volta

1. Avise os usuários de uma janela curta (10 a 20 minutos), fora do horário de pico.
2. **Congelamento**: pare o app antigo (ou suspenda o serviço na hospedagem) para que
   ninguém grave mais nada.
3. Dump final do banco antigo e restore no novo (passo 5, de novo, num banco vazio:
   `DROP DATABASE`/`CREATE DATABASE` como no passo 1).
4. Suba o serviço novo, rode as conferências do passo 5.
5. Troque o DNS (ou o link que os usuários usam) para o servidor novo. Com DNS, baixe o
   TTL para 5 minutos um dia antes.
6. Monitore `/saude` e o log nas primeiras horas.

**Voltar** (se algo der errado depois da virada): pare o serviço novo, volte o DNS/link
para a hospedagem antiga e religue o app antigo. O banco antigo ficou intacto até o
congelamento; o que foi gravado no novo depois da virada precisa ser copiado à mão (ou
descartado, se a janela foi curta). Por isso: decidir voltar ou não nas primeiras horas.
Não apague a hospedagem antiga antes de algumas semanas de uso tranquilo.

## 7. Saúde e monitoramento

- `GET /saude` (sem login): `200 {"status": "ok", "banco": "ok"}` ou
  `503 {"status": "erro", "banco": "erro"}`. Uma consulta `SELECT 1` com limite de 2 s;
  nenhuma informação sensível.
- Aponte para ela o health check da hospedagem (caminho `/saude`) e um monitor externo
  de disponibilidade (HTTP, a cada 1 a 5 minutos, alerta depois de 2 falhas seguidas,
  esperando código 200 e o texto `"ok"`).
- Erros graves (ERROR/CRITICAL no log) geram e-mail para os administradores com e-mail
  confirmado (no máximo um por erro por hora e 20 por dia); ver docs/CONFIGURACAO.md,
  `OS_ALERTAS_EMAIL`.
