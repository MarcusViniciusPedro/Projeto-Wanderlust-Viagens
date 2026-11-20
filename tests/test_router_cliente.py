"""Testes de router do self-service do Cliente/Turista (FEAT-003) com TestClient.

Cobrem o CRUD que o PROPRIO turista faz sobre a PROPRIA conta (GET/PUT/DELETE
/auth/me) e sobre as PROPRIAS compras (GET /vendas/minhas, GET /vendas/{id},
POST /vendas/minhas e POST /vendas/minhas/{id}/cancelar), todos protegidos pela
camada de authz (FEAT-001) com checagem de posse pelo id_passageiro do JWT.

Sem SQL Server vivo: os repositories de usuarios e vendas sao substituidos por
fakes em memoria via monkeypatch (padrao de tests/test_router_vendas.py) e os
JWTs sao emitidos com ``criar_token_acesso`` + WANDERLUST_JWT_SECRET por env
(padrao de tests/test_router_auth.py).

Verificamos:
  (a) GET /auth/me retorna o perfil do dono do token;
  (b) PUT /auth/me atualiza apenas campos permitidos e NAO altera papel;
  (c) DELETE /auth/me aplica a politica de soft delete/anonimizacao;
  (d) GET /vendas/minhas retorna apenas as vendas do turista do token;
  (e) GET /vendas/{id} de outro turista -> 403; inexistente -> 404;
  (f) cancelar venda de outro turista -> 403;
  (g) sem token -> 401;
  (h) sem banco -> 503;
  (i) as novas rotas aparecem em GET /openapi.json.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, Optional

import pytest
from fastapi.testclient import TestClient

from app.core.authz import Papel
from app.core.config import get_settings
from app.core.security import criar_token_acesso
from app.db.session import DatabaseNotConfiguredError
from app.usuarios.schemas import UsuarioSaida
from app.vendas.schemas import FormaPagamento, StatusPagamento
from app.vendas.service import Venda


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


@dataclass
class FakeVendasRepo:
    # venda -> dono (fk_conta_turista)
    vendas: Dict[int, Venda] = field(default_factory=dict)
    donos: Dict[int, int] = field(default_factory=dict)
    proximo_id: int = 100
    preco_persistido: float = 2500.00

    def buscar_venda_com_dono(self, id_venda, settings=None):
        venda = self.vendas.get(id_venda)
        if venda is None:
            return None
        return venda, self.donos[id_venda]

    def listar_vendas_por_turista(self, fk_conta_turista, settings=None):
        return [
            venda
            for id_venda, venda in self.vendas.items()
            if self.donos[id_venda] == fk_conta_turista
        ]

    def registrar_venda(
        self,
        fk_conta_turista,
        fk_pacote,
        forma_pagamento,
        fk_conta_colaborador=None,
        settings=None,
    ):
        id_venda = self.proximo_id
        self.proximo_id += 1
        self.vendas[id_venda] = Venda(
            id_venda=id_venda,
            valor_total=self.preco_persistido,
            forma_pagamento=FormaPagamento(forma_pagamento),
            status_pagamento=StatusPagamento.PENDENTE,
        )
        self.donos[id_venda] = fk_conta_turista
        return id_venda, self.preco_persistido

    def atualizar_status(
        self, id_venda, novo_status, status_esperado=None, settings=None
    ):
        venda = self.vendas.get(id_venda)
        if venda is None:
            return False
        if status_esperado is not None and venda.status_pagamento != status_esperado:
            return False
        self.vendas[id_venda] = replace(venda, status_pagamento=novo_status)
        return True


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


@pytest.fixture()
def fake_vendas(monkeypatch: pytest.MonkeyPatch) -> FakeVendasRepo:
    repo = FakeVendasRepo()
    # Venda 100 pertence ao turista 1; venda 200 pertence ao turista 2.
    repo.vendas[100] = Venda(
        id_venda=100,
        valor_total=1500.0,
        forma_pagamento=FormaPagamento.PIX,
        status_pagamento=StatusPagamento.PENDENTE,
    )
    repo.donos[100] = 1
    repo.vendas[200] = Venda(
        id_venda=200,
        valor_total=800.0,
        forma_pagamento=FormaPagamento.CREDITO,
        status_pagamento=StatusPagamento.PENDENTE,
    )
    repo.donos[200] = 2
    from app.vendas import repository

    for nome in (
        "buscar_venda_com_dono",
        "listar_vendas_por_turista",
        "registrar_venda",
        "atualizar_status",
    ):
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
# Compras proprias: GET /vendas/minhas, GET /vendas/{id}, POST /vendas/minhas,
# POST /vendas/minhas/{id}/cancelar.
# --------------------------------------------------------------------------


def test_listar_minhas_compras_so_do_dono(
    client: TestClient, fake_vendas: FakeVendasRepo
):
    resp = client.get("/vendas/minhas", headers=_turista(1))
    assert resp.status_code == 200
    vendas = resp.json()
    assert len(vendas) == 1
    assert vendas[0]["id_venda"] == 100


def test_obter_minha_compra(client: TestClient, fake_vendas: FakeVendasRepo):
    resp = client.get("/vendas/100", headers=_turista(1))
    assert resp.status_code == 200
    assert resp.json()["id_venda"] == 100


def test_obter_compra_de_outro_turista_403(
    client: TestClient, fake_vendas: FakeVendasRepo
):
    resp = client.get("/vendas/200", headers=_turista(1))
    assert resp.status_code == 403


def test_obter_compra_inexistente_404(
    client: TestClient, fake_vendas: FakeVendasRepo
):
    resp = client.get("/vendas/999", headers=_turista(1))
    assert resp.status_code == 404


def test_criar_minha_compra_vincula_dono_do_token(
    client: TestClient, fake_vendas: FakeVendasRepo
):
    resp = client.post(
        "/vendas/minhas",
        json={"fk_pacote": 1, "valor_total": 1.0, "forma_pagamento": "pix"},
        headers=_turista(1),
    )
    assert resp.status_code == 201
    corpo = resp.json()
    # Valor persistido (preco do pacote), nao o enviado pelo cliente.
    assert corpo["valor_total"] == fake_vendas.preco_persistido
    assert corpo["status_pagamento"] == StatusPagamento.PENDENTE.value
    id_venda = corpo["id_venda"]
    # A compra criada pertence ao turista do token (1), nao a outro.
    assert fake_vendas.donos[id_venda] == 1


def test_cancelar_minha_compra(client: TestClient, fake_vendas: FakeVendasRepo):
    resp = client.post("/vendas/minhas/100/cancelar", headers=_turista(1))
    assert resp.status_code == 200
    assert resp.json()["status_pagamento"] == StatusPagamento.CANCELADO.value
    assert fake_vendas.vendas[100].status_pagamento == StatusPagamento.CANCELADO


def test_cancelar_compra_de_outro_turista_403(
    client: TestClient, fake_vendas: FakeVendasRepo
):
    resp = client.post("/vendas/minhas/200/cancelar", headers=_turista(1))
    assert resp.status_code == 403
    assert fake_vendas.vendas[200].status_pagamento == StatusPagamento.PENDENTE


def test_vendas_cliente_sem_token_401(
    client: TestClient, fake_vendas: FakeVendasRepo
):
    assert client.get("/vendas/minhas").status_code == 401
    assert client.get("/vendas/100").status_code == 401


def test_vendas_cliente_sem_banco_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    from app.vendas import repository

    def _sem_banco(*_a, **_k):
        raise DatabaseNotConfiguredError("sem banco")

    monkeypatch.setattr(repository, "listar_vendas_por_turista", _sem_banco)
    resp = client.get("/vendas/minhas", headers=_turista(1))
    assert resp.status_code == 503


# --------------------------------------------------------------------------
# OpenAPI: as novas rotas aparecem em /openapi.json (/docs).
# --------------------------------------------------------------------------


def test_novas_rotas_cliente_no_openapi(client: TestClient):
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    assert "get" in paths["/auth/me"]
    assert "put" in paths["/auth/me"]
    assert "delete" in paths["/auth/me"]
    assert "get" in paths["/vendas/minhas"]
    assert "post" in paths["/vendas/minhas"]
    assert "get" in paths["/vendas/{id_venda}"]
    assert "post" in paths["/vendas/minhas/{id_venda}/cancelar"]
