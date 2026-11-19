"""Dados iniciais. Idempotente.  Uso: python -m osapp.seed

Cria a filial 1007 Jardinópolis, as categorias de custo, três equipamentos de exemplo e o
usuário admin. Usuários fictícios de exemplo só com OS_SEED_EXEMPLOS=1. A senha vem de
OS_SEED_SENHA (obrigatória) e nunca é exibida.
"""

from __future__ import annotations

import os
import sys

from osapp.config import ConfigError
from osapp.db import obter_engine, trava_de_inicializacao
from osapp.logs import configurar_logging
from osapp.services import administracao, senhas
from osapp.services.erros import ErroConflito, ErroValidacao

FILIAL = ("1007", "Jardinópolis")
EQUIPAMENTOS_EXEMPLO = ("Equipamento exemplo 1", "Equipamento exemplo 2", "Equipamento exemplo 3")
# (nome, login, perfil)
ADMINISTRADOR = ("Administrador", "admin", "administrador")
# Usuários fictícios, só com OS_SEED_EXEMPLOS=1 (nunca em produção).
USUARIOS_EXEMPLO = (
    ("Gabriela Gerente", "gerente.norte", "gerente"),
    ("Marina Teste", "marina.teste", "usuario"),
    ("João Fictício", "joao.ficticio", "usuario"),
    ("Usuário Teste", "usuario.teste", "solicitante"),  # papel usuario: abre solicitações
)


def executar(senha: str, exemplos: bool = False) -> dict[str, int]:
    """Cria o que faltar. Registros existentes não são alterados (nem a senha)."""
    administracao.validar_senha(senha)
    criados = {"filiais": 0, "categorias": 0, "equipamentos": 0, "usuarios": 0}
    codigo, nome = FILIAL
    try:
        administracao.criar_filial(codigo, nome)
        criados["filiais"] += 1
    except ErroConflito:
        pass
    criados["categorias"] = administracao.garantir_categorias()
    for equipamento in EQUIPAMENTOS_EXEMPLO:
        criados["equipamentos"] += administracao.garantir_equipamento(codigo, equipamento)
    usuarios = [ADMINISTRADOR, *(USUARIOS_EXEMPLO if exemplos else ())]
    for nome_usuario, login, perfil in usuarios:
        try:
            administracao.criar_usuario(
                nome_usuario,
                login,
                senha,
                codigo,
                perfil == "administrador",
                perfil == "gerente",
                papel="usuario" if perfil == "solicitante" else None,
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
            criados = executar(
                os.environ.get("OS_SEED_SENHA", ""),
                exemplos=os.environ.get("OS_SEED_EXEMPLOS", "") == "1",
            )
    except ErroValidacao:
        print(
            "Defina a variável de ambiente OS_SEED_SENHA com pelo menos "
            f"{senhas.SENHA_MIN} caracteres.",
            file=sys.stderr,
        )
        return 1
    print(
        f"Seed concluído: {criados['filiais']} filial(is), {criados['categorias']} "
        f"categoria(s), {criados['equipamentos']} equipamento(s) e {criados['usuarios']} "
        "usuário(s) criados; os demais já existiam."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
