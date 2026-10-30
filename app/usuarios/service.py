"""Servico de autenticacao e fluxo de 2FA (RF1/RF2) como funcoes puras.

Este modulo NAO acessa banco de dados diretamente: recebe os dados do usuario
(``CredencialUsuario``) ja carregados e devolve decisoes. Isso permite testar
todo o fluxo de 2FA sem um SQL Server vivo. A camada de router (``router.py``)
e responsavel por buscar/persistir essas credenciais via ``app.db``.

Fluxo de 2FA (RF2):
  etapa 1 (``iniciar_login``): valida email+senha; se ok, gera o codigo TOTP e
    o envia via SMS (interface ``SMSSender``);
  etapa 2 (``concluir_login``): valida o codigo; se ok, emite um JWT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.core.authz import Papel
from app.core.config import Settings, get_settings
from app.core.security import (
    criar_token_acesso,
    gerar_codigo_totp,
    verificar_codigo_totp,
    verificar_senha,
)
from app.integracoes.sms import SMSSender


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
    totp_secret: str
    papel: Papel
    telefone: Optional[str] = None


def iniciar_login(
    credencial: Optional[CredencialUsuario],
    senha: str,
    sms_sender: SMSSender,
    settings: Optional[Settings] = None,
) -> str:
    """Etapa 1 do login (RF2): valida senha e envia o codigo 2FA por SMS.

    Retorna o codigo gerado (util para testes/stubs). Levanta
    ``CredenciaisInvalidasError`` se o usuario nao existe ou a senha e incorreta.
    A mesma excecao e usada em ambos os casos para nao revelar se o email existe.
    """
    settings = settings or get_settings()

    if credencial is None or not verificar_senha(senha, credencial.senha_hash):
        raise CredenciaisInvalidasError("Email ou senha invalidos.")

    codigo = gerar_codigo_totp(credencial.totp_secret)
    destino = credencial.telefone or credencial.email
    sms_sender.enviar(
        destino=destino,
        conteudo=f"Seu codigo de verificacao Wanderlust e {codigo}.",
    )
    return codigo


def concluir_login(
    credencial: Optional[CredencialUsuario],
    codigo: str,
    settings: Optional[Settings] = None,
) -> str:
    """Etapa 2 do login (RF2): valida o codigo 2FA e emite o JWT.

    Levanta ``CredenciaisInvalidasError`` se o usuario nao existe e
    ``Codigo2FAInvalidoError`` se o codigo e invalido/expirado.
    """
    settings = settings or get_settings()

    if credencial is None:
        raise CredenciaisInvalidasError("Email ou senha invalidos.")

    if not verificar_codigo_totp(credencial.totp_secret, codigo):
        raise Codigo2FAInvalidoError("Codigo de verificacao invalido ou expirado.")

    return criar_token_acesso(
        subject=credencial.email,
        papel=credencial.papel.value,
        settings=settings,
    )
