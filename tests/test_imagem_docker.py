"""O contexto de build da imagem contém tudo o que o Dockerfile copia.

Regressão: o prompt 39 passou a copiar docs/guia, mas o .dockerignore excluía 'docs'
inteiro e o build no servidor falhou ('"/docs/guia": not found'). Este teste aplica as
regras do .dockerignore (padrões simples e exceções '!', na ordem; a última que casa
vale, como no Docker) a cada origem de COPY.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _regras() -> list[tuple[bool, str]]:
    regras = []
    for linha in (RAIZ / ".dockerignore").read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        excecao = linha.startswith("!")
        regras.append((excecao, linha.lstrip("!").strip("/")))
    return regras


def _excluido(caminho: str, regras: list[tuple[bool, str]]) -> bool:
    excluido = False
    partes = caminho.split("/")
    for excecao, padrao in regras:
        # Um padrão casa com o caminho ou com qualquer diretório acima dele.
        casa = any(
            fnmatch.fnmatchcase("/".join(partes[: i + 1]), padrao) for i in range(len(partes))
        )
        if casa:
            excluido = not excecao
    return excluido


def _origens_copy() -> list[str]:
    origens = []
    for linha in (RAIZ / "Dockerfile").read_text(encoding="utf-8").splitlines():
        palavras = linha.split()
        if palavras and palavras[0].upper() == "COPY" and not palavras[1].startswith("--"):
            origens.extend(palavras[1:-1])
    return origens


def test_toda_origem_de_copy_existe_e_entra_no_contexto():
    regras = _regras()
    origens = _origens_copy()
    assert "docs/guia" in origens
    for origem in origens:
        assert (RAIZ / origem).exists(), origem
        assert not _excluido(origem, regras), f"{origem} excluído pelo .dockerignore"


def test_guia_yaml_entra_no_contexto():
    assert not _excluido("docs/guia/guia.yaml", _regras())
    assert _excluido("docs/ROADMAP.md", _regras())  # o resto de docs continua fora
    assert _excluido("tests/test_guia.py", _regras())
