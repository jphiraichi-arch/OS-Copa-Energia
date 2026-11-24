# Backup do Sistema de OS

Backup diário, criptografado, guardado FORA do provedor do banco. Os recursos de
restauração do próprio provedor do banco são um bônus, não o backup: um problema de
conta, de pagamento ou um engano lá levaria o banco e a cópia juntos.

## Em resumo

| Pergunta | Resposta |
|---|---|
| O quê | O banco inteiro (`pg_dump -Fc`: tabelas, dados, sequências, versão do Alembic). |
| Quando | Uma vez por dia (sugestão: 06:00 UTC = 03:00 de Brasília). |
| Onde | Armazenamento compatível com S3 de OUTRO provedor (`OS_BACKUP_DESTINO=s3`) ou uma pasta de um servidor da empresa (`OS_BACKUP_DESTINO=pasta`). |
| Por quanto tempo | `OS_BACKUP_RETENCAO_DIAS` (padrão 30). O backup bem-sucedido mais recente nunca é apagado. |
| Criptografia | `age`, com chave pública. O servidor só tem a chave **pública** (`OS_BACKUP_CHAVE_PUBLICA`): quem roubar o servidor ou o armazenamento não lê nenhum backup. |
| Quem guarda a chave privada | **A empresa, fora de qualquer servidor** (por exemplo, dois pendrives guardados em lugares diferentes, ou o cofre de senhas da TI). |
| Quanto dado pode ser perdido | Até **um dia**: o que foi gravado depois do último backup. |
| Quanto tempo leva para restaurar | Medido no teste de restauração (tabela no fim deste documento). |

> **ATENÇÃO:** perder a chave privada torna TODOS os backups inúteis. Não existe
> recuperação. Guarde duas cópias, em lugares diferentes, e registre quem as tem.

Arquivos: `os-AAAAMMDDTHHMMSSZ.dump.age` (data e hora UTC do início) e, ao lado,
`os-....dump.age.manifest.json` (nome, tamanho, SHA-256 do arquivo criptografado,
início, fim, versões). O manifesto só é gravado depois do arquivo: backup sem manifesto
é um backup que falhou.

Como o script trabalha: `pg_dump -Fc` com a saída ligada direto ao `age` (o dump sem
criptografia nunca vai para o disco e nunca fica inteiro na memória), SHA-256 em blocos,
envio, retenção, e os arquivos temporários são apagados com sucesso ou com falha.
Qualquer falha: código de saída diferente de zero, linha `Backup FALHOU` no log e um
alerta de erro grave (prompt 33) para os administradores com e-mail confirmado, quando o
app e o e-mail estão configurados.

## Antes de tudo: versões

1. Versão do servidor de produção (rodar no seu computador, só leitura):

   ```bash
   psql "$URL_PRODUCAO" -X -A -t -c "SHOW server_version;"
   ```

2. O `pg_dump` de quem roda o backup precisa ser da **mesma versão principal ou mais
   nova** (`pg_dump --version`). A imagem `docker/backup.Dockerfile` instala o cliente
   17 (argumento `PG_MAJOR`; aumente se o servidor for mais novo).

## 1. Gerar as chaves (no SEU computador; a privada nunca vai para servidor)

```bash
age-keygen -o os-backup.agekey          # chave PRIVADA: guardar offline (2 cópias)
age-keygen -y os-backup.agekey          # imprime a chave PÚBLICA (age1...)
```

A chave pública vai para `OS_BACKUP_CHAVE_PUBLICA`. A privada fica fora de qualquer
servidor, do repositório e do armazenamento dos backups (o `.gitignore` já recusa
`*.agekey`).

## 2. Armazenamento

S3 compatível de outro provedor (exemplos: Backblaze B2, Cloudflare R2, Wasabi, AWS S3):
1. Crie um bucket privado só para os backups (sem acesso público, versão de objetos
   ligada se o provedor oferecer; bloqueio contra exclusão, se houver, ajuda contra
   ransomware).
2. Crie uma chave de acesso limitada a ESSE bucket, com permissão de listar, ler,
   gravar e apagar objetos (a retenção apaga).

Pasta num servidor da empresa: um compartilhamento montado na máquina do job; o usuário
do job precisa ler, gravar e apagar nela.

## 3. Variáveis de ambiente (do job de backup, não do app)

