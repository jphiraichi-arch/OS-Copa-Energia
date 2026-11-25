"""Prompt 43: o cartão 'Aparelhos conectados' cresce com as linhas e nunca vira um
retângulo cinza.

A causa do retângulo era um filho com ``expand`` dentro de uma ``Row(wrap=True)`` (no
Flet 1.1.2 vira um ``Expanded`` do Flutter dentro de um ``Wrap``). Estes testes cobrem a
função pura que prepara as linhas, a árvore de controles do cartão e a regra de layout em
todas as telas (docs/REGRAS.md, 'Layout').
"""

from __future__ import annotations

import ast
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import flet as ft

from osapp.services.sessoes_lembradas import Aparelho
from osapp.ui.views import aparelhos as tela

RAIZ = Path(__file__).resolve().parent.parent
T0 = datetime(2026, 11, 25, 15, 30, tzinfo=UTC)  # 12:30 em America/Sao_Paulo


def _aparelho(i: int, rotulo: str = "Chrome em Windows") -> Aparelho:
    momento = T0 - timedelta(hours=i)
    return Aparelho(f"fam{i}", rotulo, momento - timedelta(days=1), momento, T0)


# --- Função pura --------------------------------------------------------------------------


def test_nenhum_aparelho_mostra_so_a_frase():
    c = tela.preparar([], None)
    assert c.linhas == ()
    assert c.vazio == (
        'Nenhum aparelho lembrado. Marque "Lembrar de mim" ao entrar para aparecer aqui.'
    )
    assert c.ver_todos is None and c.sair_de_todos is False


def test_tres_aparelhos_tres_linhas_e_o_atual_marcado():
    lista = [_aparelho(2), _aparelho(0, "Chrome em Android"), _aparelho(1, "Safari em iPad")]
    c = tela.preparar(lista, "fam1")
    assert len(c.linhas) == 3 and c.vazio is None and c.ver_todos is None
    assert [linha.familia for linha in c.linhas] == ["fam0", "fam1", "fam2"]  # mais recente
    assert [linha.atual for linha in c.linhas] == [False, True, False]
    assert [linha.tipo for linha in c.linhas] == ["celular", "tablet", "computador"]
    assert c.sair_de_todos is True


def test_quinze_aparelhos_dez_linhas_e_ver_todos():
    lista = [_aparelho(i) for i in range(15)]
    c = tela.preparar(lista, "fam14")
    assert len(c.linhas) == 10
    assert c.ver_todos == "Ver todos (15)"
    assert [linha.familia for linha in c.linhas] == [f"fam{i}" for i in range(10)]
    todos = tela.preparar(lista, "fam14", expandido=True)
    assert len(todos.linhas) == 15 and todos.ver_todos is None
    assert todos.linhas[-1].atual is True


def test_dez_aparelhos_sem_ver_todos():
    assert tela.preparar([_aparelho(i) for i in range(10)], None).ver_todos is None


def test_textos_da_linha_no_fuso(monkeypatch):
    monkeypatch.setenv("OS_TZ", "America/Sao_Paulo")
    linha = tela.linha_do_aparelho(_aparelho(0, "Chrome em Android"), True)
    assert linha.rotulo == "Chrome em Android"
    assert linha.conectado == "Conectado em 24/11/2026"
    assert linha.ultimo_uso == "Último uso 25/11/2026 12:30"


def test_tipo_do_aparelho():
    assert tela.tipo_do_aparelho("Safari em iPhone") == "celular"
    assert tela.tipo_do_aparelho("Firefox em Linux") == "computador"
    assert tela.tipo_do_aparelho("Navegador") == "computador"


# --- Árvore de controles do cartão ---------------------------------------------------------


def _app(familia=None):
    return SimpleNamespace(
        sessao=SimpleNamespace(ator_id=1),
        familia_lembrada=familia,
        avisar=lambda *_: None,
        confirmar=lambda *_: None,
    )


def _secao(aparelhos, familia=None):
    s = tela.SecaoAparelhos(_app(familia))
    s.aparelhos = aparelhos
    s._desenhar()
    return s


def _filhos(c: ft.Control) -> list[ft.Control]:
    saida = []
    for nome in ("controls", "content"):
        v = getattr(c, nome, None)
        if isinstance(v, ft.Control):
            saida.append(v)
        elif isinstance(v, list):
            saida.extend(x for x in v if isinstance(x, ft.Control))
    return saida


def _todos(c: ft.Control):
    yield c
    for f in _filhos(c):
        yield from _todos(f)


