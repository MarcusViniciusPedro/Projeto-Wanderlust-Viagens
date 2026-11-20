"""Servico de autenticacao e fluxo de 2FA (RF1/RF2) como funcoes puras.

Este modulo NAO acessa banco de dados diretamente: recebe os dados do usuario
(``CredencialUsuario``) ja carregados e devolve decisoes. Isso permite testar
todo o fluxo de 2FA sem um SQL Server vivo. A camada de router (``router.py``)
e responsavel por buscar/persistir essas credenciais via ``app.db``.

Fluxo de 2FA (RF2):
  etapa 1 (``iniciar_login``): valida email+senha; se ok, emite um TOKEN DE
    DESAFIO curto e assinado e, quando o 2FA esta habilitado, gera o codigo
    TOTP e o envia via SMS (interface ``SMSSender``);
  etapa 2 (``concluir_login``): exige o token de desafio da etapa 1 (reamarra
    as duas chamadas HTTP, que de outra forma seriam independentes e sem
    estado), valida o codigo TOTP e so entao emite o JWT de acesso.

Reamarracao (correcao de seguranca): a etapa 2 NAO reconsulta a credencial so
pelo e-mail enviado pelo cliente. O e-mail vem do ``sub`` do token de desafio,
que so e emitido apos a senha ser validada na etapa 1. Assim, nao e possivel
obter um JWT apresentando apenas e-mail + codigo TOTP: a senha volta a ser um
fator obrigatorio.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from app.core.authz import Papel
from app.core.config import Settings, get_settings
from app.usuarios.schemas import StatusConta
from app.core.security import (
    Desafio2FAInvalidoError,
    criar_token_acesso,
    criar_token_desafio_2fa,
    gerar_codigo_totp,
    validar_token_desafio_2fa,
    verificar_codigo_totp,
    verificar_senha,
)
from app.integracoes.sms import SMSSender

# Reexporta para quem importa o erro a partir do service (camada de router).
__all__ = [
    "CredenciaisInvalidasError",
    "Codigo2FAInvalidoError",
    "Desafio2FAInvalidoError",
    "CredencialUsuario",
    "ResultadoLogin",
    "iniciar_login",
    "concluir_login",
    "AcaoModeracao",
    "ResultadoGuardaModeracao",
    "avaliar_guarda_moderacao",
]


class CredenciaisInvalidasError(RuntimeError):
    """Email/senha invalidos na etapa 1 do login."""


class Codigo2FAInvalidoError(RuntimeError):
    """Codigo 2FA invalido ou expirado na etapa 2 do login."""


@dataclass(frozen=True)
class CredencialUsuario:
    """Dados minimos de autenticacao de um usuario, carregados pela camada db.

    Mantido desacoplado da persistencia para permitir testes sem banco.
    """

    id_usuario: int
    email: str
    senha_hash: str
    totp_secret: Optional[str]
    papel: Papel
    telefone: Optional[str] = None
    # Flag da Credencial (coluna two_factor): quando False, a etapa 2 nao exige
    # o codigo TOTP (mas continua exigindo o token de desafio da etapa 1).
    two_factor: bool = True


# Funcao que carrega a credencial de um usuario pelo e-mail. Injetada pela
# camada de router (que acessa o banco) para manter o service testavel sem DB.
CarregarCredencial = Callable[[str], Optional[CredencialUsuario]]


@dataclass(frozen=True)
class ResultadoLogin:
    """Resultado da etapa 1 do login.

    ``token_desafio`` reamarra a etapa 2 a etapa 1 (so e emitido apos a senha
    ser validada). ``codigo_2fa`` so e preenchido quando o 2FA esta habilitado
    e serve para testes/stubs (nao e exposto na resposta HTTP).
    """

    token_desafio: str
    two_factor: bool
    codigo_2fa: Optional[str] = None


def iniciar_login(
    credencial: Optional[CredencialUsuario],
    senha: str,
    sms_sender: SMSSender,
    settings: Optional[Settings] = None,
) -> ResultadoLogin:
    """Etapa 1 do login (RF2): valida a senha e emite o token de desafio.

    Se o usuario tem o 2FA habilitado (``two_factor``), gera e envia o codigo
    TOTP por SMS. Retorna um ``ResultadoLogin`` com o token de desafio (que a
    etapa 2 precisa apresentar) e o codigo gerado (util para testes/stubs).

    Levanta ``CredenciaisInvalidasError`` se o usuario nao existe ou a senha e
    incorreta. A mesma excecao cobre ambos os casos para nao revelar se o
    e-mail existe.
    """
    settings = settings or get_settings()

    if credencial is None or not verificar_senha(senha, credencial.senha_hash):
        raise CredenciaisInvalidasError("Email ou senha invalidos.")

    token_desafio = criar_token_desafio_2fa(credencial.email, settings=settings)

    codigo: Optional[str] = None
    if credencial.two_factor:
        if not credencial.totp_secret:
            # 2FA habilitado mas sem segredo configurado: estado inconsistente.
            raise CredenciaisInvalidasError("Email ou senha invalidos.")
        codigo = gerar_codigo_totp(credencial.totp_secret)
        destino = credencial.telefone or credencial.email
        sms_sender.enviar(
            destino=destino,
            conteudo=f"Seu codigo de verificacao Wanderlust e {codigo}.",
        )

    return ResultadoLogin(
        token_desafio=token_desafio,
        two_factor=credencial.two_factor,
        codigo_2fa=codigo,
    )


def concluir_login(
    token_desafio: str,
    codigo: str,
    carregar_credencial: "CarregarCredencial",
    settings: Optional[Settings] = None,
) -> str:
    """Etapa 2 do login (RF2): valida o desafio + codigo 2FA e emite o JWT.

    O e-mail do usuario e extraido do ``token_desafio`` (emitido na etapa 1
    apos a senha), nunca de uma entrada arbitraria do cliente. ``carregar_
    credencial`` e a funcao que busca a credencial pelo e-mail (injetada pela
    camada de router para manter o service livre de banco).

    Levanta ``Desafio2FAInvalidoError`` se o desafio for invalido/expirado,
    ``CredenciaisInvalidasError`` se a credencial nao for encontrada e
    ``Codigo2FAInvalidoError`` se o codigo TOTP for invalido/expirado.
    """
    settings = settings or get_settings()

    email = validar_token_desafio_2fa(token_desafio, settings=settings)
    credencial = carregar_credencial(email)
    if credencial is None:
        raise CredenciaisInvalidasError("Email ou senha invalidos.")

    if credencial.two_factor:
        if not credencial.totp_secret or not verificar_codigo_totp(
            credencial.totp_secret, codigo
        ):
            raise Codigo2FAInvalidoError(
                "Codigo de verificacao invalido ou expirado."
            )

    return criar_token_acesso(
        subject=credencial.email,
        papel=credencial.papel.value,
        settings=settings,
        id_usuario=credencial.id_usuario,
    )


# ---------------------------------------------------------------------------
# Guarda anti-lockout da moderacao de contas (Gerenciar Contas, secao 4.1).
# Regra de decisao PURA e testavel sem banco: o router carrega os dados
# (papel/status da conta alvo e contagem de admins ativos) e delega a decisao
# aqui. Protege contra dois erros operacionais irreversiveis: o admin se
# auto-banir/auto-excluir e a remocao do ULTIMO administrador ativo (que
# deixaria o sistema sem ninguem capaz de moderar/gerenciar o catalogo).
# ---------------------------------------------------------------------------


class AcaoModeracao(str, Enum):
    """Acao de moderacao a ser avaliada pela guarda anti-lockout."""

    BANIR = "banir"
    EXCLUIR = "excluir"
    REATIVAR = "reativar"


@dataclass(frozen=True)
class ResultadoGuardaModeracao:
    """Decisao da guarda anti-lockout.

    ``permitido`` indica se a operacao pode seguir. Quando negada, ``motivo``
    traz a mensagem em Portugues e ``codigo_http`` o status HTTP sugerido ao
    router (403 para auto-alvo, 409 para o ultimo admin ativo).
    """

    permitido: bool
    motivo: Optional[str] = None
    codigo_http: Optional[int] = None


def _acao_remove_admin(
    acao: AcaoModeracao, novo_status: "Optional[StatusConta]"
) -> bool:
    """Diz se a acao tira um administrador do estado ativo (banir/excluir).

    Reativar (REATIVAR, ou alteracao de status para 'Ativo') nunca remove.
    Banir/denunciar e excluir removem o admin do estado ativo.
    """
    if acao == AcaoModeracao.REATIVAR:
        return False
    if novo_status is not None and novo_status == StatusConta.ATIVO:
        return False
    return acao in (AcaoModeracao.BANIR, AcaoModeracao.EXCLUIR)


def avaliar_guarda_moderacao(
    *,
    id_alvo: int,
    id_admin_atual: int,
    papel_alvo: Papel,
    acao: AcaoModeracao,
    admins_ativos: int,
    novo_status: "Optional[StatusConta]" = None,
) -> ResultadoGuardaModeracao:
    """Decide se uma acao de moderacao pode seguir (guarda anti-lockout).

    Parametros:
      id_alvo: id da conta sobre a qual a acao recai (vindo do path).
      id_admin_atual: id do administrador autenticado (vindo do JWT).
      papel_alvo: papel atual da conta alvo.
      acao: banir/excluir/reativar que esta sendo tentada.
      admins_ativos: numero de administradores com status 'Ativo' no banco.
      novo_status: para a alteracao de status, o status pretendido (usado para
        distinguir reativacao de banimento/denuncia).

    Regras (todas negam a operacao com mensagem clara):
      (a) o admin NAO pode banir/excluir/rebaixar a PROPRIA conta (403): evita
          que alguem se tranque para fora por engano.
      (b) o ULTIMO administrador ativo NAO pode ser banido/excluido (409): o
          sistema ficaria sem ninguem para moderar contas e gerenciar o
          catalogo. Reativar nunca e bloqueado.

    Reativar a propria conta ou a de outro admin e sempre permitido.
    """
    remove = _acao_remove_admin(acao, novo_status)

    # Reativacao (ou qualquer acao que mantem o admin ativo) e sempre liberada.
    if not remove:
        return ResultadoGuardaModeracao(permitido=True)

    # (a) auto-alvo: o admin tentando banir/excluir a propria conta.
    if id_alvo == id_admin_atual:
        return ResultadoGuardaModeracao(
            permitido=False,
            motivo=(
                "Um administrador nao pode banir ou excluir a propria conta. "
                "Peca a outro administrador para realizar esta operacao."
            ),
            codigo_http=403,
        )

    # (b) ultimo admin ativo: nao permitir remover o unico admin restante.
    if papel_alvo == Papel.ADMINISTRADOR and admins_ativos <= 1:
        return ResultadoGuardaModeracao(
            permitido=False,
            motivo=(
                "Nao e possivel banir ou excluir o ultimo administrador ativo. "
                "Promova ou ative outro administrador antes de continuar."
            ),
            codigo_http=409,
        )

    return ResultadoGuardaModeracao(permitido=True)
