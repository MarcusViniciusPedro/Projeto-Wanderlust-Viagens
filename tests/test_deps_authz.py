"""Testes da camada de autorizacao HTTP (app.core.deps) com FastAPI TestClient.

Monta um mini-app com rotas protegidas pelas dependencies de deps.py e exercita
os caminhos de 401/403 e a extracao de identidade. Nenhum banco e necessario: a
camada lida somente com JWT (app.core.security) e a matriz pura
(app.core.authz). Os JWTs sao gerados com criar_token_acesso e o segredo e
definido por WANDERLUST_JWT_SECRET via monkeypatch, seguindo o padrao de
tests/test_router_auth.py.
"""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.authz import Papel, Permissao
from app.core.config import get_settings
from app.core.deps import (
    UsuarioAtual,
    requer_autenticacao,
    requer_papel,
    requer_permissao,
)
from app.core.security import criar_token_acesso


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Mini-app com rotas protegidas e JWT configurado por env."""
    monkeypatch.setenv("WANDERLUST_JWT_SECRET", "segredo-de-teste-deps")
    get_settings.cache_clear()

    app = FastAPI()

    @app.get("/autenticado")
    def _autenticado(usuario: UsuarioAtual = Depends(requer_autenticacao)) -> dict:
        return {"papel": usuario.papel.value, "id_passageiro": usuario.id_passageiro}

    @app.get("/somente-admin")
    def _somente_admin(
        usuario: UsuarioAtual = Depends(requer_papel(Papel.ADMINISTRADOR)),
    ) -> dict:
        return {"papel": usuario.papel.value}

    @app.get("/gerenciar-contas")
    def _gerenciar_contas(
        usuario: UsuarioAtual = Depends(
            requer_permissao(Permissao.GERENCIAR_CONTAS)
        ),
    ) -> dict:
        return {"papel": usuario.papel.value}

    try:
        yield TestClient(app)
    finally:
        get_settings.cache_clear()


def _token(papel: Papel, id_usuario: int | None = None) -> str:
    return criar_token_acesso(
        subject="usuario@ex.com", papel=papel.value, id_usuario=id_usuario
    )


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_token_ausente_401(client: TestClient) -> None:
    resp = client.get("/autenticado")
    assert resp.status_code == 401


def test_token_invalido_401(client: TestClient) -> None:
    resp = client.get("/autenticado", headers=_auth("token.forjado.invalido"))
    assert resp.status_code == 401


def test_token_valido_retorna_usuario_atual(client: TestClient) -> None:
    resp = client.get(
        "/autenticado", headers=_auth(_token(Papel.TURISTA, id_usuario=42))
    )
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["papel"] == Papel.TURISTA.value
    assert corpo["id_passageiro"] == 42


def test_id_passageiro_ausente_quando_sem_claim(client: TestClient) -> None:
    resp = client.get("/autenticado", headers=_auth(_token(Papel.TURISTA)))
    assert resp.status_code == 200
    assert resp.json()["id_passageiro"] is None


def test_requer_papel_admin_aceito(client: TestClient) -> None:
    resp = client.get(
        "/somente-admin", headers=_auth(_token(Papel.ADMINISTRADOR))
    )
    assert resp.status_code == 200
    assert resp.json()["papel"] == Papel.ADMINISTRADOR.value


def test_requer_papel_admin_nega_turista_403(client: TestClient) -> None:
    resp = client.get("/somente-admin", headers=_auth(_token(Papel.TURISTA)))
    assert resp.status_code == 403


def test_requer_permissao_permite_papel_com_permissao(client: TestClient) -> None:
    # Administrador possui GERENCIAR_CONTAS na matriz da secao 4.1.
    resp = client.get(
        "/gerenciar-contas", headers=_auth(_token(Papel.ADMINISTRADOR))
    )
    assert resp.status_code == 200


def test_requer_permissao_nega_papel_sem_permissao_403(client: TestClient) -> None:
    # Turista nao possui GERENCIAR_CONTAS -> 403.
    resp = client.get(
        "/gerenciar-contas", headers=_auth(_token(Papel.TURISTA))
    )
    assert resp.status_code == 403


def test_requer_permissao_sem_token_401(client: TestClient) -> None:
    resp = client.get("/gerenciar-contas")
    assert resp.status_code == 401
