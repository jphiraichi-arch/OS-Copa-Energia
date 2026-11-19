from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, String, false, true
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from osapp.db import Base
from osapp.models.filial import Filial


class Usuario(Base):
    __tablename__ = "usuarios"
    __table_args__ = (
        CheckConstraint("papel IN ('usuario', 'manutencao', 'admin')", name="papel_valido"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(100))
    login: Mapped[str] = mapped_column(String(50), unique=True)
    senha_hash: Mapped[str] = mapped_column(String(255))
    filial_id: Mapped[int] = mapped_column(ForeignKey("filiais.id"))
    # Gerente: vê o relatório completo da própria filial. Administrador prevalece.
    is_gerente: Mapped[bool] = mapped_column(default=False, server_default=false())
    ativo: Mapped[bool] = mapped_column(default=True, server_default=true())
    # Papel: usuario (abre solicitações), manutencao (executa) ou admin (tudo).
    papel: Mapped[str] = mapped_column(
        String(20), default="manutencao", server_default="manutencao"
    )

    filial: Mapped[Filial] = relationship()

    @property
    def is_admin(self) -> bool:
        """Só leitura, derivado do papel (a coluna is_admin saiu na migração 0008)."""
        return self.papel == "admin"

    @validates("login")
    def _login_em_minusculas(self, _chave: str, valor: str) -> str:
        return valor.lower()
