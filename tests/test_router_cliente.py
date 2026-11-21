"""Testes de router do self-service do Cliente/Turista (FEAT-003) com TestClient.

Cobrem o CRUD que o PROPRIO turista faz sobre a PROPRIA conta (GET/PUT/DELETE
/auth/me), protegido pela camada de authz (FEAT-001) com checagem de posse pelo
id_passageiro do JWT.

Sem SQL Server vivo: o repository de usuarios e substituido por um fake em
memoria via monkeypatch (padrao de tests/test_router_vendas.py) e os JWTs sao
emitidos com ``criar_token_acesso`` + WANDERLUST_JWT_SECRET por env (padrao de
tests/test_router_auth.py).

Verificamos:
  (a) GET /auth/me retorna o perfil do dono do token;
  (b) PUT /auth/me atualiza apenas campos permitidos e NAO altera papel;
  (c) DELETE /auth/me aplica a politica de soft delete/anonimizacao;
  (d) sem token -> 401; token sem id -> 401;
  (e) sem banco -> 503;
  (f) as rotas aparecem em GET /openapi.json.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

import pytest
from fastapi.testclient import TestClient

from app.core.authz import Papel
from app.core.config import get_settings
from app.core.security import criar_token_acesso
from app.db.session import DatabaseNotConfiguredError
from app.usuarios.schemas import UsuarioSaida


# --------------------------------------------------------------------------
# Fakes em memoria dos repositories (sem DB).
# --------------------------------------------------------------------------


@dataclass
class FakeUsuariosRepo:
    perfis: Dict[int, UsuarioSaida] = field(default_factory=dict)

    def buscar_usuario_por_id(self, id_passageiro, settings=None):
        return self.perfis.get(id_passageiro)

    def atualizar_usuario(self, id_passageiro, dados, settings=None):
        perfil = self.perfis.get(id_passageiro)
        if perfil is None:
            return None
        # So aplica os campos enviados (nao-None); papel nunca muda aqui.
        atualizacoes = dados.model_dump(exclude_unset=True, exclude_none=True)
        atualizado = perfil.model_copy(update=atualizacoes)
        self.perfis[id_passageiro] = atualizado
        return atualizado

    def excluir_usuario(self, id_passageiro, settings=None):
        perfil = self.perfis.get(id_passageiro)
        if perfil is None:
            return None
        anon = perfil.model_copy(
            update={
                "nome": "Conta removida",
                "nome_social": None,
                "pronome": None,
                "email": None,
                "telefone": None,
            }
        )
        self.perfis[id_passageiro] = anon
        return anon


# --------------------------------------------------------------------------
# Fixtures.
# --------------------------------------------------------------------------


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("WANDERLUST_JWT_SECRET", "segredo-de-teste-cliente")
    get_settings.cache_clear()
    import app.main as main

    try:
        yield TestClient(main.app)
    finally:
        get_settings.cache_clear()


@pytest.fixture()
def fake_usuarios(monkeypatch: pytest.MonkeyPatch) -> FakeUsuariosRepo:
    repo = FakeUsuariosRepo()
    repo.perfis[1] = UsuarioSaida(
        id_passageiro=1,
        nome="Ana Souza",
        nome_social=None,
        pronome=None,
        email="ana@ex.com",
        telefone="+5511999999999",
        papel=Papel.TURISTA,
    )
    from app.usuarios import repository

    for nome in ("buscar_usuario_por_id", "atualizar_usuario", "excluir_usuario"):
        monkeypatch.setattr(repository, nome, getattr(repo, nome))
    return repo


def _auth(papel: Papel, id_usuario: Optional[int] = 1) -> dict[str, str]:
    token = criar_token_acesso(
        subject="u@ex.com", papel=papel.value, id_usuario=id_usuario
    )
    return {"Authorization": f"Bearer {token}"}


def _turista(id_usuario: int = 1) -> dict[str, str]:
    return _auth(Papel.TURISTA, id_usuario=id_usuario)


# --------------------------------------------------------------------------
# Conta propria: GET/PUT/DELETE /auth/me.
# --------------------------------------------------------------------------


def test_get_me_retorna_perfil_do_dono(
    client: TestClient, fake_usuarios: FakeUsuariosRepo
):
    resp = client.get("/auth/me", headers=_turista(1))
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["id_passageiro"] == 1
    assert corpo["nome"] == "Ana Souza"
    assert corpo["papel"] == Papel.TURISTA.value


def test_put_me_atualiza_apenas_campos_permitidos(
    client: TestClient, fake_usuarios: FakeUsuariosRepo
):
    resp = client.put(
        "/auth/me",
        json={"nome_social": "Aninha", "telefone": "+5511888888888"},
        headers=_turista(1),
    )
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["nome_social"] == "Aninha"
    assert corpo["telefone"] == "+5511888888888"
    assert fake_usuarios.perfis[1].nome_social == "Aninha"


def test_put_me_nao_altera_papel(
    client: TestClient, fake_usuarios: FakeUsuariosRepo
):
    # O cliente tenta escalar privilegio enviando papel/status; sao ignorados.
    resp = client.put(
        "/auth/me",
        json={"nome": "Ana", "papel": "Administrador", "status": "Ativo"},
        headers=_turista(1),
    )
    assert resp.status_code == 200
    assert resp.json()["papel"] == Papel.TURISTA.value
    assert fake_usuarios.perfis[1].papel == Papel.TURISTA


def test_delete_me_soft_delete_anonimiza(
    client: TestClient, fake_usuarios: FakeUsuariosRepo
):
    resp = client.delete("/auth/me", headers=_turista(1))
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["nome"] == "Conta removida"
    assert corpo["email"] is None
    # Soft delete: a conta ainda existe no "banco", anonimizada.
    assert fake_usuarios.perfis[1].nome == "Conta removida"


def test_me_sem_token_401(client: TestClient, fake_usuarios: FakeUsuariosRepo):
    assert client.get("/auth/me").status_code == 401


def test_me_token_sem_id_401(client: TestClient, fake_usuarios: FakeUsuariosRepo):
    # Token antigo sem a claim 'id': nao da para resolver "a propria conta".
    headers = _auth(Papel.TURISTA, id_usuario=None)
    resp = client.get("/auth/me", headers=headers)
    assert resp.status_code == 401


def test_me_sem_banco_503(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from app.usuarios import repository

    def _sem_banco(*_a, **_k):
        raise DatabaseNotConfiguredError("sem banco")

    monkeypatch.setattr(repository, "buscar_usuario_por_id", _sem_banco)
    resp = client.get("/auth/me", headers=_turista(1))
    assert resp.status_code == 503


# --------------------------------------------------------------------------
# OpenAPI: as rotas de conta propria aparecem em /openapi.json (/docs).
# --------------------------------------------------------------------------


def test_novas_rotas_cliente_no_openapi(client: TestClient):
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    assert "get" in paths["/auth/me"]
    assert "put" in paths["/auth/me"]
    assert "delete" in paths["/auth/me"]
