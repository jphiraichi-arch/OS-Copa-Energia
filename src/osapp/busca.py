"""Normalização de texto para busca. Módulo puro (sem Flet e sem banco).

O texto gravado (busca_texto) e o termo digitado passam pela mesma função, então os dois
lados comparam do mesmo jeito: sem acento, sem diferença de maiúsculas, espaços únicos.
"""

from __future__ import annotations

import unicodedata


def normalizar_busca(texto: str | None) -> str:
    """'  Válvula   de  GÁS ' -> 'valvula de gas'. None e vazio -> ''.

    NFKD separa letra e acento; os acentos (marcas combinantes) saem; casefold() é mais
    forte que lower() (ex.: 'ß' -> 'ss'); espaços em sequência viram um só.
    """
    if not texto:
        return ""
    decomposto = unicodedata.normalize("NFKD", str(texto))
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return " ".join(sem_acento.casefold().split())
