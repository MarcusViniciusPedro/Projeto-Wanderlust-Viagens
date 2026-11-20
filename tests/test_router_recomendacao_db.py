"""Testes de router do AIV DB-backed (FEAT-004) com FastAPI TestClient.

Cobrem as rotas que COLETAM/PERSISTEM dados que o AIV usa para personalizar a
recomendacao do turista logado:
  GET  /recomendacao/para-mim
  GET/PUT /recomendacao/preferencias/me
  POST /recomendacao/avaliacoes
  GET  /recomendacao/pacotes/{fk_pacote}/feedback

Sem SQL Server vivo: o ``app.recomendacao.repository`` e substituido por um
fake em memoria via monkeypatch (padrao de tests/test_router_cliente.py) e os
JWTs sao emitidos com ``criar_token_acesso`` + WANDERLUST_JWT_SECRET por env.
A heuristica pura (``recomendar``/``agregar_feedback``) NAO e mockada: os
testes exercitam o service real atraves das rotas.

Verificamos:
  (a) GET /recomendacao/para-mim usa a Preferencia e os pacotes do fake e
      retorna um ranking deterministico para o turista do token;
  (b) turista sem Preferencia ainda recebe ranking (preferencia vazia);
  (c) PUT /recomendacao/preferencias/me grava e GET le de volta a do dono;
  (d) POST /recomendacao/avaliacoes vincula fk_turista ao token (409 duplicado);
  (e) GET /recomendacao/pacotes/{id}/feedback agrega as avaliacoes via service;
  (f) sem token -> 401; token sem id -> 401;
  (g) sem banco -> 503;
  (h) as novas rotas aparecem em GET /openapi.json.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pytest
from fastapi.testclient import TestClient

from app.core.authz import Papel
from app.core.config import get_settings
from app.core.security import criar_token_acesso
from app.db.session import DatabaseNotConfiguredError
from app.recomendacao.repository import AvaliacaoDuplicadaError
from app.recomendacao.schemas import Avaliacao, PacoteParaRecomendacao, Preferencia


# --------------------------------------------------------------------------
# Fake em memoria do repository do AIV (sem DB).
# --------------------------------------------------------------------------


@dataclass
class FakeRecomendacaoRepo:
    pacotes: List[PacoteParaRecomendacao] = field(default_factory=list)
    preferencias: Dict[int, Preferencia] = field(default_factory=dict)
    # (fk_turista, fk_pacote) -> (nota, comentario)
    avaliacoes: Dict[Tuple[int, int], Tuple[int, Optional[str]]] = field(
        default_factory=dict
    )
    proximo_id: int = 500

    def listar_pacotes_para_recomendacao(self, settings=None):
        return list(self.pacotes)

    def buscar_preferencia_turista(self, fk_turista, settings=None):
        return self.preferencias.get(fk_turista)

    def upsert_preferencia(
        self,
        fk_turista,
        *,
        tipo_viagem,
        nivel,
        orcamento_max,
        estacao_preferida,
        observacoes,
        settings=None,
    ):
        pref = Preferencia(
            tipo_viagem=tipo_viagem,
            nivel=nivel,
            orcamento_max=orcamento_max,
            estacao_preferida=estacao_preferida,
        )
        self.preferencias[fk_turista] = pref
        return pref

    def registrar_avaliacao(
        self, fk_turista, fk_pacote, nota, comentario=None, settings=None
    ):
        chave = (fk_turista, fk_pacote)
        if chave in self.avaliacoes:
            raise AvaliacaoDuplicadaError("Voce ja avaliou este pacote.")
        self.avaliacoes[chave] = (nota, comentario)
        id_avaliacao = self.proximo_id
        self.proximo_id += 1
        return id_avaliacao

    def listar_avaliacoes_do_pacote(self, fk_pacote, settings=None):
        return [
            Avaliacao(nota=nota, comentario=comentario)
            for (_turista, pacote), (nota, comentario) in self.avaliacoes.items()
            if pacote == fk_pacote
        ]


# --------------------------------------------------------------------------
# Fixtures.
# --------------------------------------------------------------------------


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("WANDERLUST_JWT_SECRET", "segredo-de-teste-aiv")
    get_settings.cache_clear()
    import app.main as main

    try:
        yield TestClient(main.app)
    finally:
        get_settings.cache_clear()


@pytest.fixture()
def fake_repo(monkeypatch: pytest.MonkeyPatch) -> FakeRecomendacaoRepo:
    repo = FakeRecomendacaoRepo(
        pacotes=[
            PacoteParaRecomendacao(
                id_pacote=1,
                preco_base=2000.0,
                tipo_viagem="Praia",
                nivel="Conforto",
                score_avaliacoes=4.8,
                total_avaliacoes=10,
            ),
            PacoteParaRecomendacao(
                id_pacote=2,
                preco_base=2000.0,
                tipo_viagem="Serra",
                nivel="Economico",
            ),
        ],
        preferencias={
            1: Preferencia(
                tipo_viagem="Praia", nivel="Conforto", orcamento_max=3000.0
            )
        },
    )
    from app.recomendacao import repository

    for nome in (
        "listar_pacotes_para_recomendacao",
        "buscar_preferencia_turista",
        "upsert_preferencia",
        "registrar_avaliacao",
        "listar_avaliacoes_do_pacote",
    ):
        monkeypatch.setattr(repository, nome, getattr(repo, nome))
    return repo


def _turista(id_usuario: Optional[int] = 1) -> dict[str, str]:
    token = criar_token_acesso(
        subject="t@ex.com", papel=Papel.TURISTA.value, id_usuario=id_usuario
    )
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------
# (a)(b) GET /recomendacao/para-mim
# --------------------------------------------------------------------------


def test_para_mim_usa_preferencia_e_pacotes_do_turista(
    client: TestClient, fake_repo: FakeRecomendacaoRepo
):
    resp = client.get("/recomendacao/para-mim", headers=_turista(1))
    assert resp.status_code == 200
    itens = resp.json()
    # Pacote 1 adere a preferencia (Praia/Conforto) + boa reputacao => 1o lugar.
    assert itens[0]["id_pacote"] == 1
    assert itens[0]["score"] > itens[1]["score"]
    assert itens[0]["dentro_do_orcamento"] is True


def test_para_mim_sem_preferencia_ainda_ranqueia(
    client: TestClient, fake_repo: FakeRecomendacaoRepo
):
    # Turista 2 nao tem Preferencia salva: usa Preferencia vazia e ainda ranqueia.
    resp = client.get("/recomendacao/para-mim", headers=_turista(2))
    assert resp.status_code == 200
    itens = resp.json()
    assert len(itens) == 2
    # Sem aderencia por tipo/nivel, a reputacao do pacote 1 o coloca na frente.
    assert itens[0]["id_pacote"] == 1


# --------------------------------------------------------------------------
# (c) GET/PUT /recomendacao/preferencias/me
# --------------------------------------------------------------------------


def test_preferencia_get_404_quando_nao_existe(
    client: TestClient, fake_repo: FakeRecomendacaoRepo
):
    resp = client.get("/recomendacao/preferencias/me", headers=_turista(2))
    assert resp.status_code == 404


def test_preferencia_put_grava_e_get_le_do_dono(
    client: TestClient, fake_repo: FakeRecomendacaoRepo
):
    resp = client.put(
        "/recomendacao/preferencias/me",
        json={"tipo_viagem": "Serra", "nivel": "Luxo", "orcamento_max": 5000.0},
        headers=_turista(2),
    )
    assert resp.status_code == 200
    assert resp.json()["tipo_viagem"] == "Serra"
    # Gravou para o turista do token (2), nao para outro.
    assert fake_repo.preferencias[2].nivel == "Luxo"

    resp2 = client.get("/recomendacao/preferencias/me", headers=_turista(2))
    assert resp2.status_code == 200
    assert resp2.json()["orcamento_max"] == 5000.0


# --------------------------------------------------------------------------
# (d) POST /recomendacao/avaliacoes
# --------------------------------------------------------------------------


def test_avaliacao_vincula_fk_turista_ao_token(
    client: TestClient, fake_repo: FakeRecomendacaoRepo
):
    resp = client.post(
        "/recomendacao/avaliacoes",
        json={"fk_pacote": 1, "nota": 5, "comentario": "Otimo"},
        headers=_turista(7),
    )
    assert resp.status_code == 201
    assert resp.json()["fk_pacote"] == 1
    # A avaliacao pertence ao turista do token (7), nao a um id do corpo.
    assert (7, 1) in fake_repo.avaliacoes


def test_avaliacao_duplicada_409(
    client: TestClient, fake_repo: FakeRecomendacaoRepo
):
    corpo = {"fk_pacote": 1, "nota": 5}
    assert client.post(
        "/recomendacao/avaliacoes", json=corpo, headers=_turista(7)
    ).status_code == 201
    resp = client.post(
        "/recomendacao/avaliacoes", json=corpo, headers=_turista(7)
    )
    assert resp.status_code == 409


def test_avaliacao_nota_invalida_422(
    client: TestClient, fake_repo: FakeRecomendacaoRepo
):
    resp = client.post(
        "/recomendacao/avaliacoes",
        json={"fk_pacote": 1, "nota": 9},
        headers=_turista(7),
    )
    assert resp.status_code == 422


# --------------------------------------------------------------------------
# (e) GET /recomendacao/pacotes/{id}/feedback (agrega via service real)
# --------------------------------------------------------------------------


def test_feedback_do_pacote_agrega_avaliacoes_persistidas(
    client: TestClient, fake_repo: FakeRecomendacaoRepo
):
    fake_repo.avaliacoes[(1, 3)] = (5, None)
    fake_repo.avaliacoes[(2, 3)] = (4, None)
    resp = client.get("/recomendacao/pacotes/3/feedback")
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["fk_pacote"] == 3
    assert corpo["total_avaliacoes"] == 2
    assert corpo["score_agregado"] == pytest.approx(4.5, abs=0.01)


def test_feedback_do_pacote_sem_avaliacoes(
    client: TestClient, fake_repo: FakeRecomendacaoRepo
):
    resp = client.get("/recomendacao/pacotes/99/feedback")
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["score_agregado"] is None
    assert corpo["total_avaliacoes"] == 0


# --------------------------------------------------------------------------
# (f) autenticacao
# --------------------------------------------------------------------------


def test_rotas_protegidas_sem_token_401(
    client: TestClient, fake_repo: FakeRecomendacaoRepo
):
    assert client.get("/recomendacao/para-mim").status_code == 401
    assert client.get("/recomendacao/preferencias/me").status_code == 401
    assert (
        client.put("/recomendacao/preferencias/me", json={}).status_code == 401
    )
    assert (
        client.post(
            "/recomendacao/avaliacoes", json={"fk_pacote": 1, "nota": 5}
        ).status_code
        == 401
    )


def test_para_mim_token_sem_id_401(
    client: TestClient, fake_repo: FakeRecomendacaoRepo
):
    resp = client.get("/recomendacao/para-mim", headers=_turista(id_usuario=None))
    assert resp.status_code == 401


# --------------------------------------------------------------------------
# (g) sem banco -> 503
# --------------------------------------------------------------------------


def test_para_mim_sem_banco_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    from app.recomendacao import repository

    def _sem_banco(*_a, **_k):
        raise DatabaseNotConfiguredError("sem banco")

    monkeypatch.setattr(repository, "buscar_preferencia_turista", _sem_banco)
    resp = client.get("/recomendacao/para-mim", headers=_turista(1))
    assert resp.status_code == 503


def test_feedback_do_pacote_sem_banco_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    from app.recomendacao import repository

    def _sem_banco(*_a, **_k):
        raise DatabaseNotConfiguredError("sem banco")

    monkeypatch.setattr(repository, "listar_avaliacoes_do_pacote", _sem_banco)
    resp = client.get("/recomendacao/pacotes/1/feedback")
    assert resp.status_code == 503


# --------------------------------------------------------------------------
# (h) OpenAPI
# --------------------------------------------------------------------------


def test_novas_rotas_aiv_no_openapi(client: TestClient):
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    assert "get" in paths["/recomendacao/para-mim"]
    assert "get" in paths["/recomendacao/preferencias/me"]
    assert "put" in paths["/recomendacao/preferencias/me"]
    assert "post" in paths["/recomendacao/avaliacoes"]
    assert "get" in paths["/recomendacao/pacotes/{fk_pacote}/feedback"]
