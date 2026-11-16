"""Hash de senhas com argon2id, usando os parâmetros recomendados pela argon2-cffi."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

SENHA_MIN = 8
SENHA_MAX = 128

_hasher = PasswordHasher()  # padrões da biblioteca: argon2id


def gerar_hash(senha: str) -> str:
    return _hasher.hash(senha)


def verificar(senha: str, hash_armazenado: str) -> bool:
    """True se a senha confere. Nunca levanta exceção por senha errada ou hash inválido."""
    try:
        return _hasher.verify(hash_armazenado, senha)
    except (VerificationError, InvalidHashError):
        return False


def precisa_rehash(hash_armazenado: str) -> bool:
    """True se o hash foi gerado com parâmetros diferentes dos atuais."""
    try:
        return _hasher.check_needs_rehash(hash_armazenado)
    except InvalidHashError:
        return True
