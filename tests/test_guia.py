"""Prompt 39: guia rápido (arquivo YAML, validação, cache, ordem de escolha, CLI)."""

from __future__ import annotations

import logging
import os
import time

import pytest

from osapp import guia
from osapp.ui import rotas
from tests.conftest import RAIZ

ARQUIVO = RAIZ / "docs" / "guia" / "guia.yaml"


@pytest.fixture
def arquivo(tmp_path, monkeypatch):
    destino = tmp_path / "guia.yaml"
    destino.write_text(ARQUIVO.read_text("utf-8"), encoding="utf-8")
    monkeypatch.setenv("OS_GUIA_ARQUIVO", str(destino))
    guia._cache = guia._Cache()
    return destino


def test_o_arquivo_do_repositorio_e_valido_e_cobre_todas_as_telas():
    g = guia.carregar_arquivo(ARQUIVO)
    assert set(guia.TELAS_POR_PAPEL) == set(rotas.TABELA)  # toda rota está mapeada
    assert guia.faltando(g, guia.TELAS_POR_PAPEL) == []
    login = g.telas["login"]["todos"].texto
    assert "Lembrar de mim" in login and "Não marque em aparelhos compartilhados" in login


def test_ordem_papel_depois_todos_depois_nada(arquivo):
    arquivo.write_text(
        """
telas:
  home:
    manutencao: {titulo: Manutenção, texto: "a\\nb\\nc"}
    todos: {titulo: Todos, texto: "a\\nb\\nc"}
  perfil:
    admin: {titulo: Só admin, texto: "a\\nb\\nc"}
""",
        encoding="utf-8",
    )
    assert guia.entrada("home", "manutencao").titulo == "Manutenção"
    assert guia.entrada("home", "usuario").titulo == "Todos"
    assert guia.entrada("perfil", "usuario") is None  # o '?' some
    assert guia.entrada("perfil", "admin").titulo == "Só admin"
    assert guia.entrada("relatorios", "admin") is None
    assert guia.entrada("home", "").titulo == "Todos"  # sem papel: só 'todos'


def test_usuario_nunca_recebe_o_texto_de_outro_papel():
    g = guia.carregar_arquivo(ARQUIVO)
    for tela, blocos in g.telas.items():
        if "usuario" in blocos or "todos" in blocos:
            continue
        assert guia.TELAS_POR_PAPEL.get(tela) is None or "usuario" not in guia.TELAS_POR_PAPEL[tela]
    guia._cache = guia._Cache()
    for tela in rotas.TABELA:
        e = guia.entrada(tela, "usuario")
        blocos = g.telas.get(tela, {})
        if e is not None:
            assert e in (blocos.get("usuario"), blocos.get("todos"))
            assert e not in (blocos.get("manutencao"), blocos.get("admin")) or e == blocos.get(
                "todos"
            )


def test_arquivo_invalido_mantem_a_ultima_versao(arquivo, caplog):
    assert guia.entrada("home", "admin") is not None
    time.sleep(0.01)
    arquivo.write_text("telas: [isto não é válido", encoding="utf-8")
    os.utime(arquivo, (time.time() + 5, time.time() + 5))
    with caplog.at_level(logging.WARNING):
        e = guia.entrada("home", "admin")
    assert e is not None and e.titulo == "Ordens de Serviço"
    assert "inválido" in caplog.text


@pytest.mark.parametrize(
    "texto",
    [
        'telas:\n  tela_que_nao_existe:\n    todos: {titulo: X, texto: "a\\nb\\nc"}\n',
        'telas:\n  home:\n    gerente: {titulo: X, texto: "a\\nb\\nc"}\n',
        'telas:\n  home:\n    todos: {titulo: X, texto: "só uma linha"}\n',
        'telas:\n  home:\n    todos: {texto: "a\\nb\\nc"}\n',
        "nada: 1\n",
    ],
)
def test_validacao(texto, tmp_path):
    caminho = tmp_path / "g.yaml"
    caminho.write_text(texto, encoding="utf-8")
    with pytest.raises(guia.GuiaInvalido):
        guia.carregar_arquivo(caminho)


def test_recarrega_quando_o_arquivo_muda(arquivo):
    assert guia.entrada("home", "admin").titulo == "Ordens de Serviço"
    arquivo.write_text(
        'telas:\n  home:\n    admin: {titulo: Novo título, texto: "a\\nb\\nc"}\n', encoding="utf-8"
    )
    os.utime(arquivo, (time.time() + 10, time.time() + 10))
    assert guia.entrada("home", "admin").titulo == "Novo título"


def test_cli_validar_guia(arquivo, capsys, monkeypatch, tmp_path):
    from osapp import cli

    monkeypatch.setenv("OS_DATABASE_URL", f"sqlite:///{tmp_path / 'x.db'}")  # o CLI exige

    assert cli.main(["validar-guia"]) == 0
    assert "válido" in capsys.readouterr().out
    arquivo.write_text("telas: {}\n", encoding="utf-8")
    os.utime(arquivo, (time.time() + 20, time.time() + 20))
    assert cli.main(["validar-guia"]) == 0  # válido, mas lista o que falta
    saida = capsys.readouterr().out
    assert "home/usuario" in saida and "sem texto" in saida
    arquivo.write_text("telas: [ruim", encoding="utf-8")
    assert cli.main(["validar-guia"]) == 1


def test_botao_de_ajuda_acessivel():
    from osapp.ui import theme
    from osapp.ui.components import cabecalho

    b = cabecalho.botao_ajuda(lambda _e: None)
    assert b.tooltip == "Ajuda desta tela" and b.icon.semantics_label == "Ajuda desta tela"
    assert b.width >= 48 and b.height >= 48 and theme.ALVO_TOQUE_MIN >= 48
