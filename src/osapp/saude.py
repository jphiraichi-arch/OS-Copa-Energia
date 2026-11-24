"""GET /saude (prompt 33): o app está de pé e o banco responde.

200 {"status": "ok", "banco": "ok"} ou 503 {"status": "erro", "banco": "erro"}. Sem
login e sem dado sensível: nem versão, nem host, nem mensagem de erro, nem contagem.
Barato: um ``SELECT 1`` com limite de 2 segundos; verificações simultâneas (vários
monitores ao mesmo tempo) compartilham a mesma consulta em andamento, então uma queda do
banco não empilha conexões nem threads.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi.responses import JSONResponse

from osapp import db

logger = logging.getLogger(__name__)

TIMEOUT_SEGUNDOS = 2.0
OK = {"status": "ok", "banco": "ok"}
ERRO = {"status": "erro", "banco": "erro"}
CABECALHOS = {"Cache-Control": "no-store"}

_em_andamento: asyncio.Future | None = None


async def banco_ok(timeout: float = TIMEOUT_SEGUNDOS) -> bool:
    global _em_andamento
    if _em_andamento is None or _em_andamento.done():
        _em_andamento = asyncio.ensure_future(asyncio.to_thread(db.banco_responde))
    try:
        return bool(await asyncio.wait_for(asyncio.shield(_em_andamento), timeout))
    except Exception:  # noqa: BLE001 - qualquer falha é 'erro'; o detalhe não sai daqui
        logger.warning("Saúde: o banco não respondeu em %.0f s.", timeout)
        return False


async def rota_saude() -> JSONResponse:
    if await banco_ok():
        return JSONResponse(OK, status_code=200, headers=CABECALHOS)
    return JSONResponse(ERRO, status_code=503, headers=CABECALHOS)
