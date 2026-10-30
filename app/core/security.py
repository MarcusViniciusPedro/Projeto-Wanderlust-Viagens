"""Primitivas de seguranca: hash de senha, JWT e codigos 2FA (TOTP).

Todas as funcoes sao puras no sentido de nao dependerem de banco de dados, o
que permite testa-las isoladamente. Nenhum segredo e hardcoded: chaves e
issuer sao lidos de ``Settings`` (variaveis de ambiente / .env), conforme
RNF3/LGPD.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
import pyotp
from jose import JWTError, jwt

from app.core.config import Settings, get_settings


class TokenInvalidoError(RuntimeError):
    """Levantado quando um token JWT e invalido ou expirado."""


# --- Hash de senha --------------------------------------------------------
# Usa a biblioteca ``bcrypt`` diretamente (backend de ``passlib[bcrypt]``). O
# bcrypt limita a senha a 72 bytes; o truncamento e aplicado de forma explicita
# e consistente no hash e na verificacao. Senhas NUNCA sao armazenadas em texto
# puro (RNF3/LGPD).
_BCRYPT_MAX_BYTES = 72


def _preparar(senha: str) -> bytes:
    """Codifica e trunca a senha para o limite de 72 bytes do bcrypt."""
    return senha.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_senha(senha: str) -> str:
    """Gera o hash bcrypt de uma senha em texto puro."""
    return bcrypt.hashpw(_preparar(senha), bcrypt.gensalt()).decode("utf-8")


def verificar_senha(senha: str, senha_hash: str) -> bool:
    """Verifica se ``senha`` corresponde ao ``senha_hash`` armazenado."""
    try:
        return bcrypt.checkpw(_preparar(senha), senha_hash.encode("utf-8"))
    except (ValueError, TypeError):
        # Hash malformado -> tratado como falha de verificacao, nunca sucesso.
        return False


# --- JWT -------------------------------------------------------------------
def _jwt_secret(settings: Settings) -> str:
    """Obtem o segredo JWT de Settings; erro claro se ausente (sem default)."""
    if not settings.jwt_secret:
        raise TokenInvalidoError(
            "JWT nao configurado. Defina WANDERLUST_JWT_SECRET."
        )
    return settings.jwt_secret


def criar_token_acesso(
    subject: str,
    papel: str,
    settings: Optional[Settings] = None,
    expira_em_minutos: Optional[int] = None,
) -> str:
    """Emite um JWT assinado contendo ``sub`` (usuario) e ``papel``."""
    settings = settings or get_settings()
    minutos = (
        expira_em_minutos
        if expira_em_minutos is not None
        else settings.jwt_expire_minutes
    )
    agora = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "papel": papel,
        "iat": agora,
        "exp": agora + timedelta(minutes=minutos),
    }
    return jwt.encode(payload, _jwt_secret(settings), algorithm=settings.jwt_algorithm)


def decodificar_token(token: str, settings: Optional[Settings] = None) -> dict[str, Any]:
    """Valida e decodifica um JWT; levanta ``TokenInvalidoError`` se invalido."""
    settings = settings or get_settings()
    try:
        return jwt.decode(
            token, _jwt_secret(settings), algorithms=[settings.jwt_algorithm]
        )
    except JWTError as exc:
        raise TokenInvalidoError("Token invalido ou expirado.") from exc


# --- 2FA / TOTP ------------------------------------------------------------
def gerar_segredo_totp() -> str:
    """Gera um novo segredo base32 para configurar o TOTP de um usuario."""
    return pyotp.random_base32()


def gerar_codigo_totp(segredo: str) -> str:
    """Gera o codigo TOTP atual para um segredo."""
    return pyotp.TOTP(segredo).now()


def verificar_codigo_totp(segredo: str, codigo: str, janela: int = 1) -> bool:
    """Verifica um codigo TOTP.

    ``janela`` permite tolerar pequenas defasagens de relogio (cada passo e de
    30s). Codigos invalidos ou expirados retornam False.
    """
    if not codigo:
        return False
    return pyotp.TOTP(segredo).verify(codigo, valid_window=janela)


def uri_provisionamento_totp(
    segredo: str, nome_conta: str, settings: Optional[Settings] = None
) -> str:
    """URI otpauth:// para configurar o TOTP em um app autenticador."""
    settings = settings or get_settings()
    return pyotp.TOTP(segredo).provisioning_uri(
        name=nome_conta, issuer_name=settings.totp_issuer
    )
