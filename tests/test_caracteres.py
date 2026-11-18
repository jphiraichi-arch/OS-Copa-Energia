"""Caracteres acentuados: arquivos, banco, formatação e fonte embutida (prompt 11)."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from osapp import formatacao
from osapp.services import administracao, ordens
from osapp.ui import theme
from osapp.ui.marca import PASTA_ASSETS

RAIZ = Path(__file__).resolve().parents[1]
TEXTO = "Ação Conclusão Jardinópolis ÇÃÕÉÊÍÓÚ àâêôü"
EXTENSOES_DE_TEXTO = {
    ".py",
    ".md",
    ".toml",
    ".ini",
    ".mako",
    ".txt",
    ".yaml",
    ".yml",
    ".sh",
    ".json",
}


# --- Arquivos --------------------------------------------------------------------------


@pytest.mark.parametrize("pasta", ["src", "tests"])
def test_todo_arquivo_de_texto_e_utf8_valido(pasta):
    invalidos = []
    for caminho in sorted((RAIZ / pasta).rglob("*")):
        if caminho.is_file() and caminho.suffix in EXTENSOES_DE_TEXTO:
            try:
                caminho.read_bytes().decode("utf-8")
            except UnicodeDecodeError as erro:
                invalidos.append(f"{caminho.relative_to(RAIZ)}: {erro}")
    assert not invalidos


# --- Ida e volta pelo serviço e pelo banco ---------------------------------------------


def test_texto_acentuado_ida_e_volta_pelo_banco(cenario):
    d = ordens.criar_os(cenario["marina"], TEXTO, TEXTO, 100, 60)
    lida = ordens.obter_os(cenario["marina"], d.id)
    assert (lida.titulo, lida.descricao) == (TEXTO, TEXTO)
    # a busca sem diferenciar maiúsculas também funciona com acentos
    assert [i.id for i in ordens.listar_os(cenario["marina"], busca="jardinÓpolis").itens] == [d.id]
    assert [i.titulo for i in ordens.listar_os(cenario["marina"]).itens] == [TEXTO]

    novo = TEXTO + " (revisão)"
    ordens.editar_os(cenario["marina"], d.id, lida.versao, {"titulo": novo})
    evento = ordens.listar_eventos(cenario["marina"], d.id)[-1]
    assert (evento.valor_antigo, evento.valor_novo) == (TEXTO, novo)


def test_nomes_acentuados_de_filial_e_usuario(banco):
    filial = administracao.criar_filial("J007", "Jardinópolis")
    usuario = administracao.criar_usuario(
        "Conceição Ação", "conceicao", "senha-ficticia-123", "J007"
    )
    assert filial.nome == "Jardinópolis" and usuario.nome == "Conceição Ação"
    from osapp.services.auth import carregar_ator

    assert carregar_ator(usuario.id).nome == "Conceição Ação"


# --- Formatação ------------------------------------------------------------------------


def test_formatacao_com_entrada_acentuada():
    assert formatacao.ler_brl("R$ 1.234,56") == 123456
    for texto in ("1.234,56 ç", "çã", "R$ ação", "1:3ã", "Conclusão"):
        with pytest.raises(ValueError):
            formatacao.ler_brl(texto)
        with pytest.raises(ValueError):
            formatacao.ler_duracao(texto)
    assert formatacao.formatar_duracao(90) == "1h30"


# --- Fonte embutida --------------------------------------------------------------------


def caracteres_da_fonte(caminho: Path) -> set[int]:
    """Lê a tabela cmap (formatos 4 e 12) de um arquivo TrueType, sem dependências."""
    dados = caminho.read_bytes()
    num_tabelas = struct.unpack(">H", dados[4:6])[0]
    tabelas = {
        dados[12 + 16 * i : 16 + 16 * i].decode("latin-1"): struct.unpack(
            ">II", dados[20 + 16 * i : 28 + 16 * i]
        )
        for i in range(num_tabelas)
    }
    inicio = tabelas["cmap"][0]
    pontos: set[int] = set()
    for i in range(struct.unpack(">H", dados[inicio + 2 : inicio + 4])[0]):
        deslocamento = struct.unpack(">I", dados[inicio + 8 + 8 * i : inicio + 12 + 8 * i])[0]
        sub = inicio + deslocamento
        formato = struct.unpack(">H", dados[sub : sub + 2])[0]
        if formato == 4:
            segmentos = struct.unpack(">H", dados[sub + 6 : sub + 8])[0] // 2
            fins = struct.unpack(f">{segmentos}H", dados[sub + 14 : sub + 14 + 2 * segmentos])
            base = sub + 16 + 2 * segmentos
            comecos = struct.unpack(f">{segmentos}H", dados[base : base + 2 * segmentos])
            for comeco, fim in zip(comecos, fins, strict=True):
                pontos.update(range(comeco, fim + 1))
        elif formato == 12:
            grupos = struct.unpack(">I", dados[sub + 12 : sub + 16])[0]
            for g in range(grupos):
                comeco, fim, _ = struct.unpack(">III", dados[sub + 16 + 12 * g : sub + 28 + 12 * g])
                pontos.update(range(comeco, fim + 1))
    pontos.discard(0xFFFF)
    return pontos


def arquivos_da_fonte() -> list[Path]:
    return [PASTA_ASSETS / caminho.lstrip("/") for caminho in theme.FONTE_ARQUIVOS.values()]


def test_fonte_embutida_registrada_e_no_pacote():
    import tomllib

    assert theme.FONTE_FAMILIA in theme.FONTE_ARQUIVOS
    assert theme.criar_tema().font_family == theme.FONTE_FAMILIA
    for arquivo in arquivos_da_fonte():
        assert arquivo.read_bytes()[:4] == b"\x00\x01\x00\x00", arquivo  # TrueType
    assert "SIL Open Font License" in (PASTA_ASSETS / "fonts" / "OFL.txt").read_text("utf-8")
    pacote = tomllib.loads((RAIZ / "pyproject.toml").read_text("utf-8"))
    dados = pacote["tool"]["setuptools"]["package-data"]["osapp"]
    assert "assets/fonts/*.ttf" in dados and "assets/fonts/OFL.txt" in dados
    main = (RAIZ / "src" / "osapp" / "main.py").read_text("utf-8")
    assert main.count("no_cdn=True") == 2  # desenvolvimento e ASGI: nada de CDN


def test_fonte_cobre_portugues_e_os_simbolos_usados():
    pontos = caracteres_da_fonte(arquivos_da_fonte()[0])
    assert all(ord(c) in pontos for c in "áâãàéêíóôõúçÁÂÃÀÉÊÍÓÔÕÚÇºª€…·–—“”‘’")
    # o leitor da tabela também acusa o que falta (sem isso o teste passaria à toa)
    assert ord("‒") not in pontos and ord("Ж") not in pontos and ord("→") not in pontos


def test_todo_caractere_dos_textos_da_interface_existe_na_fonte():
    """Falha se um rótulo usar um caractere que a fonte embutida não desenha."""
    import ast

    pontos = caracteres_da_fonte(arquivos_da_fonte()[0])
    pastas = [RAIZ / "src" / "osapp" / "ui", RAIZ / "src" / "osapp" / "services"]
    faltando = set()
    for pasta in pastas:
        for arquivo in pasta.rglob("*.py"):
            for no in ast.walk(ast.parse(arquivo.read_text("utf-8"))):
                if isinstance(no, ast.Constant) and isinstance(no.value, str):
                    faltando |= {
                        f"{c!r} U+{ord(c):04X} em {arquivo.name}"
                        for c in no.value
                        if ord(c) >= 0x20 and c not in "\n\t" and ord(c) not in pontos
                    }
    assert not faltando, sorted(faltando)
