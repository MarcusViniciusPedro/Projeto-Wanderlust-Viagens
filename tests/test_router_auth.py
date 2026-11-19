"""Testes de router da autenticacao (RF1/RF2) com FastAPI TestClient.

Exercitam a composicao dos endpoints HTTP (etapas 1 e 2 do 2FA) sem SQL Server
vivo: a camada ``app.usuarios.repository`` e substituida por fakes via
monkeypatch e o segredo JWT e definido por variavel de ambiente. Estes testes
cobrem especificamente a reamarracao da senha (o bug que passou verde por
falta de teste de router): a etapa 2 so emite o JWT se apresentar o
``token_desafio`` emitido pela etapa 1 apos a validacao da senha.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.authz import Papel
from app.core.config import get_settings
from app.core.security import hash_senha, gerar_segredo_totp, gerar_codigo_totp
from app.usuarios.service import CredencialUsuario


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient com JWT configurado por env e cache de settings limpo."""
    monkeypatch.setenv("WANDERLUST_JWT_SECRET", "segredo-de-teste-router")
    get_settings.cache_clear()
    import app.main as main

    try:
        yield TestClient(main.app)
    finally:
        get_settings.cache_clear()


def _credencial(two_factor: bool = True) -> CredencialUsuario:
    return CredencialUsuario(
        id_usuario=1,
        email="turista@ex.com",
        senha_hash=hash_senha("SenhaForte123"),
        totp_secret=gerar_segredo_totp(),
        papel=Papel.TURISTA,
        telefone="+5511999999999",
        two_factor=two_factor,
    )


def _patch_credencial(
    monkeypatch: pytest.MonkeyPatch, cred: CredencialUsuario | None
) -> None:
    from app.usuarios import repository

    monkeypatch.setattr(
        repository, "buscar_credencial_por_email", lambda _email, **_k: cred
    )


def test_login_retorna_token_desafio(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    cred = _credencial()
    _patch_credencial(monkeypatch, cred)
    resp = client.post(
        "/auth/login", json={"email": cred.email, "senha": "SenhaForte123"}
    )
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["desafio_2fa"] is True
    assert corpo["token_desafio"]  # token de desafio presente


def test_login_senha_errada_401(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_credencial(monkeypatch, _credencial())
    resp = client.post(
        "/auth/login", json={"email": "turista@ex.com", "senha": "errada"}
    )
    assert resp.status_code == 401


def test_2fa_sem_desafio_valido_nao_emite_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pular a etapa 1 (sem token_desafio valido) nao autentica (reamarracao)."""
    cred = _credencial()
    _patch_credencial(monkeypatch, cred)
    codigo = gerar_codigo_totp(cred.totp_secret)
    resp = client.post(
        "/auth/2fa/verificar",
        json={"token_desafio": "forjado", "codigo": codigo},
    )
    assert resp.status_code == 401


def test_fluxo_2fa_completo_emite_jwt(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    cred = _credencial()
    _patch_credencial(monkeypatch, cred)

    # Etapa 1: obtem o token de desafio apos a senha correta.
    login = client.post(
        "/auth/login", json={"email": cred.email, "senha": "SenhaForte123"}
    )
    token_desafio = login.json()["token_desafio"]

    # Etapa 2: apresenta o desafio + codigo TOTP correto.
    codigo = gerar_codigo_totp(cred.totp_secret)
    resp = client.post(
        "/auth/2fa/verificar",
        json={"token_desafio": token_desafio, "codigo": codigo},
    )
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["access_token"]
    assert corpo["papel"] == Papel.TURISTA.value


def test_2fa_codigo_errado_401(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    cred = _credencial()
    _patch_credencial(monkeypatch, cred)
    login = client.post(
        "/auth/login", json={"email": cred.email, "senha": "SenhaForte123"}
    )
    token_desafio = login.json()["token_desafio"]
    resp = client.post(
        "/auth/2fa/verificar",
        json={"token_desafio": token_desafio, "codigo": "000000"},
    )
    assert resp.status_code == 401


def test_2fa_verificar_nao_aceita_email(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O endpoint da etapa 2 nao aceita e-mail: identidade vem do desafio."""
    cred = _credencial()
    _patch_credencial(monkeypatch, cred)
    codigo = gerar_codigo_totp(cred.totp_secret)
    # Enviar apenas e-mail + codigo (schema antigo) deve ser rejeitado (422).
    resp = client.post(
        "/auth/2fa/verificar",
        json={"email": cred.email, "codigo": codigo},
    )
    assert resp.status_code == 422
