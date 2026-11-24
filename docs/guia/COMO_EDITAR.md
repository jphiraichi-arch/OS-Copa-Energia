# Como editar o Guia rápido (o botão '?')

O texto que aparece no botão **?** de cada tela fica em um único arquivo:
`docs/guia/guia.yaml`. Não é preciso programar para mudar.

## Mudar um texto

1. Abra `docs/guia/guia.yaml` num editor de texto simples (UTF-8; no Windows, o Bloco de
   Notas serve).
2. Procure a tela (por exemplo `home:`) e, dentro dela, o papel: `usuario:`,
   `manutencao:`, `admin:` ou `todos:` (`todos` vale para quem não tem bloco próprio).
3. Mude o `titulo` (uma linha) e o `texto` (de 3 a 8 linhas curtas). No texto dá para usar
   **negrito** (`**assim**`) e listas (linhas começando com `- `).
4. **Mantenha o recuo** (os espaços no começo das linhas) igual ao dos outros blocos.
5. Não escreva texto de um papel na tela de outro: quem é `usuario` nunca vê o texto de
   `manutencao` ou `admin`.

Links no texto não abrem sozinhos: só abrem se a pessoa tocar neles.

## Conferir

No servidor (ou no seu computador, na pasta do projeto):

```bash
python -m osapp.cli validar-guia
```

O comando diz se o arquivo está certo e lista as telas e papéis que ficaram sem texto.
Se o arquivo tiver um erro, o app **continua funcionando** com a última versão válida e
registra um aviso no log.

## Quando a mudança vale

- Se o arquivo for alterado **no servidor** (o caminho está em `OS_GUIA_ARQUIVO`; padrão
  `docs/guia/guia.yaml` na pasta do app), a mudança vale na próxima vez que alguém tocar
  no **?** — sem reiniciar nem implantar.
- Se o arquivo for alterado **no repositório**, a mudança vale na próxima implantação.