| Variável | Obrigatória | Significado |
|---|---|---|
| `OS_DATABASE_URL` | sim | A mesma do app (pode ser um usuário só de leitura). Segredo. |
| `OS_BACKUP_CHAVE_PUBLICA` | sim | Chave pública do age (`age1...`). |
| `OS_BACKUP_DESTINO` | sim | `s3` ou `pasta`. |
| `OS_BACKUP_BUCKET` | sim | Nome do bucket (s3) ou caminho da pasta (pasta). |
| `OS_BACKUP_S3_ENDPOINT` | s3 de outro provedor | URL do serviço S3 do provedor (ex.: `https://s3.us-west-000.backblazeb2.com`). |
| `OS_BACKUP_S3_REGIAO` | depende do provedor | Região. |
| `OS_BACKUP_S3_CHAVE_ID` | s3 | Id da chave de acesso. Segredo. |
| `OS_BACKUP_S3_CHAVE_SECRETA` | s3 | Segredo da chave de acesso. Segredo. |
| `OS_BACKUP_S3_PREFIXO` | não | Pasta dentro do bucket (ex.: `sistema-os/`). |
| `OS_BACKUP_RETENCAO_DIAS` | não | Padrão 30. |
| `OS_HMAC_SEGREDO` e as de SMTP | só para o alerta | As mesmas do app, se quiser o e-mail de alerta na falha. |

## 4. Agendamento

**Hospedagem atual (Render):** um *Cron Job* (serviço pago: cobrado pelo tempo de
execução, mínimo de US$ 1 por mês por job; não existe no plano gratuito). Novo > Cron
Job > o mesmo repositório, ambiente Docker, Dockerfile `docker/backup.Dockerfile`,
agenda `0 6 * * *` (o Render usa UTC), e as variáveis do item 3 (pode usar um
*Environment Group* compartilhado com o app para `OS_DATABASE_URL`). O Render
interrompe uma execução depois de 12 horas.

**Servidor da empresa (systemd):** `/etc/systemd/system/sistema-os-backup.service`

```ini
[Unit]
Description=Backup do Sistema de OS
[Service]
Type=oneshot
User=osbackup
EnvironmentFile=/etc/sistema-os/backup      # mode 600, dono osbackup
WorkingDirectory=/opt/sistema-os/app
ExecStart=/opt/sistema-os/venv/bin/python scripts/backup.py
```

e `/etc/systemd/system/sistema-os-backup.timer`

```ini
[Unit]
Description=Backup diário do Sistema de OS
[Timer]
OnCalendar=*-*-* 03:00:00 America/Sao_Paulo
Persistent=true
RandomizedDelaySec=10m
[Install]
WantedBy=timers.target
```

`sudo systemctl enable --now sistema-os-backup.timer`; ver com
`systemctl list-timers` e `journalctl -u sistema-os-backup`. (Com cron:
`0 3 * * * osbackup cd /opt/sistema-os/app && set -a && . /etc/sistema-os/backup && /opt/sistema-os/venv/bin/python scripts/backup.py`.)
Instale `age` e o `postgresql-client` da versão certa no servidor.

## 5. Primeira execução manual

Com as variáveis do item 3 no ambiente: `python scripts/backup.py`. Confira no
armazenamento o par `os-....dump.age` + `.manifest.json` e, no log,
`Backup os-....: concluído`.

## 6. Restauração, passo a passo

1. Crie um banco **novo e vazio** (`CREATE DATABASE os_restaurado;`), da mesma versão
   principal do PostgreSQL ou mais nova.
2. Pegue a chave privada (pendrive) e, numa máquina com `age`, `pg_restore` e `psql`,
   com as variáveis de acesso ao armazenamento (item 3):

   ```bash
   python scripts/restaurar.py --arquivo ultimo \
       --identidade /media/pendrive/os-backup.agekey \
       --destino-url "postgresql://usuario:senha@host:5432/os_restaurado"
   ```

   `--arquivo os-20261124T060000Z.dump.age` escolhe um backup específico. O script
   confere o SHA-256 com o manifesto ANTES de decriptar, recusa um banco que não esteja
   vazio e recusa a URL de produção (`OS_DATABASE_URL` ou `--url-producao`) sem
   `--permitir-producao` e a confirmação digitada `RESTAURAR PRODUCAO`.
3. Na pasta do app, apontando para o banco restaurado: `alembic current` (a versão do
   backup) e, se o código for mais novo, `alembic upgrade head`.
4. Para colocar em produção: siga a virada de docs/IMPLANTACAO_LOCAL.md (item 6).

## 7. Teste de restauração (obrigatório antes do piloto)

1. Restaure o backup mais recente num banco novo e vazio (item 6), marcando a hora de
   início e de fim.
2. `alembic current` no banco restaurado.
3. Conte as tabelas principais nos dois bancos e compare:
   `SELECT count(*) FROM usuarios;` e o mesmo para `ordens_servico`, `os_eventos`,
   `os_itens_custo`, `filiais`. (Diferença = o que foi gravado depois do backup.)
4. Abra o app num ambiente de TESTE apontando para o banco restaurado (nunca o de
   produção) e entre com um usuário de cada papel.
5. Registre abaixo.

| Data | Backup restaurado | Duração | alembic current | Contagens conferem? | App abriu? | Quem fez |
|---|---|---|---|---|---|---|
| (preencher) | | | | | | |

Os testes automáticos (`tests/test_backup.py`) fazem a mesma ida e volta com um
PostgreSQL local e um par de chaves de teste:

```bash
sudo apt install -y age postgresql-client-16
OS_TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/os_teste pytest -q tests/test_backup.py
```
