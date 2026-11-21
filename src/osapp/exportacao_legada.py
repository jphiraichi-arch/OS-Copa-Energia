"""Exportação dos equipamentos antes da migração 0010 (que remove o cadastro).

Único módulo de src/ que ainda conhece equipamento (o teste de referências o exclui). Os
modelos do app já não têm essas colunas: as tabelas são lidas por reflexão do banco, com
o SQLAlchemy (consultas montadas pelo SQLAlchemy, parâmetros vinculados).
"""

from __future__ import annotations

import csv
from pathlib import Path

from sqlalchemy import MetaData, inspect, select

from osapp.db import obter_engine


class SemEquipamentos(RuntimeError):
    """O banco já não tem as colunas de equipamento (migração 0010 aplicada)."""


def exportar_equipamentos(arquivo: str | Path) -> int:
    """Grava numero;equipamento (nome do cadastro ou o texto 'Outro') de cada OS que tem
    equipamento. Devolve quantas linhas gravou. Não altera nada no banco."""
    engine = obter_engine()
    colunas = {c["name"] for c in inspect(engine).get_columns("ordens_servico")}
    if "equipamento_id" not in colunas:
        raise SemEquipamentos("O banco não tem mais as colunas de equipamento.")
    meta = MetaData()
    meta.reflect(bind=engine, only=["ordens_servico", "equipamentos"])
    ordens = meta.tables["ordens_servico"]
    equipamentos = meta.tables["equipamentos"]
    consulta = (
        select(ordens.c.numero, equipamentos.c.nome, ordens.c.equipamento_outro)
        .select_from(ordens.outerjoin(equipamentos, ordens.c.equipamento_id == equipamentos.c.id))
        .where((ordens.c.equipamento_id.is_not(None)) | (ordens.c.equipamento_outro.is_not(None)))
        .order_by(ordens.c.numero)
    )
    with engine.connect() as conexao:
        linhas = conexao.execute(consulta).all()
    with open(arquivo, "w", newline="", encoding="utf-8") as saida:
        escritor = csv.writer(saida, delimiter=";")
        escritor.writerow(["numero", "equipamento"])
        for numero, nome, outro in linhas:
            escritor.writerow([numero, nome if nome is not None else outro])
    return len(linhas)


def registrar_comando(sub) -> None:
    """Comando de linha 'exportar-equipamentos ARQUIVO.csv' (chamado por osapp.cli)."""
    from osapp.services.erros import ErroValidacao

    def executar(args) -> str:
        try:
            total = exportar_equipamentos(args.arquivo)
        except SemEquipamentos as exc:
            raise ErroValidacao("arquivo", str(exc)) from None
        return f"{total} linha(s) gravada(s) em {args.arquivo}."

    p = sub.add_parser(
        "exportar-equipamentos",
        help="Antes da migração 0010: grava numero;equipamento das OS num CSV",
    )
    p.add_argument("arquivo")
    p.set_defaults(func=executar)
