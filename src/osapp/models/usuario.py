from __future__ import annotations

from sqlalchemy import CheckConstraint, Column, ForeignKey, String, Table, false, true
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from osapp.db import Base
from osapp.models.especialidade import Especialidade, usuario_especialidades
from osapp.models.filial import Filial

# Prompt 34 (regra do prompt 28): filiais permitidas de cada usuário. A filial padrão
# (usuarios.filial_id) é sempre uma delas.
usuario_filiais = Table(
    "usuario_filiais",
    Base.metadata,
    Column("usuario_id", ForeignKey("usuarios.id"), primary_key=True),
    Column("filial_id", ForeignKey("filiais.id"), primary_key=True),
)


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
    # Senha temporária (criada ou redefinida pelo administrador): trocar no próximo login.
    deve_trocar_senha: Mapped[bool] = mapped_column(default=False, server_default=false())
    versao: Mapped[int] = mapped_column(default=1, server_default="1")

    # Trava otimista: edições com versão desatualizada são recusadas.
    __mapper_args__ = {"version_id_col": versao}

    filial: Mapped[Filial] = relationship()  # filial padrão
    filiais: Mapped[list[Filial]] = relationship(secondary=usuario_filiais, order_by=Filial.codigo)

    # Prompt 37: especialidades de quem é da manutenção (prepara o filtro de avisos).
    especialidades: Mapped[list[Especialidade]] = relationship(
        secondary=usuario_especialidades, order_by=Especialidade.ordem
    )

    @property
    def filiais_ids(self) -> tuple[int, ...]:
        """Filiais permitidas (sempre com a padrão, mesmo num banco antigo sem a linha)."""
        ids = {f.id for f in self.filiais} | {self.filial_id}
        return tuple(sorted(ids))

    @property
    def e_admin(self) -> bool:
        """Só leitura, derivado do papel (a antiga coluna booleana saiu na migração 0008)."""
        return self.papel == "admin"

    @validates("login")
    def _login_em_minusculas(self, _chave: str, valor: str) -> str:
        return valor.lower()
