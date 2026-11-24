"""SLA (prompt 38): prazos de início e de solução por filial e urgência, em minutos de
relógio (um dia = 24 horas; sem calendário de dias úteis nesta versão)."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from osapp.db import Base


class SlaAlvo(Base):
    __tablename__ = "sla_alvos"
    __table_args__ = (
        UniqueConstraint("filial_id", "urgencia"),
        CheckConstraint(
            "urgencia IN ('baixa', 'media', 'alta', 'emergencial')", name="urgencia_valida"
        ),
        CheckConstraint("prazo_inicio_min > 0 AND prazo_solucao_min > 0", name="prazos_positivos"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    filial_id: Mapped[int] = mapped_column(ForeignKey("filiais.id"))
    urgencia: Mapped[str] = mapped_column(String(12))
    prazo_inicio_min: Mapped[int]
    prazo_solucao_min: Mapped[int]
