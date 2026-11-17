# Regras permanentes do projeto — Sistema de OS

Este arquivo é vinculante para todos os prompts. `docs/ESTADO.md` registra o que já existe.

## STACK (fixa)

- Python 3.12+ em Linux, venv + pip. O projeto instala com: `pip install -e '.[dev]'`
- Flet 1.1.x, fixado como `flet>=1.1,<1.2`, rodando como app web no lado do servidor: o Python
  roda no servidor, o navegador mostra a interface. Não é build estático nem Pyodide.
- SQLAlchemy 2 + Alembic (adicionados no prompt 2). SQLite em desenvolvimento, PostgreSQL depois.
- pytest e ruff como dependências de desenvolvimento.

## REGRA DO FLET (crítica)

O Flet 1.0 foi uma reescrita completa; código Flet escrito de memória ou copiado de tutoriais
antigos normalmente falha. Antes de usar qualquer API do Flet:

1. Confirme a versão instalada com: `pip show flet`
2. Consulte a API na documentação atual em https://flet.dev/docs, ou pelo servidor MCP oficial
   (pacote PyPI `flet-mcp`, iniciado com o comando `flet mcp`). Não use o pacote comunitário
   não relacionado chamado `flet-mcp-server`.
3. Exemplos de armadilhas conhecidas (lista incompleta): `ft.app(target=main)` virou
   `ft.run(main)`; `page.go()` virou o assíncrono `page.push_route()`; `ElevatedButton` virou
   `Button`.
4. O Flet 1.1 mudou as superfícies padrão do tema para branco neutro / quase preto; portanto
   defina explicitamente toda cor de que o app precisa.
5. Use os controles Material padrão, não os controles com estilo shadcn adicionados na 1.1.

Se não for possível verificar uma API, pare e avise. Não adivinhe.

## Camadas

- `models -> repositories -> services -> ui`.
- Regras de negócio e verificações de permissão vivem somente em `services`.
- Views nunca importam `models` nem `repositories`.

## Segurança

- Senhas com hash argon2id; nunca armazenadas nem registradas em log em texto puro.
- Toda verificação de permissão e de filial é aplicada em `services` e coberta por teste.
- Acesso ao banco somente pelo ORM do SQLAlchemy, com parâmetros vinculados.
- Toda entrada é validada no lado do servidor.
- Segredos e a URL do banco ficam somente em variáveis de ambiente.
- O usuário vê mensagens de erro genéricas; os detalhes vão para os logs do servidor.
- Dados de seed usam apenas nomes fictícios.

## Perfis de acesso

- **Usuário (operário):** trabalha só na própria filial; vê o relatório básico (contagens e
  tempos) da própria filial.
- **Gerente:** mesmas permissões do usuário nas Ordens de Serviço; além disso vê o relatório
  completo (valores em dinheiro, gasto do mês, desvios e desempenho por pessoa) da própria
  filial.
- **Administrador:** age em todas as filiais e vê todos os relatórios, por filial ou
  consolidados.
- Dados sensíveis (valores em dinheiro, desempenho por pessoa) só saem do serviço para
  gerente (própria filial) e administrador. A interface apenas mostra o que recebe.

## Idioma

- Interface em português do Brasil; datas `dd/mm/aaaa`; moeda `R$ 1.234,56`.
- Identificadores de domínio em português (`filial`, `usuario`, `ordem_servico`).

## Armazenamento

- Dinheiro em centavos inteiros, durações em minutos inteiros, instantes (timestamps) em UTC.

## Interface

- `src/osapp/ui/theme.py` é a única fonte de cores, raios e tamanhos. Nenhum valor hexadecimal
  de cor pode aparecer em outro arquivo de `src/osapp` (garantido por `tests/test_tema.py`).
- Celulares são o alvo principal: coluna única, sem rolagem horizontal a 390 px; alvo de toque
  mínimo de 48 px.
- O único logotipo permitido é o arquivo oficial da Copa Energia fornecido pelo responsável,
  `src/osapp/assets/logo.png`: sem redesenhar, recolorir nem distorcer. Nenhum outro
  logotipo real de empresa.

## Fora do escopo do MVP (o desenho não pode bloqueá-los)

Status cancelada, triagem, aceite pela operação, KPIs, fotos, notificações, planos preventivos,
estoque, exportação PDF/Excel.
