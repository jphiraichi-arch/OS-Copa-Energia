from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from osapp.db import Base
from osapp.models.custos import OsItemCusto
from osapp.models.equipamento import Equipamento
from osapp.models.filial import Filial
from osapp.models.tipos import DataHoraUTC
from osapp.models.usuario import Usuario


def _agora_utc() -> datetime:
    return datetime.now(UTC)


class OrdemServico(Base):
    __tablename__ = "ordens_servico"
    __table_args__ = (
        CheckConstraint("tempo_previsto_minutos > 0", name="tempo_previsto_positivo"),
        Index("ix_ordens_servico_filial_id_status", "filial_id", "status"),
        Index("ix_ordens_servico_criado_em", "criado_em"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[str] = mapped_column(String(30), unique=True)
    # Integração SAP futura: indexado, ainda não único.
    numero_sap: Mapped[str | None] = mapped_column(String(40), index=True)
    filial_id: Mapped[int] = mapped_column(ForeignKey("filiais.id"))
    criado_por_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    titulo: Mapped[str] = mapped_column(String(120))
    descricao: Mapped[str] = mapped_column(Text)
    # Os valores permitidos de status são verificados no serviço, não por constraint.
    status: Mapped[str] = mapped_column(String(20))
    tempo_previsto_minutos: Mapped[int]
    inicio_realizado: Mapped[datetime | None] = mapped_column(DataHoraUTC())
    fim_realizado: Mapped[datetime | None] = mapped_column(DataHoraUTC())
    descricao_realizado: Mapped[str | None] = mapped_column(Text)
    executor_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    # Equipamento: um cadastrado da filial, ou "Outro" com texto livre.
    equipamento_id: Mapped[int | None] = mapped_column(ForeignKey("equipamentos.id"))
    equipamento_outro: Mapped[str | None] = mapped_column(String(120))
    iniciado_em: Mapped[datetime | None] = mapped_column(DataHoraUTC())
    concluido_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    concluido_em: Mapped[datetime | None] = mapped_column(DataHoraUTC())
    criado_em: Mapped[datetime] = mapped_column(DataHoraUTC(), default=_agora_utc)
    atualizado_em: Mapped[datetime] = mapped_column(DataHoraUTC(), default=_agora_utc)
    versao: Mapped[int] = mapped_column(default=1, server_default="1")

    # Trava otimista: o ORM inclui "WHERE versao = ?" em cada UPDATE e incrementa o valor.
    __mapper_args__ = {"version_id_col": versao}

    filial: Mapped[Filial] = relationship()
    criado_por: Mapped[Usuario] = relationship(foreign_keys=[criado_por_id])
    executor: Mapped[Usuario | None] = relationship(foreign_keys=[executor_id])
    concluido_por: Mapped[Usuario | None] = relationship(foreign_keys=[concluido_por_id])
    equipamento: Mapped[Equipamento | None] = relationship()
    # Itens de custo (os totais são sempre calculados a partir deles).
    itens: Mapped[list[OsItemCusto]] = relationship(
        order_by="OsItemCusto.id", lazy="selectin", viewonly=True
    )
