"""Dados iniciais. Idempotente.  Uso: python -m osapp.seed

Cria a filial 1007 Jardinópolis, as categorias de custo e o usuário admin. Usuários
fictícios de exemplo só com OS_SEED_EXEMPLOS=1. A senha vem de OS_SEED_SENHA
(obrigatória) e nunca é exibida.
"""

from __future__ import annotations

import logging
import sys

from osapp import config
from osapp.config import ConfigError
from osapp.db import obter_engine, trava_de_inicializacao
from osapp.logs import configurar_logging
from osapp.services import administracao, senhas
from osapp.services.erros import ErroConflito, ErroValidacao

logger = logging.getLogger("osapp.seed")


def motivo_para_pular(senha: str) -> str | None:
    """Por que o seed não pode rodar com esta senha, ou None. Nunca inclui a senha."""
    if not senha:
        return f"OS_SEED_SENHA não está definida (mínimo de {senhas.SENHA_MIN} caracteres)"
    if len(senha) < senhas.SENHA_MIN:
        return f"OS_SEED_SENHA tem menos de {senhas.SENHA_MIN} caracteres"
    return None


FILIAL = ("1007", "Jardinópolis")
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
    criados = {"filiais": 0, "categorias": 0, "usuarios": 0}
    codigo, nome = FILIAL
    try:
        administracao.criar_filial(codigo, nome)
        criados["filiais"] += 1
    except ErroConflito:
        pass
    criados["categorias"] = administracao.garantir_categorias()
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
    senha = config.seed_senha()
    motivo = motivo_para_pular(senha)
    if motivo is not None:
        # Nunca em silêncio: a linha de ERRO fica no log de inicialização.
        logger.error(
            "Seed NÃO executado: %s. Nenhum usuário foi criado ou alterado; o app sobe sem o seed.",
            motivo,
        )
        return 1
    try:
        # Instâncias que sobem juntas rodam o seed uma de cada vez.
        with trava_de_inicializacao(obter_engine()):
            criados = executar(senha, exemplos=config.seed_exemplos())
    except ErroValidacao as exc:
        logger.error("Seed NÃO executado: %s", exc.mensagem)
        return 1
    print(
        f"Seed concluído: {criados['filiais']} filial(is), {criados['categorias']} "
        f"categoria(s) e {criados['usuarios']} "
        "usuário(s) criados; os demais já existiam."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
