"""Dados fictícios de desenvolvimento. Idempotente.  Uso: python -m osapp.seed

A senha de todos os usuários vem de OS_SEED_SENHA (obrigatória) e nunca é exibida.
"""

from __future__ import annotations

import os
import sys

from osapp.config import ConfigError
from osapp.db import obter_engine, trava_de_inicializacao
from osapp.logs import configurar_logging
from osapp.services import administracao
from osapp.services.erros import ErroConflito, ErroValidacao

FILIAIS = [("F001", "Filial Modelo Norte"), ("F002", "Filial Modelo Sul")]
# (nome, login, código da filial, perfil)
USUARIOS = [
    ("Administrador Fictício", "admin", "F001", "administrador"),
    ("Gabriela Gerente", "gerente.norte", "F001", "gerente"),
    ("Marina Teste", "marina.teste", "F001", "usuario"),
    ("João Fictício", "joao.ficticio", "F001", "usuario"),
    ("Carlos Exemplo", "carlos.exemplo", "F002", "usuario"),
]


def executar(senha: str) -> dict[str, int]:
    """Cria o que faltar. Registros existentes não são alterados (nem a senha)."""
    administracao.validar_senha(senha)
    criados = {"filiais": 0, "usuarios": 0}
    for codigo, nome in FILIAIS:
        try:
            administracao.criar_filial(codigo, nome)
            criados["filiais"] += 1
        except ErroConflito:
            pass
    for nome, login, filial, perfil in USUARIOS:
        try:
            administracao.criar_usuario(
                nome, login, senha, filial, perfil == "administrador", perfil == "gerente"
            )
            criados["usuarios"] += 1
        except ErroConflito:
            pass
    return criados


def main() -> int:
    try:
        configurar_logging()
    except ConfigError as exc:
        print(f"Erro de configuração: {exc}", file=sys.stderr)
        return 1
    try:
        # Instâncias que sobem juntas rodam o seed uma de cada vez.
        with trava_de_inicializacao(obter_engine()):
            criados = executar(os.environ.get("OS_SEED_SENHA", ""))
    except ErroValidacao:
        print(
            "Defina a variável de ambiente OS_SEED_SENHA com pelo menos 8 caracteres.",
            file=sys.stderr,
        )
        return 1
    print(
        f"Seed concluído: {criados['filiais']} filial(is) e {criados['usuarios']} usuário(s) "
        "criados; os demais já existiam."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
