"""IP do cliente atrás de proxy reverso. Infraestrutura (sem regra de negócio).

Ordem de decisão, só quando a conexão direta vem de um proxy confiável
(OS_PROXIES_CONFIAVEIS; padrão 10.0.0.0/8 mais loopback):
1. ``True-Client-Ip`` (Render e Cloudflare), se for um IP válido;
2. ``X-Forwarded-For`` lido da DIREITA para a ESQUERDA, pulando endereços confiáveis:
   o primeiro não confiável é o cliente. A entrada mais à esquerda nunca é usada por
   ser a primeira (o cliente pode escrevê-la);
3. senão, o endereço da conexão direta.
De uma conexão que não vem de proxy confiável nenhum cabeçalho é aceito.

O middleware ASGI reescreve ``scope["client"]``; o flet-web lê ``websocket.client.host``
e o entrega em ``Page.client_ip``.
"""

from __future__ import annotations

import ipaddress
import logging
import os
from collections.abc import Iterable

logger = logging.getLogger(__name__)

VARIAVEL_PROXIES = "OS_PROXIES_CONFIAVEIS"
VARIAVEL_DEPURACAO = "OS_DEPURAR_CABECALHOS_IP"
PROXIES_PADRAO = "10.0.0.0/8"
LOOPBACK = ("127.0.0.0/8", "::1/128")
CABECALHOS_DE_DEPURACAO = (
    b"true-client-ip",
    b"x-forwarded-for",
    b"x-forwarded-proto",
    b"x-real-ip",
    b"forwarded",
    b"cf-connecting-ip",
)

Rede = ipaddress.IPv4Network | ipaddress.IPv6Network


def ler_redes(texto: str | None) -> tuple[Rede, ...]:
    """'10.0.0.0/8, 192.168.1.5' -> redes. Loopback é sempre incluído.

    Entrada inválida levanta ValueError (o app não deve iniciar com ela). ``*`` é recusado.
    """
    texto = (texto or "").strip() or PROXIES_PADRAO
    redes: list[Rede] = []
    for parte in [*texto.split(","), *LOOPBACK]:
        parte = parte.strip()
        if not parte:
            continue
        if parte == "*":
            raise ValueError(f"{VARIAVEL_PROXIES} não aceita '*': informe IPs ou redes.")
        try:
            redes.append(ipaddress.ip_network(parte, strict=False))
        except ValueError:
            raise ValueError(f"{VARIAVEL_PROXIES}: endereço inválido {parte!r}.") from None
    return tuple(redes)


def ip_valido(valor: str | None) -> str | None:
    """Texto -> IP normalizado, ou None. Aceita 'IPv4:porta' e '[IPv6]:porta'."""
    if not valor:
        return None
    valor = valor.strip().strip('"')
    if valor.startswith("["):
        fim = valor.find("]")
        valor = valor[1:fim] if fim > 0 else ""
    elif valor.count(":") == 1:  # IPv4 com porta
        valor = valor.split(":", 1)[0]
    try:
        return str(ipaddress.ip_address(valor))
    except ValueError:
        return None


def confiavel(ip: str | None, redes: Iterable[Rede]) -> bool:
    if ip is None:
        return False
    endereco = ipaddress.ip_address(ip)
    return any(endereco in rede for rede in redes)


def resolver_ip(par: str | None, cabecalhos: dict[str, str], redes: tuple[Rede, ...]) -> str | None:
    """IP do cliente. ``par``: endereço da conexão direta; ``cabecalhos``: nomes minúsculos."""
    direto = ip_valido(par)
    if not confiavel(direto, redes):
        return direto  # não veio de proxy confiável: cabeçalhos ignorados
    verdadeiro = ip_valido(cabecalhos.get("true-client-ip"))
    if verdadeiro:
        return verdadeiro
    entradas = [e for e in cabecalhos.get("x-forwarded-for", "").split(",") if e.strip()]
    for entrada in reversed(entradas):
        ip = ip_valido(entrada)
        if ip is None:
            break  # lixo no meio da cadeia: não dá para confiar no que está à esquerda
        if not confiavel(ip, redes):
            return ip
    return direto


class ResolverIpCliente:
    """Middleware ASGI: aplica ``resolver_ip`` a pedidos HTTP e WebSocket."""

    def __init__(self, app, redes: tuple[Rede, ...] | None = None, depurar: bool | None = None):
        self.app = app
        self.redes = redes if redes is not None else ler_redes(os.environ.get(VARIAVEL_PROXIES))
        if depurar is None:
            depurar = os.environ.get(VARIAVEL_DEPURACAO, "") == "1"
        self.depurar = depurar
        if depurar:
            logger.warning(
                "%s=1: os cabeçalhos de encaminhamento e IPs crus vão para o log. "
                "Desligue depois de conferir.",
                VARIAVEL_DEPURACAO,
            )

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            cliente = scope.get("client")
            par = cliente[0] if cliente else None
            cabecalhos: dict[str, str] = {}
            for nome, valor in scope.get("headers", []):
                texto = valor.decode("latin1")
                chave = nome.decode("latin1").lower()
                # Cabeçalhos repetidos se juntam na ordem (como o X-Forwarded-For pede).
                anterior = cabecalhos.get(chave)
                cabecalhos[chave] = texto if anterior is None else f"{anterior}, {texto}"
            ip = resolver_ip(par, cabecalhos, self.redes)
            if self.depurar:
                logger.warning(
                    "Depuração de IP: tipo=%s par=%s escolhido=%s cabeçalhos=%s",
                    scope["type"],
                    par,
                    ip,
                    {
                        n.decode(): cabecalhos[n.decode()]
                        for n in CABECALHOS_DE_DEPURACAO
                        if n.decode() in cabecalhos
                    },
                )
            scope = dict(scope)
            if ip is not None and ip != par:
                scope["client"] = (ip, 0)
            proto = cabecalhos.get("x-forwarded-proto", "").strip().lower()
            if confiavel(ip_valido(par), self.redes) and proto in ("http", "https"):
                if scope["type"] == "websocket":
                    scope["scheme"] = "wss" if proto == "https" else "ws"
                else:
                    scope["scheme"] = proto
        await self.app(scope, receive, send)
