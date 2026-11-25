"""Guia rápido (prompt 39): o texto do botão '?' de cada tela, lido de docs/guia/guia.yaml.

- O arquivo é editado por quem não programa (docs/guia/COMO_EDITAR.md). É validado (telas e
  papéis conhecidos, campos obrigatórios, tamanho do texto) e guardado em cache; quando o
  arquivo muda (data de modificação), é relido.
- Arquivo inválido nunca derruba o app: fica a última versão válida e um aviso vai para o
  log.
- Ordem de escolha: o bloco do papel; senão, 'todos'; senão, nada (o '?' some).
- O guia só explica: nunca decide o que alguém pode fazer. E nunca entrega o texto de um
  papel que o usuário não tem.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from osapp import config
from osapp.ui import rotas

logger = logging.getLogger(__name__)

PAPEIS = ("usuario", "manutencao", "admin")
TODOS = "todos"
TELAS = tuple(rotas.TABELA)  # os nomes das rotas (ui/rotas.py) são os ids das telas
TITULO_MAX = 80
LINHAS_MIN, LINHAS_MAX = 3, 8
TEXTO_MAX = 1200


@dataclass(frozen=True)
class Entrada:
    titulo: str
    texto: str  # Markdown


@dataclass(frozen=True)
class Guia:
    telas: dict[str, dict[str, Entrada]] = field(default_factory=dict)
    sem_ajuda: tuple[str, ...] = ()


class GuiaInvalido(ValueError):
    pass


def validar(dados: object) -> Guia:
    """Dados do YAML -> Guia, ou GuiaInvalido com uma lista legível dos problemas."""
    problemas: list[str] = []
    if not isinstance(dados, dict) or not isinstance(dados.get("telas"), dict):
        raise GuiaInvalido("O arquivo precisa de uma seção 'telas'.")
    telas: dict[str, dict[str, Entrada]] = {}
    for tela, blocos in dados["telas"].items():
        if tela not in TELAS:
            problemas.append(f"tela desconhecida: {tela!r}")
            continue
        if not isinstance(blocos, dict) or not blocos:
            problemas.append(f"{tela}: sem blocos de papel")
            continue
        telas[tela] = {}
        for papel, bloco in blocos.items():
            onde = f"{tela}/{papel}"
            if papel not in (*PAPEIS, TODOS):
                problemas.append(f"{onde}: papel desconhecido")
                continue
            if not isinstance(bloco, dict):
                problemas.append(f"{onde}: precisa de 'titulo' e 'texto'")
                continue
            titulo, texto = bloco.get("titulo"), bloco.get("texto")
            if not isinstance(titulo, str) or not 1 <= len(titulo.strip()) <= TITULO_MAX:
                problemas.append(f"{onde}: 'titulo' de 1 a {TITULO_MAX} caracteres")
                continue
            if not isinstance(texto, str) or len(texto) > TEXTO_MAX:
                problemas.append(f"{onde}: 'texto' obrigatório, até {TEXTO_MAX} caracteres")
                continue
            linhas = [x for x in texto.strip().splitlines() if x.strip()]
            if not LINHAS_MIN <= len(linhas) <= LINHAS_MAX:
                problemas.append(f"{onde}: 'texto' com {LINHAS_MIN} a {LINHAS_MAX} linhas")
                continue
            telas[tela][papel] = Entrada(titulo.strip(), texto.strip())
    sem_ajuda = dados.get("sem_ajuda") or []
    if not isinstance(sem_ajuda, list) or any(t not in TELAS for t in sem_ajuda):
        problemas.append("'sem_ajuda' deve listar nomes de telas conhecidos")
        sem_ajuda = []
    if problemas:
        raise GuiaInvalido("; ".join(problemas))
    return Guia(telas, tuple(sem_ajuda))


def carregar_arquivo(caminho: Path) -> Guia:
    try:
        dados = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise GuiaInvalido(f"não foi possível ler o arquivo ({type(exc).__name__})") from exc
    return validar(dados)


class _Cache:
    def __init__(self) -> None:
        self._trava = threading.Lock()
        self._guia = Guia()
        self._carimbo: tuple[str, float] | None = None

    def atual(self) -> Guia:
        caminho = Path(config.guia_arquivo())
        try:
            carimbo = (str(caminho), caminho.stat().st_mtime)
        except OSError:
            carimbo = (str(caminho), -1.0)
        with self._trava:
            if carimbo != self._carimbo:
                self._carimbo = carimbo
                try:
                    self._guia = carregar_arquivo(caminho)
                    logger.info("Guia rápido carregado de %s.", caminho.name)
                except GuiaInvalido as exc:
                    logger.warning("Guia rápido inválido; mantida a última versão: %s", exc)
            return self._guia


_cache = _Cache()


def entrada(tela: str, papel: str) -> Entrada | None:
    """O texto da tela para o papel: o do papel, senão 'todos', senão None (o '?' some).
    Nunca o de outro papel. Sem papel (login, antes de entrar): só 'todos'."""
    blocos = _cache.atual().telas.get(tela, {})
    if papel not in PAPEIS:
        return blocos.get(TODOS)
    return blocos.get(papel) or blocos.get(TODOS)


def faltando(guia: Guia, telas_por_papel: dict[str, tuple[str, ...]]) -> list[str]:
    """'tela/papel' sem texto (nem do papel nem 'todos') e fora de 'sem_ajuda'."""
    saida = []
    for tela, papeis in telas_por_papel.items():
        if tela in guia.sem_ajuda:
            continue
        blocos = guia.telas.get(tela, {})
        for papel in papeis:
            if papel not in blocos and TODOS not in blocos:
                saida.append(f"{tela}/{papel}")
    return saida


# Quem abre cada tela hoje (inspeção do prompt 39). O serviço é quem decide; isto só serve
# para a conferência do guia.
TELAS_POR_PAPEL: dict[str, tuple[str, ...]] = {
    "login": PAPEIS,
    "trocar_senha": PAPEIS,
    "home": PAPEIS,
    "solicitacao_nova": PAPEIS,
    "os_nova": ("manutencao", "admin"),
    "os_detalhe": PAPEIS,
    "os_assumir": ("manutencao", "admin"),
    "os_editar": ("manutencao", "admin"),
    "os_solicitacao": ("usuario", "admin"),
    "os_concluir": ("manutencao", "admin"),
    "relatorios": ("manutencao", "admin"),
    "relatorios_mensal": ("manutencao", "admin"),
    "perfil": PAPEIS,
    "alterar_senha": PAPEIS,
    "configuracoes": PAPEIS,
    "usuarios": ("admin",),
    "usuario_novo": ("admin",),
    "usuario": ("admin",),
    "lixeira": ("admin",),
    "lixeira_detalhe": ("admin",),
    "especialidades": ("admin",),
    "sla": ("admin",),
    "motivos_cancelamento": ("admin",),
}