def _problemas(raiz: ft.Control) -> list[str]:
    """Filho com expand numa Row que quebra linha; ListView ou scroll dentro do cartão;
    expand numa Column (altura sem limite dentro da página que rola)."""
    erros = []
    for c in _todos(raiz):
        if isinstance(c, ft.ListView | ft.GridView):
            erros.append(f"{type(c).__name__} dentro do cartão")
        if isinstance(c, ft.Column) and c.scroll is not None:
            erros.append("Column com scroll dentro do cartão")
        for f in _filhos(c):
            if not getattr(f, "expand", None):
                continue
            if isinstance(c, ft.Row) and c.wrap:
                erros.append(f"{type(f).__name__}(expand) dentro de Row(wrap=True)")
            if isinstance(c, ft.Column):
                erros.append(f"{type(f).__name__}(expand) dentro de Column")
    return erros


def _textos(raiz) -> list[str]:
    saida = []
    for c in _todos(raiz):
        if isinstance(c, ft.Text):
            saida.append(c.value)
        if isinstance(c, ft.TextButton) and isinstance(c.content, str):
            saida.append(c.content)
    return saida


def test_cartao_com_0_1_3_e_15_aparelhos_sem_padrao_que_vira_cinza():
    for n in (0, 1, 3, 15):
        s = _secao([_aparelho(i) for i in range(n)], "fam0")
        assert _problemas(s.controle) == [], n
        assert s.lista.expand in (None, False, 0) and s.lista.scroll is None


def test_cartao_vazio_so_a_frase_e_sem_sair_de_todos():
    s = _secao([])
    assert _textos(s.lista) == [tela.NENHUM]
    assert s.botao_todos.visible is False


def test_cartao_com_tres_aparelhos_tres_botoes_de_48px_e_este_aparelho():
    s = _secao([_aparelho(i) for i in range(3)], "fam1")
    botoes = [
        c for c in _todos(s.lista) if isinstance(c, ft.TextButton) and c.content == tela.SAIR_DESTE
    ]
    assert len(botoes) == 3
    assert all(b.height >= 48 for b in botoes)
    assert _textos(s.lista).count(tela.ESTE) == 1
    assert s.botao_todos.visible is True


def test_ver_todos_expande_no_lugar():
    s = _secao([_aparelho(i) for i in range(15)])
    assert "Ver todos (15)" in _textos(s.lista)
    s._ver_todos()
    assert _textos(s.lista).count(tela.SAIR_DESTE) == 15
    assert "Ver todos (15)" not in _textos(s.lista)


def test_erro_numa_linha_vira_uma_frase_e_vai_para_o_log(monkeypatch, caplog):
    s = tela.SecaoAparelhos(_app())
    s.aparelhos = [_aparelho(0), _aparelho(1)]
    original = s._linha

    def quebra(linha):
        if linha.familia == "fam0":
            raise ValueError("teste")
        return original(linha)

    monkeypatch.setattr(s, "_linha", quebra)
    with caplog.at_level(logging.ERROR):
        s._desenhar()
    assert tela.FALHA_LINHA in _textos(s.lista)
    assert _textos(s.lista).count(tela.SAIR_DESTE) == 1
    assert "Falha ao montar a linha" in caplog.text


# --- Regra em todas as telas (docs/REGRAS.md, 'Layout') ------------------------------------


def _nome(c: ast.Call) -> str:
    f = c.func
    return f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")


def _kw(c: ast.Call, k: str):
    return next((x.value for x in c.keywords if x.arg == k), None)


def test_nenhuma_tela_usa_expand_dentro_de_row_que_quebra_linha_nem_listview():
    erros = []
    for arquivo in sorted((RAIZ / "src" / "osapp" / "ui").rglob("*.py")):
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            if not isinstance(no, ast.Call):
                continue
            local = f"{arquivo.relative_to(RAIZ)}:{no.lineno}"
            if _nome(no) in ("ListView", "GridView"):
                erros.append(f"{local} {_nome(no)}")
            if _nome(no) != "Row":
                continue
            wrap = _kw(no, "wrap")
            if not (isinstance(wrap, ast.Constant) and wrap.value is True):
                continue
            lista = no.args[0] if no.args else _kw(no, "controls")
            for filho in getattr(lista, "elts", []):
                if isinstance(filho, ast.Call) and _kw(filho, "expand") is not None:
                    erros.append(f"{local} {_nome(filho)}(expand) em Row(wrap=True)")
    assert erros == []
