"""Erros de domínio. Só ErroValidacao carrega texto destinado ao usuário."""

from __future__ import annotations


class ErroDominio(Exception):
    """Base de todos os erros de regra de negócio."""


class ErroValidacao(ErroDominio):
    """Entrada inválida. ``mensagem`` está em português e pode ser mostrada ao usuário."""

    def __init__(self, campo: str, mensagem: str) -> None:
        super().__init__(mensagem)
        self.campo = campo
        self.mensagem = mensagem


class ErroAutenticacao(ErroDominio):
    """Credenciais inválidas ou sessão sem usuário válido. Sempre a mesma mensagem."""

    def __init__(self) -> None:
        super().__init__("Falha de autenticação.")


class ErroMuitasTentativas(ErroAutenticacao):
    """Tentativa de login antes do instante permitido (login ou IP com falhas demais).

    A senha não chegou a ser conferida. A resposta é a mesma para logins que existem e
    que não existem.
    """


class ErroPermissao(ErroDominio):
    def __init__(self) -> None:
        super().__init__("Operação não permitida.")


class ErroNaoEncontrado(ErroDominio):
    def __init__(self) -> None:
        super().__init__("Registro não encontrado.")


class ErroConflito(ErroDominio):
    def __init__(self) -> None:
        super().__init__("Conflito de dados.")
