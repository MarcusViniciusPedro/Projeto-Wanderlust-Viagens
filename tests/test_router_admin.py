"""Testes de router do CRUD do Administrador (secao 4.1) com TestClient.

Cobrem as tres capacidades do admin, todas protegidas pela camada de authz
(FEAT-001): Gerenciar Catalogo (Pacote/Destino), Agendar Viagem (Viagem) e
Gerenciar Contas (listar/alterar-status/excluir). Sem SQL Server vivo: os
repositories de catalogo e usuarios sao substituidos por fakes em memoria via
monkeypatch (padrao de tests/test_router_vendas.py) e os JWTs sao emitidos com
``criar_token_acesso`` + WANDERLUST_JWT_SECRET por env (padrao de
tests/test_router_auth.py).

Para pelo menos uma rota de cada capacidade, verificamos:
  (a) admin autenticado opera (2xx) e o fake registra a mudanca;
  (b) Turista recebe 403;
  (c) sem token recebe 401;
  (d) sem banco configurado recebe 503;
  (e) GET /openapi.json lista os novos paths.
Para Gerenciar Contas, verificamos que a resposta NAO contem cpf/senha.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

import pytest
from fastapi.testclient import TestClient

from app.core.authz import Papel
from app.core.config import get_settings
from app.core.security import criar_token_acesso
from app.catalogo.schemas import (
    DestinoSaida,
    PacoteSaida,
    ViagemSaida,
)
from app.db.session import DatabaseNotConfiguredError
from app.usuarios.schemas import ContaAdminSaida, StatusConta


# --------------------------------------------------------------------------
# Fakes em memoria dos repositories (sem DB).
# --------------------------------------------------------------------------


@dataclass
class FakeCatalogoRepo:
    pacotes: Dict[int, PacoteSaida] = field(default_factory=dict)
    destinos: Dict[int, DestinoSaida] = field(default_factory=dict)
    viagens: Dict[int, ViagemSaida] = field(default_factory=dict)
    proximo_pacote: int = 1
    proximo_destino: int = 1
    proximo_viagem: int = 1

    def criar_pacote(self, dados, settings=None):
        id_pacote = self.proximo_pacote
        self.proximo_pacote += 1
        pacote = PacoteSaida(id_pacote=id_pacote, **dados.model_dump())
        self.pacotes[id_pacote] = pacote
        return pacote

    def atualizar_pacote(self, id_pacote, dados, settings=None):
        if id_pacote not in self.pacotes:
            return None
        pacote = PacoteSaida(id_pacote=id_pacote, **dados.model_dump())
        self.pacotes[id_pacote] = pacote
        return pacote

    def excluir_pacote(self, id_pacote, settings=None):
        return self.pacotes.pop(id_pacote, None) is not None

    def criar_destino(self, dados, settings=None):
        id_destino = self.proximo_destino
        self.proximo_destino += 1
        destino = DestinoSaida(id_destino=id_destino, **dados.model_dump())
        self.destinos[id_destino] = destino
        return destino

    def buscar_destino_completo(self, id_destino, settings=None):
        return self.destinos.get(id_destino)

    def atualizar_destino(self, id_destino, dados, settings=None):
        if id_destino not in self.destinos:
            return None
        destino = DestinoSaida(id_destino=id_destino, **dados.model_dump())
        self.destinos[id_destino] = destino
        return destino

    def excluir_destino(self, id_destino, settings=None):
        return self.destinos.pop(id_destino, None) is not None

    def criar_viagem(self, dados, settings=None):
        id_viagem = self.proximo_viagem
        self.proximo_viagem += 1
        viagem = ViagemSaida(id_viagem=id_viagem, **dados.model_dump())
        self.viagens[id_viagem] = viagem
        return viagem

    def listar_viagens(self, settings=None):
        return list(self.viagens.values())

    def excluir_viagem(self, id_viagem, settings=None):
        return self.viagens.pop(id_viagem, None) is not None


@dataclass
class FakeUsuariosRepo:
    contas: Dict[int, ContaAdminSaida] = field(default_factory=dict)

    def listar_contas(self, settings=None):
        return list(self.contas.values())

    def buscar_conta(self, id_passageiro, settings=None):
        return self.contas.get(id_passageiro)

    def alterar_status_conta(self, id_passageiro, novo_status, settings=None):
        conta = self.contas.get(id_passageiro)
        if conta is None:
            return None
        atualizada = conta.model_copy(update={"status": novo_status})
        self.contas[id_passageiro] = atualizada
        return atualizada

    def excluir_conta(self, id_passageiro, settings=None):
        conta = self.contas.get(id_passageiro)
        if conta is None:
            return None
        anon = conta.model_copy(
            update={
                "status": StatusConta.BANIDO,
                "nome": "Conta removida",
                "email": None,
            }
        )
        self.contas[id_passageiro] = anon
        return anon


# --------------------------------------------------------------------------
# Fixtures.
# --------------------------------------------------------------------------


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("WANDERLUST_JWT_SECRET", "segredo-de-teste-admin")
    get_settings.cache_clear()
    import app.main as main

    try:
        yield TestClient(main.app)
    finally:
        get_settings.cache_clear()


@pytest.fixture()
def fake_catalogo(monkeypatch: pytest.MonkeyPatch) -> FakeCatalogoRepo:
    repo = FakeCatalogoRepo()
    from app.catalogo import repository

    for nome in (
        "criar_pacote",
        "atualizar_pacote",
        "excluir_pacote",
        "criar_destino",
        "buscar_destino_completo",
        "atualizar_destino",
        "excluir_destino",
        "criar_viagem",
        "listar_viagens",
        "excluir_viagem",
    ):
        monkeypatch.setattr(repository, nome, getattr(repo, nome))
    return repo


@pytest.fixture()
def fake_usuarios(monkeypatch: pytest.MonkeyPatch) -> FakeUsuariosRepo:
    repo = FakeUsuariosRepo()
    repo.contas[1] = ContaAdminSaida(
        id_passageiro=1,
        nome="Ana Souza",
        email="ana@ex.com",
        papel=Papel.TURISTA,
        status=StatusConta.ATIVO,
    )
    from app.usuarios import repository

    for nome in (
        "listar_contas",
        "buscar_conta",
        "alterar_status_conta",
        "excluir_conta",
    ):
        monkeypatch.setattr(repository, nome, getattr(repo, nome))
    return repo


def _auth(papel: Papel) -> dict[str, str]:
    token = criar_token_acesso(subject="u@ex.com", papel=papel.value, id_usuario=1)
    return {"Authorization": f"Bearer {token}"}


def _admin() -> dict[str, str]:
    return _auth(Papel.ADMINISTRADOR)


_PACOTE_PAYLOAD = {
    "preco_base": 2500.0,
    "data_inicio": "2025-12-20",
    "data_fim": "2025-12-27",
    "estoque": 10,
    "tipo_viagem": "Praia",
    "nivel": "Conforto",
}
_DESTINO_PAYLOAD = {
    "cidade": "Rio de Janeiro",
    "estado": "RJ",
    "pais": "Brasil",
    "categoria": "Praia",
    "descricao": "Praias famosas.",
}
_VIAGEM_PAYLOAD = {
    "data_partida": "2025-12-20T08:00:00",
    "data_chegada": "2025-12-20T10:00:00",
    "meio_transporte": "Aviao",
    "duracao": "2h",
    "fk_Destino_id_destino": 1,
}


# --------------------------------------------------------------------------
# Gerenciar Catalogo (Pacote/Destino) - permissao gerenciar_catalogo.
# --------------------------------------------------------------------------


def test_admin_cria_pacote(client: TestClient, fake_catalogo: FakeCatalogoRepo):
    resp = client.post("/catalogo/pacotes", json=_PACOTE_PAYLOAD, headers=_admin())
    assert resp.status_code == 201
    corpo = resp.json()
    assert corpo["id_pacote"] == 1
    assert fake_catalogo.pacotes[1].preco_base == 2500.0


def test_admin_atualiza_e_exclui_pacote(
    client: TestClient, fake_catalogo: FakeCatalogoRepo
):
    client.post("/catalogo/pacotes", json=_PACOTE_PAYLOAD, headers=_admin())
    atualizado = {**_PACOTE_PAYLOAD, "estoque": 3}
    resp = client.put("/catalogo/pacotes/1", json=atualizado, headers=_admin())
    assert resp.status_code == 200
    assert resp.json()["estoque"] == 3
    resp_del = client.delete("/catalogo/pacotes/1", headers=_admin())
    assert resp_del.status_code == 204
    assert 1 not in fake_catalogo.pacotes


def test_pacote_inexistente_404(client: TestClient, fake_catalogo: FakeCatalogoRepo):
    resp = client.put("/catalogo/pacotes/999", json=_PACOTE_PAYLOAD, headers=_admin())
    assert resp.status_code == 404


def test_admin_cria_destino(client: TestClient, fake_catalogo: FakeCatalogoRepo):
    resp = client.post("/catalogo/destinos", json=_DESTINO_PAYLOAD, headers=_admin())
    assert resp.status_code == 201
    assert fake_catalogo.destinos[1].cidade == "Rio de Janeiro"


def test_catalogo_turista_403(client: TestClient, fake_catalogo: FakeCatalogoRepo):
    resp = client.post(
        "/catalogo/pacotes", json=_PACOTE_PAYLOAD, headers=_auth(Papel.TURISTA)
    )
    assert resp.status_code == 403


def test_catalogo_sem_token_401(client: TestClient, fake_catalogo: FakeCatalogoRepo):
    resp = client.post("/catalogo/pacotes", json=_PACOTE_PAYLOAD)
    assert resp.status_code == 401


def test_catalogo_sem_banco_503(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from app.catalogo import repository

    def _sem_banco(*_a, **_k):
        raise DatabaseNotConfiguredError("sem banco")

    monkeypatch.setattr(repository, "criar_pacote", _sem_banco)
    resp = client.post("/catalogo/pacotes", json=_PACOTE_PAYLOAD, headers=_admin())
    assert resp.status_code == 503


# --------------------------------------------------------------------------
# Agendar Viagem (Viagem) - permissao agendar.
# --------------------------------------------------------------------------


def test_admin_agenda_lista_exclui_viagem(
    client: TestClient, fake_catalogo: FakeCatalogoRepo
):
    resp = client.post("/catalogo/viagens", json=_VIAGEM_PAYLOAD, headers=_admin())
    assert resp.status_code == 201
    assert resp.json()["id_viagem"] == 1
    assert fake_catalogo.viagens[1].meio_transporte == "Aviao"

    lista = client.get("/catalogo/viagens", headers=_admin())
    assert lista.status_code == 200
    assert len(lista.json()) == 1

    resp_del = client.delete("/catalogo/viagens/1", headers=_admin())
    assert resp_del.status_code == 204
    assert 1 not in fake_catalogo.viagens


def test_viagem_data_invalida_422(client: TestClient, fake_catalogo: FakeCatalogoRepo):
    payload = {**_VIAGEM_PAYLOAD, "data_chegada": "2025-12-20T06:00:00"}
    resp = client.post("/catalogo/viagens", json=payload, headers=_admin())
    assert resp.status_code == 422


def test_viagem_turista_403(client: TestClient, fake_catalogo: FakeCatalogoRepo):
    resp = client.post(
        "/catalogo/viagens", json=_VIAGEM_PAYLOAD, headers=_auth(Papel.TURISTA)
    )
    assert resp.status_code == 403


def test_viagem_sem_token_401(client: TestClient, fake_catalogo: FakeCatalogoRepo):
    resp = client.post("/catalogo/viagens", json=_VIAGEM_PAYLOAD)
    assert resp.status_code == 401


# --------------------------------------------------------------------------
# Gerenciar Contas - permissao gerenciar_contas.
# --------------------------------------------------------------------------


def test_admin_lista_contas_sem_dados_sensiveis(
    client: TestClient, fake_usuarios: FakeUsuariosRepo
):
    resp = client.get("/auth/admin/contas", headers=_admin())
    assert resp.status_code == 200
    contas = resp.json()
    assert len(contas) == 1
    conta = contas[0]
    # RNF3/LGPD: a resposta NAO expoe dados pessoais sensiveis.
    assert "cpf" not in conta
    assert "senha" not in conta
    assert "senha_hash" not in conta
    assert "data_nascimento" not in conta
    assert conta["status"] == StatusConta.ATIVO.value


def test_admin_altera_status_conta(
    client: TestClient, fake_usuarios: FakeUsuariosRepo
):
    resp = client.patch(
        "/auth/admin/contas/1/status",
        json={"novo_status": "Banido", "motivo": "abuso"},
        headers=_admin(),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "Banido"
    assert fake_usuarios.contas[1].status == StatusConta.BANIDO


def test_admin_exclui_conta_soft_delete(
    client: TestClient, fake_usuarios: FakeUsuariosRepo
):
    resp = client.delete("/auth/admin/contas/1", headers=_admin())
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["status"] == "Banido"
    assert "cpf" not in corpo
    # Soft delete: a conta ainda existe no "banco", anonimizada.
    assert fake_usuarios.contas[1].status == StatusConta.BANIDO


def test_conta_inexistente_404(client: TestClient, fake_usuarios: FakeUsuariosRepo):
    resp = client.patch(
        "/auth/admin/contas/999/status",
        json={"novo_status": "Banido"},
        headers=_admin(),
    )
    assert resp.status_code == 404


def test_contas_turista_403(client: TestClient, fake_usuarios: FakeUsuariosRepo):
    resp = client.get("/auth/admin/contas", headers=_auth(Papel.TURISTA))
    assert resp.status_code == 403


def test_contas_sem_token_401(client: TestClient, fake_usuarios: FakeUsuariosRepo):
    resp = client.get("/auth/admin/contas")
    assert resp.status_code == 401


def test_contas_sem_banco_503(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from app.usuarios import repository

    def _sem_banco(*_a, **_k):
        raise DatabaseNotConfiguredError("sem banco")

    monkeypatch.setattr(repository, "listar_contas", _sem_banco)
    resp = client.get("/auth/admin/contas", headers=_admin())
    assert resp.status_code == 503


# --------------------------------------------------------------------------
# OpenAPI: as novas rotas aparecem em /openapi.json (/docs).
# --------------------------------------------------------------------------


def test_novas_rotas_no_openapi(client: TestClient):
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    assert "post" in paths["/catalogo/pacotes"]
    assert "put" in paths["/catalogo/pacotes/{id_pacote}"]
    assert "delete" in paths["/catalogo/pacotes/{id_pacote}"]
    assert "post" in paths["/catalogo/destinos"]
    assert "post" in paths["/catalogo/viagens"]
    assert "get" in paths["/catalogo/viagens"]
    assert "get" in paths["/auth/admin/contas"]
    assert "patch" in paths["/auth/admin/contas/{id_passageiro}/status"]
    assert "delete" in paths["/auth/admin/contas/{id_passageiro}"]
