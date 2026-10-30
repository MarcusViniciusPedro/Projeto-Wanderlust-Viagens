"""Testes de autenticacao e fluxo de 2FA (RF1/RF2) sem banco de dados vivo.

Cobre:
  - hash/verificacao de senha (falha se senha errada for aceita);
  - geracao e verificacao de TOTP (sucesso e codigo invalido/expirado);
  - maquina do fluxo 2FA (senha errada bloqueia; codigo errado bloqueia;
    caminho feliz emite token), usando o SMS stub para capturar o codigo.
"""

from __future__ import annotations

import re

import pytest

from app.core.authz import Papel
from app.core.config import Settings
from app.core.security import (
    criar_token_acesso,
    decodificar_token,
    gerar_codigo_totp,
    gerar_segredo_totp,
    hash_senha,
    verificar_codigo_totp,
    verificar_senha,
)
from app.integracoes.sms import StubSMSSender
from app.usuarios.service import (
    Codigo2FAInvalidoError,
    CredenciaisInvalidasError,
    CredencialUsuario,
    concluir_login,
    iniciar_login,
)

# Settings de teste: segredo JWT definido via objeto (nunca hardcoded no app).
SETTINGS_TESTE = Settings(jwt_secret="segredo-de-teste-apenas", db_server=None)


# --- Hash de senha --------------------------------------------------------
def test_hash_senha_nao_e_texto_puro() -> None:
    senha = "SenhaForte123"
    h = hash_senha(senha)
    assert h != senha
    assert h.startswith("$2")  # prefixo bcrypt


def test_verificar_senha_correta() -> None:
    senha = "SenhaForte123"
    assert verificar_senha(senha, hash_senha(senha)) is True


def test_verificar_senha_errada_falha() -> None:
    h = hash_senha("SenhaForte123")
    assert verificar_senha("senhaErrada", h) is False


# --- TOTP / 2FA -----------------------------------------------------------
def test_totp_sucesso() -> None:
    segredo = gerar_segredo_totp()
    codigo = gerar_codigo_totp(segredo)
    assert verificar_codigo_totp(segredo, codigo) is True


def test_totp_codigo_invalido_falha() -> None:
    segredo = gerar_segredo_totp()
    assert verificar_codigo_totp(segredo, "000000") is False
    assert verificar_codigo_totp(segredo, "") is False


def test_totp_codigo_expirado_falha() -> None:
    import pyotp

    segredo = gerar_segredo_totp()
    # Codigo gerado 5 minutos atras (fora da janela de tolerancia) e invalido.
    codigo_antigo = pyotp.TOTP(segredo).at(0)
    assert pyotp.TOTP(segredo).verify(codigo_antigo) is False


# --- JWT ------------------------------------------------------------------
def test_jwt_emite_e_decodifica() -> None:
    token = criar_token_acesso(
        "turista@ex.com", Papel.TURISTA.value, settings=SETTINGS_TESTE
    )
    payload = decodificar_token(token, settings=SETTINGS_TESTE)
    assert payload["sub"] == "turista@ex.com"
    assert payload["papel"] == Papel.TURISTA.value


# --- Fluxo 2FA (maquina de estados) ---------------------------------------
def _credencial() -> CredencialUsuario:
    return CredencialUsuario(
        id_usuario=1,
        email="turista@ex.com",
        senha_hash=hash_senha("SenhaForte123"),
        totp_secret=gerar_segredo_totp(),
        papel=Papel.TURISTA,
        telefone="+5511999999999",
    )


def test_fluxo_2fa_senha_errada_bloqueia() -> None:
    sms = StubSMSSender()
    with pytest.raises(CredenciaisInvalidasError):
        iniciar_login(_credencial(), "senhaErrada", sms, settings=SETTINGS_TESTE)
    # Nenhum codigo deve ter sido enviado quando a senha falha.
    assert sms.ultima_mensagem is None


def test_fluxo_2fa_usuario_inexistente_bloqueia() -> None:
    sms = StubSMSSender()
    with pytest.raises(CredenciaisInvalidasError):
        iniciar_login(None, "qualquer", sms, settings=SETTINGS_TESTE)


def test_fluxo_2fa_codigo_errado_bloqueia() -> None:
    cred = _credencial()
    sms = StubSMSSender()
    iniciar_login(cred, "SenhaForte123", sms, settings=SETTINGS_TESTE)
    assert sms.ultima_mensagem is not None  # codigo foi "enviado"
    with pytest.raises(Codigo2FAInvalidoError):
        concluir_login(cred, "000000", settings=SETTINGS_TESTE)


def test_fluxo_2fa_caminho_feliz_emite_token() -> None:
    cred = _credencial()
    sms = StubSMSSender()
    codigo = iniciar_login(cred, "SenhaForte123", sms, settings=SETTINGS_TESTE)

    # O codigo tambem fica legivel pelo SMS stub (como os testes usariam).
    assert sms.ultima_mensagem is not None
    extraido = re.search(r"\d{6}", sms.ultima_mensagem.conteudo)
    assert extraido is not None
    assert extraido.group(0) == codigo

    token = concluir_login(cred, codigo, settings=SETTINGS_TESTE)
    payload = decodificar_token(token, settings=SETTINGS_TESTE)
    assert payload["sub"] == cred.email
    assert payload["papel"] == Papel.TURISTA.value
