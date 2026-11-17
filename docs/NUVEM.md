# Publicar na nuvem sem custo (Render + Neon)

Combinação testada no desenho do projeto: o app roda como contêiner no plano gratuito do
**Render** e o banco fica no plano gratuito do **Neon** (PostgreSQL). Nenhum dos dois é
indicado para produção; servem para demonstração e piloto.

## O que você recebe e o que não recebe

| Ponto | Comportamento no plano gratuito |
|---|---|
| Endereço | `https://<nome-do-serviço>.onrender.com`, com HTTPS |
| WebSocket | Funciona (o app depende dele) |
| Inatividade | O serviço dorme depois de 15 minutos sem acesso; o próximo acesso leva cerca de 1 minuto para acordar |
| Sessões | Ficam na memória: quando o serviço dorme ou reinicia, todos fazem login de novo |
| Dados | Ficam no Neon e **não** se perdem quando o serviço dorme |
| Banco | 1 GB por projeto; o banco também hiberna após 5 minutos parado e acorda sozinho |
| Horas | 750 horas de instância por mês por conta no Render |

Os limites mudam com frequência: confira as páginas oficiais antes de depender deles.

## Passo a passo (cerca de 10 minutos)

1. **Banco (Neon).** Crie uma conta em https://neon.com e um projeto na região
   **AWS US East 1 (N. Virginia)**, a mesma do app no Render (o plano gratuito do Render
   não tem região no Brasil, e app e banco devem ficar lado a lado). Copie a *connection
   string* (botão **Connect**), no formato
   `postgresql://usuario:senha@host/banco?sslmode=require`. Trate-a como senha.
2. **App (Render).** Crie uma conta em https://render.com e conecte o seu GitHub. Escolha
   **New > Blueprint**, selecione este repositório e o ramo que contém o `render.yaml`.
3. O Render pede duas variáveis:
   - `OS_DATABASE_URL`: cole a connection string do Neon.
   - `OS_SEED_SENHA`: uma senha de 8 ou mais caracteres para os usuários fictícios
     (`admin`, `marina.teste`, `joao.ficticio`, `carlos.exemplo`).
4. Confirme. O Render constrói a imagem (`Dockerfile`), e o contêiner, ao iniciar, roda
   `alembic upgrade head`, o seed (se `OS_SEED_SENHA` existir) e o servidor.
5. Abra o endereço mostrado pelo Render e entre com `admin` e a senha do passo 3.

## Depois de publicar

- **Usuários reais:** o plano gratuito do Render não tem terminal. Rode a CLI no seu
  computador apontando para o mesmo banco:
  `OS_DATABASE_URL='<url do Neon>' python -m osapp.cli criar-usuario` (instale antes com
  `pip install -e '.[postgres]'`).
- **Remover os usuários fictícios:** apague `OS_SEED_SENHA` no painel e desative-os com
  `python -m osapp.cli desativar-usuario --login marina.teste` (e os demais).
- **Atualizações:** cada push no ramo publicado gera uma nova implantação; as migrações
  rodam sozinhas na inicialização.

## Migração e seed na inicialização

O contêiner roda `alembic upgrade head` e o seed a cada início (`docker/iniciar.sh`). O
comando de pré-implantação (*pre-deploy*) do Render, que rodaria a migração uma única vez,
só existe em serviços pagos. No plano gratuito, uma trava consultiva do PostgreSQL
(`db.trava_de_inicializacao`) garante que, se duas instâncias subirem juntas, uma espere a
outra terminar. Ao passar para um plano pago, a migração pode ir para o pre-deploy.

## Outras plataformas

O `Dockerfile` não depende do Render. Qualquer serviço que rode contêineres com WebSocket
serve, desde que: (1) haja **uma única instância**, (2) `OS_DATABASE_URL` aponte para um
PostgreSQL e (3) a plataforma forneça HTTPS. A porta vem da variável `PORT` (padrão 8000).

## Rodar a imagem localmente

```bash
docker build -t sistema-os .
docker run --rm -p 8000:8000 \
  -e OS_DATABASE_URL='postgresql://usuario:senha@host/banco' \
  -e OS_SEED_SENHA='uma-senha-de-teste' sistema-os
```
