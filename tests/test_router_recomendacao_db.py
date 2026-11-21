"""Testes de router do AIV DB-backed (FEAT-004) com FastAPI TestClient.

Cobrem as rotas que PERSISTEM/COLETAM as avaliacoes que o AIV usa para o
feedback agregado:
  POST /recomendacao/avaliacoes
  GET  /recomendacao/pacotes/{fk_pacote}/feedback

Sem SQL Server vivo: o ``app.recomendacao.repository`` e substituido por um
fake em memoria via monkeypatch (padrao de tests/test_router_cliente.py) e os
JWTs sao emitidos com ``criar_token_acesso`` + WANDERLUST_JWT_SECRET por env.
A heuristica pura (``agregar_feedback``) NAO e mockada: os testes exercitam o
service real atraves das rotas.

Verificamos:
  (a) POST /recomendacao/avaliacoes vincula fk_turista ao token (409 duplicado);
  (b) GET /recomendacao/pacotes/{id}/feedback agrega as avaliacoes via service;
  (c) sem token -> 401;
  (d) sem banco -> 503;
  (e) as rotas aparecem em GET /openapi.json.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import pytest
from fastapi.testclient import TestClient

from app.core.authz import Papel
from app.core.config import get_settings
from app.core.security import criar_token_acesso
from app.db.session import DatabaseNotConfiguredError
from app.recomendacao.repository import AvaliacaoDuplicadaError
from app.recomendacao.schemas import Avaliacao


# --------------------------------------------------------------------------
# Fake em memoria do repository do AIV (sem DB).
# --------------------------------------------------------------------------


@dataclass
class FakeRecomendacaoRepo:
    # (fk_turista, fk_pacote) -> (nota, comentario)
    avaliacoes: Dict[Tuple[int, int], Tuple[int, Optional[str]]] = field(
        default_factory=dict
    )
    proximo_id: int = 500

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
    repo = FakeRecomendacaoRepo()
    from app.recomendacao import repository

    for nome in (
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
# (a) POST /recomendacao/avaliacoes
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
# (a2) Corrida no INSERT: a UNIQUE(fk_turista, fk_pacote) barra o segundo
# pedido que escapou do SELECT previo. O repository traduz a IntegrityError do
# pymssql em AvaliacaoDuplicadaError e a rota responde 409 (nunca 500).
# --------------------------------------------------------------------------


class _FakeCursorIntegrityNoInsert:
    """Cursor que nao ve duplicata no SELECT mas quebra a UNIQUE no INSERT."""

    def __init__(self) -> None:
        self._ultimo_select_vazio = True

    def execute(self, sql, params=None):
        import pymssql

        if sql.strip().upper().startswith("SELECT"):
            # SELECT previo nao encontra o par (corrida): segue para o INSERT.
            self._ultimo_select_vazio = True
            return
        # INSERT: a restricao UNIQUE barra, como faria o SQL Server.
        raise pymssql.IntegrityError(
            "Violation of UNIQUE KEY constraint 'uq_avaliacao_turista_pacote'."
        )

    def fetchone(self):
        # SELECT previo retorna None (nenhuma linha): nao detecta duplicata.
        return None


class _FakeConnIntegrity:
    def __init__(self) -> None:
        self.rolled_back = False

    def cursor(self):
        return _FakeCursorIntegrityNoInsert()

    def commit(self):  # pragma: no cover - nao alcancado nesta corrida
        raise AssertionError("commit nao deve ocorrer apos a violacao da UNIQUE")

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


def test_registrar_avaliacao_corrida_insert_vira_duplicada(
    monkeypatch: pytest.MonkeyPatch,
):
    """Unit test do repository: IntegrityError no INSERT -> AvaliacaoDuplicadaError.

    Simula a corrida em que o SELECT previo nao viu a duplicata mas o INSERT
    violou a UNIQUE. Sem banco vivo: ``get_connection`` e substituido por uma
    conexao fake cujo INSERT levanta ``pymssql.IntegrityError``.
    """
    from app.recomendacao import repository

    conn = _FakeConnIntegrity()
    monkeypatch.setattr(repository, "get_connection", lambda settings=None: conn)

    with pytest.raises(AvaliacaoDuplicadaError):
        repository.registrar_avaliacao(fk_turista=7, fk_pacote=1, nota=5)
    assert conn.rolled_back is True


# --------------------------------------------------------------------------
# (b) GET /recomendacao/pacotes/{id}/feedback (agrega via service real)
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
# (c) autenticacao
# --------------------------------------------------------------------------


def test_avaliacoes_sem_token_401(
    client: TestClient, fake_repo: FakeRecomendacaoRepo
):
    assert (
        client.post(
            "/recomendacao/avaliacoes", json={"fk_pacote": 1, "nota": 5}
        ).status_code
        == 401
    )


# --------------------------------------------------------------------------
# (d) sem banco -> 503
# --------------------------------------------------------------------------


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
# (e) OpenAPI
# --------------------------------------------------------------------------


def test_novas_rotas_aiv_no_openapi(client: TestClient):
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    assert "post" in paths["/recomendacao/avaliacoes"]
    assert "get" in paths["/recomendacao/pacotes/{fk_pacote}/feedback"]
