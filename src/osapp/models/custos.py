from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String, Text, event, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from osapp.busca import normalizar_busca
from osapp.db import Base
from osapp.models.tipos import DataHoraUTC, Quantidade

FASE_PREVISTO = "PREVISTO"
FASE_REALIZADO = "REALIZADO"


def _agora_utc() -> datetime:
    return datetime.now(UTC)


class CategoriaCusto(Base):
    """Categoria de custo. Tabela (não enum) para renomear, criar ou desativar sem migração."""

    __tablename__ = "categorias_custo"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nome: Mapped[str] = mapped_column(String(60))
    ordem: Mapped[int]
    ativo: Mapped[bool] = mapped_column(default=True, server_default=true())


class OsItemCusto(Base):
    """Item de custo de uma OS. Totais são sempre calculados: não há coluna de total."""

    __tablename__ = "os_itens_custo"
    __table_args__ = (
        CheckConstraint("fase IN ('PREVISTO', 'REALIZADO')", name="fase_valida"),
        CheckConstraint("quantidade > 0", name="quantidade_positiva"),
        CheckConstraint("valor_unitario_centavos >= 0", name="valor_unitario_nao_negativo"),
        Index("ix_os_itens_custo_os_id_fase", "os_id", "fase"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    os_id: Mapped[int] = mapped_column(ForeignKey("ordens_servico.id", ondelete="RESTRICT"))
    fase: Mapped[str] = mapped_column(String(10))
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias_custo.id"))
    descricao: Mapped[str] = mapped_column(String(200))
    # normalizar_busca(descrição), mantida pelos eventos do ORM abaixo.
    busca_texto: Mapped[str] = mapped_column(Text, default="", server_default="")
    quantidade: Mapped[Decimal] = mapped_column(Quantidade())
    valor_unitario_centavos: Mapped[int] = mapped_column(BigInteger)
    criado_em: Mapped[datetime] = mapped_column(DataHoraUTC(), default=_agora_utc)
    atualizado_em: Mapped[datetime] = mapped_column(DataHoraUTC(), default=_agora_utc)

    categoria: Mapped[CategoriaCusto] = relationship()


@event.listens_for(OsItemCusto, "before_insert")
@event.listens_for(OsItemCusto, "before_update")
def _atualizar_busca_do_item(_mapper, _conexao, item: OsItemCusto) -> None:
    item.busca_texto = normalizar_busca(item.descricao)
