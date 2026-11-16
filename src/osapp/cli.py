"""Administração pela linha de comando.  Uso: python -m osapp.cli <comando>

Senhas são sempre lidas com getpass, nunca dos argumentos.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from osapp.config import ConfigError
from osapp.logs import configurar_logging
from osapp.services import administracao
from osapp.services.erros import ErroConflito, ErroDominio, ErroNaoEncontrado, ErroValidacao


def _perguntar(valor: str | None, rotulo: str) -> str:
    return valor if valor is not None else input(f"{rotulo}: ")


def _ler_senha() -> str:
    senha = getpass.getpass("Senha: ")
    if getpass.getpass("Repita a senha: ") != senha:
        raise ErroValidacao("senha", "As senhas não conferem.")
    return senha


def _criar_filial(args) -> str:
    filial = administracao.criar_filial(
        _perguntar(args.codigo, "Código"), _perguntar(args.nome, "Nome")
    )
    return f"Filial {filial.codigo} criada."


def _criar_usuario(args) -> str:
    nome = _perguntar(args.nome, "Nome")
    login = _perguntar(args.login, "Login")
    filial = _perguntar(args.filial, "Código da filial")
    usuario = administracao.criar_usuario(nome, login, _ler_senha(), filial, args.admin)
    papel = "administrador" if usuario.is_admin else "usuário"
    return f"Usuário {usuario.login} criado na filial {usuario.filial_codigo} ({papel})."


def _redefinir_senha(args) -> str:
    login = _perguntar(args.login, "Login")
    administracao.redefinir_senha(login, _ler_senha())
    return "Senha redefinida."


def _desativar_usuario(args) -> str:
    administracao.desativar_usuario(_perguntar(args.login, "Login"))
    return "Usuário desativado."


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m osapp.cli", description="Sistema de OS")
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("criar-filial", help="Cria uma filial")
    p.add_argument("--codigo")
    p.add_argument("--nome")
    p.set_defaults(func=_criar_filial)

    p = sub.add_parser("criar-usuario", help="Cria um usuário (a senha é pedida)")
    p.add_argument("--nome")
    p.add_argument("--login")
    p.add_argument("--filial", help="Código da filial")
    p.add_argument("--admin", action="store_true", help="Cria como administrador")
    p.set_defaults(func=_criar_usuario)

    p = sub.add_parser("redefinir-senha", help="Redefine a senha e remove o bloqueio")
    p.add_argument("--login")
    p.set_defaults(func=_redefinir_senha)

    p = sub.add_parser("desativar-usuario", help="Desativa um usuário")
    p.add_argument("--login")
    p.set_defaults(func=_desativar_usuario)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = criar_parser().parse_args(argv)
    try:
        configurar_logging()
    except ConfigError as exc:
        print(f"Erro de configuração: {exc}", file=sys.stderr)
        return 1
    try:
        print(args.func(args))
    except ErroValidacao as exc:
        print(f"Erro: {exc.mensagem}", file=sys.stderr)
        return 1
    except ErroConflito:
        print("Erro: já existe um registro com esse código ou login.", file=sys.stderr)
        return 1
    except ErroNaoEncontrado:
        print("Erro: usuário não encontrado.", file=sys.stderr)
        return 1
    except ErroDominio:
        print("Erro: não foi possível concluir a operação.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
