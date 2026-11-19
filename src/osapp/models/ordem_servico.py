from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from osapp.db import Base
from osapp.models.custos import OsItemCusto
from osapp.models.equipamento import Equipamento
from osapp.models.filial import Filial
from osapp.models.tipo_manutencao import TipoManutencao
from osapp.models.tipos import DataHoraUTC
from osapp.models.usuario import Usuario


def _agora_utc() -> datetime:
    return datetime.now(UTC)


class OrdemServico(Base):
    __tablename__ = "ordens_servico"
    __table_args__ = (
        # Vale só quando preenchido (NULL passa num CHECK).
        CheckConstraint("tempo_previsto_minutos > 0", name="tempo_previsto_positivo"),
        CheckConstraint("origem IN ('solicitacao', 'manutencao')", name="origem_valida"),
        CheckConstraint(
            "urgencia IN ('baixa', 'media', 'alta', 'emergencial')", name="urgencia_valida"
        ),
        CheckConstraint(
            "prioridade IN ('baixa', 'media', 'alta', 'emergencial')", name="prioridade_valida"
        ),
        # Linhas do tempo impossíveis não podem ser gravadas.
        CheckConstraint("inicio_execucao_em >= aberta_em", name="inicio_apos_abertura"),
        CheckConstraint("concluida_em >= inicio_execucao_em", name="conclusao_apos_inicio"),
        CheckConstraint("cancelada_em >= aberta_em", name="cancelamento_apos_abertura"),
        CheckConstraint(
            "concluida_em IS NULL OR cancelada_em IS NULL", name="concluida_ou_cancelada"
        ),
        Index("ix_ordens_servico_filial_id_status", "filial_id", "status"),
        Index("ix_ordens_servico_criado_em", "criado_em"),
        Index("ix_ordens_servico_filial_id_origem_aberta_em", "filial_id", "origem", "aberta_em"),
        Index("ix_ordens_servico_status", "status"),
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
    tempo_previsto_minutos: Mapped[int | None]
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

    # --- Prompt 16: solicitações e instantes de cada mudança de status ----------------
    origem: Mapped[str] = mapped_column(
        String(20), default="manutencao", server_default="manutencao"
    )
    urgencia: Mapped[str | None] = mapped_column(String(20))  # do solicitante
    prioridade: Mapped[str | None] = mapped_column(String(20))  # da manutenção
    tipo_id: Mapped[int | None] = mapped_column(ForeignKey("tipos_manutencao.id"))
    nota_conclusao: Mapped[str | None] = mapped_column(Text)
    aberta_em: Mapped[datetime] = mapped_column(
        DataHoraUTC(), default=_agora_utc, server_default=func.now()
    )
    inicio_execucao_em: Mapped[datetime | None] = mapped_column(DataHoraUTC())
    concluida_em: Mapped[datetime | None] = mapped_column(DataHoraUTC())
    cancelada_em: Mapped[datetime | None] = mapped_column(DataHoraUTC())
    cancelada_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))

    # Trava otimista: o ORM inclui "WHERE versao = ?" em cada UPDATE e incrementa o valor.
    __mapper_args__ = {"version_id_col": versao}

    filial: Mapped[Filial] = relationship()
    criado_por: Mapped[Usuario] = relationship(foreign_keys=[criado_por_id])
    executor: Mapped[Usuario | None] = relationship(foreign_keys=[executor_id])
    concluido_por: Mapped[Usuario | None] = relationship(foreign_keys=[concluido_por_id])
    equipamento: Mapped[Equipamento | None] = relationship()
    tipo: Mapped[TipoManutencao | None] = relationship()
    cancelada_por: Mapped[Usuario | None] = relationship(foreign_keys=[cancelada_por_id])
    # Itens de custo (os totais são sempre calculados a partir deles).
    itens: Mapped[list[OsItemCusto]] = relationship(
        order_by="OsItemCusto.id", lazy="selectin", viewonly=True
    )
