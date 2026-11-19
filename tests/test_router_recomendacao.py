"""Testes de router do AIV (RF4/RF7/RF8) com FastAPI TestClient.

Cobrem especialmente o endpoint de feedback (RF8), que antes nao era exposto
por nenhuma rota. As rotas do AIV nao dependem de banco: operam sobre o corpo
da requisicao e delegam a heuristica deterministica em ``service.py``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> TestClient:
    import app.main as main

    return TestClient(main.app)


def test_orcamento_endpoint(client: TestClient) -> None:
    resp = client.post("/recomendacao/orcamento", json={"preco_base": 1000.0})
    assert resp.status_code == 200
    assert resp.json()["total_estimado"] == 1000.0


def test_ranking_endpoint(client: TestClient) -> None:
    payload = {
        "preferencia": {"tipo_viagem": "Praia", "nivel": "Conforto"},
        "pacotes": [
            {"id_pacote": 1, "preco_base": 2000, "tipo_viagem": "Praia", "nivel": "Conforto"},
            {"id_pacote": 2, "preco_base": 2000, "tipo_viagem": "Serra", "nivel": "Economico"},
        ],
    }
    resp = client.post("/recomendacao/ranking", json=payload)
    assert resp.status_code == 200
    itens = resp.json()
    assert itens[0]["id_pacote"] == 1  # melhor aderencia vem primeiro


def test_feedback_endpoint_agrega_avaliacoes(client: TestClient) -> None:
    """RF8 exposto por HTTP: agrega notas em score + resumo deterministico."""
    resp = client.post(
        "/recomendacao/feedback",
        json={
            "fk_pacote": 7,
            "avaliacoes": [{"nota": 5}, {"nota": 4}, {"nota": 5}],
        },
    )
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["fk_pacote"] == 7
    assert corpo["total_avaliacoes"] == 3
    assert corpo["score_agregado"] == pytest.approx(4.67, abs=0.01)
    assert "media" in corpo["resumo"]


def test_feedback_endpoint_sem_avaliacoes(client: TestClient) -> None:
    resp = client.post(
        "/recomendacao/feedback", json={"fk_pacote": 9, "avaliacoes": []}
    )
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["score_agregado"] is None
    assert corpo["total_avaliacoes"] == 0


def test_feedback_endpoint_nota_invalida_422(client: TestClient) -> None:
    resp = client.post(
        "/recomendacao/feedback",
        json={"fk_pacote": 1, "avaliacoes": [{"nota": 9}]},
    )
    assert resp.status_code == 422
