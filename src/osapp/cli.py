"""Administração pela linha de comando.  Uso: python -m osapp.cli <comando>

Senhas são sempre lidas com getpass, nunca dos argumentos.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from osapp import exportacao_legada
from osapp.config import ConfigError
from osapp.logs import configurar_logging
from osapp.services import administracao, ordens
from osapp.services.erros import (
    ErroConflito,
    ErroDominio,
    ErroNaoEncontrado,
    ErroPermissao,
    ErroValidacao,
)


def _perguntar(valor: str | None, rotulo: str) -> str:
    return valor if valor is not None else input(f"{rotulo}: ")


def _ler_senha() -> str:
    senha = getpass.getpass("Senha: ")
    if getpass.getpass("Repita a senha: ") != senha:
        raise ErroValidacao("senha", "As senhas não conferem.")
    return senha


def _criar_filial(args) -> str:
    filial = administracao.criar_filial(
        _perguntar(args.codigo, "Código"), _perguntar(args.nome, "Nome")
    )
    return f"Filial {filial.codigo} criada."


def _criar_usuario(args) -> str:
    nome = _perguntar(args.nome, "Nome")
    login = _perguntar(args.login, "Login")
    filial = _perguntar(args.filial, "Código da filial")
    papel = "admin" if args.admin else args.papel
    usuario = administracao.criar_usuario(
        nome, login, _ler_senha(), filial, False, args.gerente, papel=papel, temporaria=True
    )
    extra = ", gerente" if usuario.is_gerente else ""
    return (
        f"Usuário {usuario.login} criado na filial {usuario.filial_codigo} "
        f"(papel {usuario.papel}{extra}). A senha é temporária: será trocada no primeiro login."
    )


def _definir_perfil(args) -> str:
    administracao.definir_perfil(_perguntar(args.login, "Login"), args.perfil)
    return f"Perfil alterado para {args.perfil}."


def _consolidar_1007(args) -> str:
    if args.aplicar:
        if not args.responsavel:
            raise ErroValidacao(
                "responsavel", "Informe --responsavel com o login de um administrador."
            )
        plano = administracao.aplicar_consolidacao(args.responsavel)
        titulo = "APLICADO"
    else:
        plano = administracao.planejar_consolidacao()
        titulo = "SIMULAÇÃO (nada foi alterado; para aplicar use --aplicar --responsavel LOGIN)"
    linhas = [titulo, f"Filial de destino: {plano.filial_destino}", "Filiais de origem:"]
    linhas += [f"  {f}" for f in plano.filiais_de_origem] or ["  (nenhuma)"]
    for rotulo, itens in (
        ("Usuários a desativar", plano.desativar_usuarios),
        ("Usuários a mover para 1007", plano.mover_usuarios),
        ("OS a mover para 1007", plano.mover_ordens),
    ):
        linhas.append(f"{rotulo}: {len(itens)}")
        linhas += [f"  {item}" for item in itens]
    return "\n".join(linhas)


def _verificar_eventos_status(_args) -> str:
    """Só leitura: lista as ordens cujo histórico de status não bate com as colunas."""
    achados = administracao.verificar_eventos_status()
    if not achados:
        return "Nenhuma divergência entre eventos de status e colunas de instante."
    linhas = [f"{d.numero}: {d.problema}" for d in achados]
    return "\n".join([*linhas, f"{len(achados)} divergência(s)."])


def _recalcular_busca(_args) -> str:
    resultado = administracao.recalcular_busca()
    return (
        f"Busca recalculada: {resultado['ordens']} ordem(ns) e {resultado['itens']} item(ns) "
        "alterados."
    )


def _redefinir_senha(args) -> str:
    login = _perguntar(args.login, "Login")
    administracao.redefinir_senha(login, _ler_senha())
    return "Senha redefinida (temporária: será trocada no próximo login)."


def _limpar_tentativas(_args) -> str:
    apagadas = administracao.limpar_tentativas_antigas()
    return f"{apagadas} contador(es) de falha de login apagado(s)."


def _previa_papeis(_args) -> str:
    linhas = administracao.previa_papeis()
    largura = max([len("login"), *(len(p.login) for p in linhas)])
    saida = [f"{'login':<{largura}}  filial  is_admin  papel"]
    for p in linhas:
        saida.append(
            f"{p.login:<{largura}}  {p.filial_codigo:<6}  {'sim' if p.is_admin else 'não':<8}  "
            f"{p.papel_proposto}"
        )
    saida.append(f"{len(linhas)} usuário(s). Nada foi alterado.")
    return "\n".join(saida)


def _definir_papel(args) -> str:
    administracao.definir_papel(args.login, args.papel)
    return "Papel alterado."


def _reclassificar_origem(args) -> str:
    r = ordens.reclassificar_origem(args.responsavel, args.numero, args.origem, args.aplicar)
    if r.aplicada:
        return f"OS {r.numero}: origem {r.origem_atual} -> {r.origem_nova}."
    if r.origem_atual == r.origem_nova:
        return f"OS {r.numero} já tem origem {r.origem_atual}. Nada a fazer."
    return (
        f"OS {r.numero}: origem {r.origem_atual} -> {r.origem_nova} (prévia; nada foi "
        "alterado; use --aplicar)."
    )


def _desativar_usuario(args) -> str:
    administracao.desativar_usuario(_perguntar(args.login, "Login"))
    return "Usuário desativado."


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m osapp.cli", description="Sistema de OS")
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("criar-filial", help="Cria uma filial")
    p.add_argument("--codigo")
    p.add_argument("--nome")
    p.set_defaults(func=_criar_filial)

    p = sub.add_parser("criar-usuario", help="Cria um usuário (a senha é pedida)")
    p.add_argument("--nome")
    p.add_argument("--login")
    p.add_argument("--filial", help="Código da filial")
    perfil = p.add_mutually_exclusive_group()
    perfil.add_argument("--admin", action="store_true", help="O mesmo que --papel admin")
    perfil.add_argument("--gerente", action="store_true", help="Cria como gerente da filial")
    p.add_argument(
        "--papel",
        choices=administracao.PAPEIS,
        default="manutencao",
        help="usuario (abre solicitações), manutencao (padrão) ou admin",
    )
    p.set_defaults(func=_criar_usuario)

    p = sub.add_parser("definir-perfil", help="Muda o perfil de um usuário")
    p.add_argument("--login")
    p.add_argument("--perfil", required=True, choices=administracao.PERFIS)
    p.set_defaults(func=_definir_perfil)

    p = sub.add_parser(
        "consolidar-1007",
        help="Lista (ou aplica) a passagem de usuários e OS para a filial 1007; nada é apagado",
    )
    p.add_argument("--aplicar", action="store_true", help="Aplica de fato (padrão: só lista)")
    p.add_argument("--responsavel", help="Login do administrador que aplica")
    p.set_defaults(func=_consolidar_1007)

    p = sub.add_parser(
        "recalcular-busca",
        help="Recalcula o texto de busca de todas as ordens e itens (pode repetir)",
    )
    p.set_defaults(func=_recalcular_busca)

    p = sub.add_parser(
        "verificar-eventos-status",
        help="Confere o histórico de status com as colunas de instante (só leitura)",
    )
    p.set_defaults(func=_verificar_eventos_status)

    exportacao_legada.registrar_comando(sub)  # exportação antes da migração 0010

    p = sub.add_parser(
        "previa-papeis",
        help="Lista login, filial e papel de cada usuário (não altera nada)",
    )
    p.set_defaults(func=_previa_papeis)

    p = sub.add_parser("definir-papel", help="Corrige o papel: usuario, manutencao ou admin")
    p.add_argument("login")
    p.add_argument("papel", choices=administracao.PAPEIS)
    p.set_defaults(func=_definir_papel)

    p = sub.add_parser(
        "reclassificar-origem",
        help="Muda a origem de uma OS antiga (administrador; prévia sem --aplicar)",
    )
    p.add_argument("numero")
    p.add_argument("origem", choices=("solicitacao", "manutencao"))
    p.add_argument("--responsavel", required=True, help="Login do administrador")
    p.add_argument("--aplicar", action="store_true", help="Aplica de fato (padrão: só mostra)")
    p.set_defaults(func=_reclassificar_origem)

    p = sub.add_parser(
        "limpar-tentativas",
        help="Apaga contadores de falha de login expirados (o app também limpa sozinho)",
    )
    p.set_defaults(func=_limpar_tentativas)

    p = sub.add_parser("redefinir-senha", help="Redefine a senha e zera o atraso do login")
    p.add_argument("--login")
    p.set_defaults(func=_redefinir_senha)

    p = sub.add_parser("desativar-usuario", help="Desativa um usuário")
    p.add_argument("--login")
    p.set_defaults(func=_desativar_usuario)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = criar_parser().parse_args(argv)
    try:
        configurar_logging()
    except ConfigError as exc:
        print(f"Erro de configuração: {exc}", file=sys.stderr)
        return 1
    try:
        print(args.func(args))
    except ConfigError as exc:
        print(f"Erro de configuração: {exc}", file=sys.stderr)
        return 1
    except ErroValidacao as exc:
        print(f"Erro: {exc.mensagem}", file=sys.stderr)
        return 1
    except ErroConflito:
        print("Erro: já existe um registro com esse código ou login.", file=sys.stderr)
        return 1
    except ErroNaoEncontrado:
        print("Erro: registro não encontrado.", file=sys.stderr)
        return 1
    except ErroPermissao:
        print("Erro: é preciso um administrador ativo (--responsavel).", file=sys.stderr)
        return 1
    except ErroDominio:
        print("Erro: não foi possível concluir a operação.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
