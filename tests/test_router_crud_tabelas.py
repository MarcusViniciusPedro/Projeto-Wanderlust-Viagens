"""Testes do CRUD generico de tabelas (FEAT-005) com TestClient.

Cobrem duas frentes, ambas sem SQL Server vivo (repositories substituidos por
fakes em memoria via monkeypatch + JWTs emitidos por WANDERLUST_JWT_SECRET):

  1. CRUD HTTP de dbo.Hospedagem em app/catalogo, gated por gerenciar_catalogo:
     admin cria/le/lista/atualiza/exclui; Turista -> 403; sem token -> 401;
     sem banco -> 503; 404 para id inexistente; rotas no OpenAPI. Tambem as
     leituras adicionadas do catalogo (GET /catalogo/pacotes/{id} publico e
     GET /catalogo/destinos publico).

  2. Guarda anti-lockout de moderacao de contas: admin nao pode banir/excluir a
     propria conta (403); nao e possivel banir/excluir o ultimo admin ativo
     (409); banir um admin quando ha outro admin ativo e permitido. Inclui o
     teste unitario direto da funcao pura ``avaliar_guarda_moderacao``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

import pytest
from fastapi.testclient import TestClient

from app.core.authz import Papel
from app.core.config import get_settings
from app.core.security import criar_token_acesso
from app.catalogo.schemas import HospedagemSaida
from app.db.session import DatabaseNotConfiguredError
from app.usuarios.schemas import ContaAdminSaida, StatusConta
from app.usuarios.service import (
    AcaoModeracao,
    avaliar_guarda_moderacao,
)


# --------------------------------------------------------------------------
# Fakes em memoria dos repositories (sem DB).
# --------------------------------------------------------------------------


@dataclass
class FakeCatalogoRepo:
    hospedagens: Dict[int, HospedagemSaida] = field(default_factory=dict)
    proximo_hospedagem: int = 1

    def criar_hospedagem(self, dados, settings=None):
        id_hospedagem = self.proximo_hospedagem
        self.proximo_hospedagem += 1
        hosp = HospedagemSaida(id_hospedagem=id_hospedagem, **dados.model_dump())
        self.hospedagens[id_hospedagem] = hosp
        return hosp

    def listar_hospedagens(self, fk_pacote=None, settings=None):
        valores = list(self.hospedagens.values())
        if fk_pacote is not None:
            valores = [h for h in valores if h.fk_Pacote_id_pacote == fk_pacote]
        return valores

    def buscar_hospedagem(self, id_hospedagem, settings=None):
        return self.hospedagens.get(id_hospedagem)

    def atualizar_hospedagem(self, id_hospedagem, dados, settings=None):
        if id_hospedagem not in self.hospedagens:
            return None
        hosp = HospedagemSaida(id_hospedagem=id_hospedagem, **dados.model_dump())
        self.hospedagens[id_hospedagem] = hosp
        return hosp

    def excluir_hospedagem(self, id_hospedagem, settings=None):
        return self.hospedagens.pop(id_hospedagem, None) is not None


@dataclass
class FakeUsuariosRepo:
    contas: Dict[int, ContaAdminSaida] = field(default_factory=dict)

    def buscar_conta(self, id_passageiro, settings=None):
        return self.contas.get(id_passageiro)

    def contar_admins_ativos(self, settings=None):
        return sum(
            1
            for c in self.contas.values()
            if c.papel == Papel.ADMINISTRADOR and c.status == StatusConta.ATIVO
        )

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
    monkeypatch.setenv("WANDERLUST_JWT_SECRET", "segredo-de-teste-crud")
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
        "criar_hospedagem",
        "listar_hospedagens",
        "buscar_hospedagem",
        "atualizar_hospedagem",
        "excluir_hospedagem",
    ):
        monkeypatch.setattr(repository, nome, getattr(repo, nome))
    return repo


@pytest.fixture()
def fake_usuarios(monkeypatch: pytest.MonkeyPatch) -> FakeUsuariosRepo:
    repo = FakeUsuariosRepo()
    from app.usuarios import repository

    for nome in (
        "buscar_conta",
        "contar_admins_ativos",
        "alterar_status_conta",
        "excluir_conta",
    ):
        monkeypatch.setattr(repository, nome, getattr(repo, nome))
    return repo


def _auth(papel: Papel, id_usuario: int = 1) -> dict[str, str]:
    token = criar_token_acesso(
        subject="u@ex.com", papel=papel.value, id_usuario=id_usuario
    )
    return {"Authorization": f"Bearer {token}"}


def _admin(id_usuario: int = 1) -> dict[str, str]:
    return _auth(Papel.ADMINISTRADOR, id_usuario=id_usuario)


_HOSPEDAGEM_PAYLOAD = {
    "cep": "22070-011",
    "rua": "Avenida Atlantica",
    "numero": 1702,
    "nome": "Hotel Copacabana",
    "tipo_quarto": "Suite",
    "regime_alimentacao": "Meia pensao",
    "fk_Pacote_id_pacote": 1,
}


# --------------------------------------------------------------------------
# Hospedagem - CRUD completo gated por gerenciar_catalogo.
# --------------------------------------------------------------------------


def test_admin_cria_le_lista_atualiza_exclui_hospedagem(
    client: TestClient, fake_catalogo: FakeCatalogoRepo
):
    # Create.
    resp = client.post(
        "/catalogo/hospedagens", json=_HOSPEDAGEM_PAYLOAD, headers=_admin()
    )
    assert resp.status_code == 201
    corpo = resp.json()
    assert corpo["id_hospedagem"] == 1
    assert corpo["nome"] == "Hotel Copacabana"
    assert fake_catalogo.hospedagens[1].numero == 1702

    # Read por id.
    resp_get = client.get("/catalogo/hospedagens/1", headers=_admin())
    assert resp_get.status_code == 200
    assert resp_get.json()["cep"] == "22070-011"

    # List (e filtro por pacote).
    resp_list = client.get("/catalogo/hospedagens", headers=_admin())
    assert resp_list.status_code == 200
    assert len(resp_list.json()) == 1
    resp_filtro = client.get(
        "/catalogo/hospedagens", params={"fk_pacote": 99}, headers=_admin()
    )
    assert resp_filtro.json() == []

    # Update.
    atualizado = {**_HOSPEDAGEM_PAYLOAD, "nome": "Hotel Ipanema"}
    resp_put = client.put(
        "/catalogo/hospedagens/1", json=atualizado, headers=_admin()
    )
    assert resp_put.status_code == 200
    assert resp_put.json()["nome"] == "Hotel Ipanema"
    assert fake_catalogo.hospedagens[1].nome == "Hotel Ipanema"

    # Delete.
    resp_del = client.delete("/catalogo/hospedagens/1", headers=_admin())
    assert resp_del.status_code == 204
    assert 1 not in fake_catalogo.hospedagens


def test_hospedagem_inexistente_404(
    client: TestClient, fake_catalogo: FakeCatalogoRepo
):
    assert client.get("/catalogo/hospedagens/999", headers=_admin()).status_code == 404
    assert (
        client.put(
            "/catalogo/hospedagens/999",
            json=_HOSPEDAGEM_PAYLOAD,
            headers=_admin(),
        ).status_code
        == 404
    )
    assert (
        client.delete("/catalogo/hospedagens/999", headers=_admin()).status_code
        == 404
    )


def test_hospedagem_numero_invalido_422(
    client: TestClient, fake_catalogo: FakeCatalogoRepo
):
    payload = {**_HOSPEDAGEM_PAYLOAD, "numero": 0}
    resp = client.post("/catalogo/hospedagens", json=payload, headers=_admin())
    assert resp.status_code == 422


def test_hospedagem_turista_403(
    client: TestClient, fake_catalogo: FakeCatalogoRepo
):
    resp = client.post(
        "/catalogo/hospedagens",
        json=_HOSPEDAGEM_PAYLOAD,
        headers=_auth(Papel.TURISTA),
    )
    assert resp.status_code == 403


def test_hospedagem_sem_token_401(
    client: TestClient, fake_catalogo: FakeCatalogoRepo
):
    resp = client.post("/catalogo/hospedagens", json=_HOSPEDAGEM_PAYLOAD)
    assert resp.status_code == 401


def test_hospedagem_sem_banco_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    from app.catalogo import repository

    def _sem_banco(*_a, **_k):
        raise DatabaseNotConfiguredError("sem banco")

    monkeypatch.setattr(repository, "criar_hospedagem", _sem_banco)
    resp = client.post(
        "/catalogo/hospedagens", json=_HOSPEDAGEM_PAYLOAD, headers=_admin()
    )
    assert resp.status_code == 503


# --------------------------------------------------------------------------
# Leituras adicionadas do catalogo (publicas, fecham o R do CRUD).
# --------------------------------------------------------------------------


def test_get_pacote_por_id_publico(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    from app.catalogo import repository
    from app.catalogo.schemas import PacoteSaida

    def _buscar(id_pacote, settings=None):
        if id_pacote != 7:
            return None
        return PacoteSaida(
            id_pacote=7,
            preco_base=1999.9,
            data_inicio="2025-12-20",
            data_fim="2025-12-27",
            estoque=5,
            tipo_viagem="Praia",
            nivel="Conforto",
            fk_destino=1,
            cidade="Rio de Janeiro",
            estado="RJ",
            descricao="Praias famosas.",
        )

    monkeypatch.setattr(repository, "buscar_pacote", _buscar)
    # Publico: sem token deve funcionar (2xx), coerente com GET /catalogo/pacotes.
    resp = client.get("/catalogo/pacotes/7")
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["id_pacote"] == 7
    assert corpo["fk_destino"] == 1
    assert corpo["cidade"] == "Rio de Janeiro"
    assert client.get("/catalogo/pacotes/999").status_code == 404


_PACOTE_PAYLOAD = {
    "preco_base": 2500.0,
    "data_inicio": "2025-12-20",
    "data_fim": "2025-12-27",
    "estoque": 10,
    "tipo_viagem": "Praia",
    "nivel": "Conforto",
    "fk_destino": 1,
}


def test_criar_pacote_aceita_fk_destino(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    from app.catalogo import repository
    from app.catalogo.schemas import PacoteSaida

    def _criar(dados, settings=None):
        return PacoteSaida(
            id_pacote=42,
            preco_base=dados.preco_base,
            data_inicio=dados.data_inicio,
            data_fim=dados.data_fim,
            estoque=dados.estoque,
            tipo_viagem=dados.tipo_viagem,
            nivel=dados.nivel,
            fk_destino=dados.fk_destino,
        )

    monkeypatch.setattr(repository, "criar_pacote", _criar)
    resp = client.post(
        "/catalogo/pacotes", json=_PACOTE_PAYLOAD, headers=_admin()
    )
    assert resp.status_code == 201
    corpo = resp.json()
    assert corpo["id_pacote"] == 42
    assert corpo["fk_destino"] == 1


def test_criar_pacote_destino_inexistente_400(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    from app.catalogo import repository

    def _criar(dados, settings=None):
        # Simula o THROW 50020/'Destino inexistente.' propagado pelo pymssql.
        raise Exception(
            "(50020, b'Destino inexistente.DB-Lib error message 50020')"
        )

    monkeypatch.setattr(repository, "criar_pacote", _criar)
    resp = client.post(
        "/catalogo/pacotes", json=_PACOTE_PAYLOAD, headers=_admin()
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Destino inexistente."


def test_get_pacote_por_id_sem_banco_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    from app.catalogo import repository

    def _sem_banco(*_a, **_k):
        raise DatabaseNotConfiguredError("sem banco")

    monkeypatch.setattr(repository, "buscar_pacote", _sem_banco)
    assert client.get("/catalogo/pacotes/1").status_code == 503


def test_listar_destinos_publico(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    from app.catalogo import repository
    from app.catalogo.schemas import DestinoSaida

    def _listar(settings=None):
        return [
            DestinoSaida(
                id_destino=1,
                cidade="Rio de Janeiro",
                estado="RJ",
                pais="Brasil",
                categoria="Praia",
                descricao=None,
            )
        ]

    monkeypatch.setattr(repository, "listar_destinos", _listar)
    resp = client.get("/catalogo/destinos")
    assert resp.status_code == 200
    assert resp.json()[0]["cidade"] == "Rio de Janeiro"


# --------------------------------------------------------------------------
# Guarda anti-lockout (via router).
# --------------------------------------------------------------------------


def _conta(id_: int, papel: Papel, status_: StatusConta) -> ContaAdminSaida:
    return ContaAdminSaida(
        id_passageiro=id_,
        nome=f"Conta {id_}",
        email=f"c{id_}@ex.com",
        papel=papel,
        status=status_,
    )


def test_admin_nao_bane_propria_conta(
    client: TestClient, fake_usuarios: FakeUsuariosRepo
):
    fake_usuarios.contas[1] = _conta(1, Papel.ADMINISTRADOR, StatusConta.ATIVO)
    fake_usuarios.contas[2] = _conta(2, Papel.ADMINISTRADOR, StatusConta.ATIVO)
    resp = client.patch(
        "/auth/admin/contas/1/status",
        json={"novo_status": "Banido"},
        headers=_admin(id_usuario=1),
    )
    assert resp.status_code == 403
    assert fake_usuarios.contas[1].status == StatusConta.ATIVO


def test_admin_nao_exclui_propria_conta(
    client: TestClient, fake_usuarios: FakeUsuariosRepo
):
    fake_usuarios.contas[1] = _conta(1, Papel.ADMINISTRADOR, StatusConta.ATIVO)
    fake_usuarios.contas[2] = _conta(2, Papel.ADMINISTRADOR, StatusConta.ATIVO)
    resp = client.delete("/auth/admin/contas/1", headers=_admin(id_usuario=1))
    assert resp.status_code == 403
    assert fake_usuarios.contas[1].status == StatusConta.ATIVO


def test_nao_bane_ultimo_admin_ativo_409(
    client: TestClient, fake_usuarios: FakeUsuariosRepo
):
    # Unico admin ativo e o alvo (2); o ator (1) tambem e admin mas banido.
    fake_usuarios.contas[1] = _conta(1, Papel.ADMINISTRADOR, StatusConta.BANIDO)
    fake_usuarios.contas[2] = _conta(2, Papel.ADMINISTRADOR, StatusConta.ATIVO)
    resp = client.patch(
        "/auth/admin/contas/2/status",
        json={"novo_status": "Banido"},
        headers=_admin(id_usuario=1),
    )
    assert resp.status_code == 409
    assert fake_usuarios.contas[2].status == StatusConta.ATIVO


def test_nao_exclui_ultimo_admin_ativo_409(
    client: TestClient, fake_usuarios: FakeUsuariosRepo
):
    fake_usuarios.contas[1] = _conta(1, Papel.ADMINISTRADOR, StatusConta.BANIDO)
    fake_usuarios.contas[2] = _conta(2, Papel.ADMINISTRADOR, StatusConta.ATIVO)
    resp = client.delete("/auth/admin/contas/2", headers=_admin(id_usuario=1))
    assert resp.status_code == 409
    assert fake_usuarios.contas[2].status == StatusConta.ATIVO


def test_bane_admin_com_outro_admin_ativo_permitido(
    client: TestClient, fake_usuarios: FakeUsuariosRepo
):
    # Dois admins ativos: banir um deles (o outro, nao o ator) e permitido.
    fake_usuarios.contas[1] = _conta(1, Papel.ADMINISTRADOR, StatusConta.ATIVO)
    fake_usuarios.contas[2] = _conta(2, Papel.ADMINISTRADOR, StatusConta.ATIVO)
    resp = client.patch(
        "/auth/admin/contas/2/status",
        json={"novo_status": "Banido"},
        headers=_admin(id_usuario=1),
    )
    assert resp.status_code == 200
    assert fake_usuarios.contas[2].status == StatusConta.BANIDO


def test_reativar_propria_conta_permitido(
    client: TestClient, fake_usuarios: FakeUsuariosRepo
):
    # Reativar (Ativo) nunca e bloqueado, nem para a propria conta.
    fake_usuarios.contas[1] = _conta(1, Papel.ADMINISTRADOR, StatusConta.DENUNCIADO)
    resp = client.patch(
        "/auth/admin/contas/1/status",
        json={"novo_status": "Ativo"},
        headers=_admin(id_usuario=1),
    )
    assert resp.status_code == 200
    assert fake_usuarios.contas[1].status == StatusConta.ATIVO


def test_bane_turista_nao_e_afetado_pela_guarda(
    client: TestClient, fake_usuarios: FakeUsuariosRepo
):
    # Banir um Turista nunca dispara a regra do ultimo admin.
    fake_usuarios.contas[1] = _conta(1, Papel.ADMINISTRADOR, StatusConta.ATIVO)
    fake_usuarios.contas[5] = _conta(5, Papel.TURISTA, StatusConta.ATIVO)
    resp = client.patch(
        "/auth/admin/contas/5/status",
        json={"novo_status": "Banido"},
        headers=_admin(id_usuario=1),
    )
    assert resp.status_code == 200
    assert fake_usuarios.contas[5].status == StatusConta.BANIDO


# --------------------------------------------------------------------------
# Guarda anti-lockout (funcao pura, testada diretamente).
# --------------------------------------------------------------------------


def test_guarda_pura_bloqueia_auto_alvo():
    r = avaliar_guarda_moderacao(
        id_alvo=1,
        id_admin_atual=1,
        papel_alvo=Papel.ADMINISTRADOR,
        acao=AcaoModeracao.BANIR,
        admins_ativos=5,
    )
    assert r.permitido is False
    assert r.codigo_http == 403


def test_guarda_pura_bloqueia_ultimo_admin():
    r = avaliar_guarda_moderacao(
        id_alvo=2,
        id_admin_atual=1,
        papel_alvo=Papel.ADMINISTRADOR,
        acao=AcaoModeracao.EXCLUIR,
        admins_ativos=1,
    )
    assert r.permitido is False
    assert r.codigo_http == 409


def test_guarda_pura_permite_com_outro_admin():
    r = avaliar_guarda_moderacao(
        id_alvo=2,
        id_admin_atual=1,
        papel_alvo=Papel.ADMINISTRADOR,
        acao=AcaoModeracao.BANIR,
        admins_ativos=2,
    )
    assert r.permitido is True


def test_guarda_pura_permite_reativar_mesmo_auto_alvo():
    r = avaliar_guarda_moderacao(
        id_alvo=1,
        id_admin_atual=1,
        papel_alvo=Papel.ADMINISTRADOR,
        acao=AcaoModeracao.REATIVAR,
        admins_ativos=1,
        novo_status=StatusConta.ATIVO,
    )
    assert r.permitido is True


def test_guarda_pura_permite_banir_turista():
    r = avaliar_guarda_moderacao(
        id_alvo=5,
        id_admin_atual=1,
        papel_alvo=Papel.TURISTA,
        acao=AcaoModeracao.BANIR,
        admins_ativos=1,
    )
    assert r.permitido is True


# --------------------------------------------------------------------------
# OpenAPI: as novas rotas aparecem em /openapi.json.
# --------------------------------------------------------------------------


def test_novas_rotas_crud_tabelas_no_openapi(client: TestClient):
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    assert "post" in paths["/catalogo/hospedagens"]
    assert "get" in paths["/catalogo/hospedagens"]
    assert "get" in paths["/catalogo/hospedagens/{id_hospedagem}"]
    assert "put" in paths["/catalogo/hospedagens/{id_hospedagem}"]
    assert "delete" in paths["/catalogo/hospedagens/{id_hospedagem}"]
    assert "get" in paths["/catalogo/pacotes/{id_pacote}"]
    assert "get" in paths["/catalogo/destinos"]


def test_put_catalogo_vincula_schemas_atualizar_no_openapi(client: TestClient):
    """As rotas PUT de catalogo bindam os schemas *Atualizar (nao os *Criar).

    Garante que ``HospedagemAtualizar``/``PacoteAtualizar``/``DestinoAtualizar``
    (antes nao-usados) ficam efetivamente ligados ao corpo do PUT, mantendo a
    simetria entre as tres entidades de catalogo.
    """
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]

    def _schema_ref_do_put(caminho: str) -> str:
        corpo = paths[caminho]["put"]["requestBody"]["content"]
        return corpo["application/json"]["schema"]["$ref"]

    assert _schema_ref_do_put("/catalogo/hospedagens/{id_hospedagem}").endswith(
        "/HospedagemAtualizar"
    )
    assert _schema_ref_do_put("/catalogo/pacotes/{id_pacote}").endswith(
        "/PacoteAtualizar"
    )
    assert _schema_ref_do_put("/catalogo/destinos/{id_destino}").endswith(
        "/DestinoAtualizar"
    )
