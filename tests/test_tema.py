import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1] / "src" / "osapp"
ARQUIVO_TEMA = RAIZ / "ui" / "theme.py"
# '#' seguido de 3, 4, 6 ou 8 dígitos hexadecimais, dentro de uma string.
RE_HEX = re.compile(r"""["']#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})["']""")


def test_cores_hex_so_no_tema():
    infratores = []
    for arquivo in sorted(RAIZ.rglob("*.py")):
        if arquivo == ARQUIVO_TEMA:
            continue
        for n, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), start=1):
            if RE_HEX.search(linha):
                infratores.append(f"{arquivo.relative_to(RAIZ)}:{n}: {linha.strip()}")
    assert not infratores, "Cor hexadecimal fora de ui/theme.py:\n" + "\n".join(infratores)


def test_o_detector_funciona():
    assert RE_HEX.search('cor = "#F28C28"')
    assert RE_HEX.search("cor = '#fff'")
    assert not RE_HEX.search("# comentário comum")
    assert RE_HEX.search(ARQUIVO_TEMA.read_text(encoding="utf-8"))


def test_tokens_do_tema():
    from osapp.ui import theme

    assert theme.COR_CABECALHO == "#3A3A3A"
    assert theme.COR_DESTAQUE == "#F28C28"
    assert theme.COR_BOTAO_PRIMARIO == "#2F4A54"
    assert theme.COR_FUNDO_PAGINA == "#F1F2F4"
    assert theme.COR_TITULO == "#1F2A44"
    assert theme.COR_SUBTITULO == "#6B7280"
    assert theme.RAIO_CARTAO == 16
    assert theme.ALVO_TOQUE_MIN == 48


def test_cabecalho_monta_com_padroes_e_parametros():
    import flet as ft

    from osapp.ui.components.cabecalho import cabecalho

    def textos(controle):
        achados = []
        if isinstance(controle, ft.Text):
            achados.append(controle.value)
        for filho in getattr(controle, "controls", None) or []:
            achados += textos(filho)
        conteudo = getattr(controle, "content", None)
        if isinstance(conteudo, ft.Control):
            achados += textos(conteudo)
        return achados

    padrao = textos(cabecalho())
    assert "F000" in padrao and "Olá, Visitante" in padrao
    outro = textos(cabecalho(nome="Marina Teste", codigo_filial="F001"))
    assert "F001" in outro and "Olá, Marina Teste" in outro


def test_logotipo_da_empresa():
    import flet as ft

    from osapp.ui import marca
    from osapp.ui.components.cabecalho import barra

    assert marca.logo_disponivel()
    assert (marca.PASTA_ASSETS / marca.ARQUIVO_LOGO).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    def imagens(controle):
        achadas = [controle] if isinstance(controle, ft.Image) else []
        for filho in getattr(controle, "controls", None) or []:
            achadas += imagens(filho)
        conteudo = getattr(controle, "content", None)
        if isinstance(conteudo, ft.Control):
            achadas += imagens(conteudo)
        return achadas

    (imagem,) = imagens(barra("F001"))
    assert imagem.src == "logo.png" and imagem.semantics_label == "Copa Energia"
    assert imagem.fit == ft.BoxFit.CONTAIN  # proporções mantidas


def test_logotipo_vai_no_pacote_instalado():
    import tomllib

    from tests.conftest import RAIZ

    config = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    assert "assets/*.png" in config["tool"]["setuptools"]["package-data"]["osapp"]
    main = (RAIZ / "src" / "osapp" / "main.py").read_text(encoding="utf-8")
    assert main.count("assets_dir=str(PASTA_ASSETS)") == 2  # desenvolvimento e ASGI
