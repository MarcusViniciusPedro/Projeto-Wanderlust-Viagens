"""Testes de router de vendas/pagamentos (RF5) com FastAPI TestClient.

Substituem a camada ``app.vendas.repository`` por um fake em memoria (sem SQL
Server vivo) para exercitar a composicao dos endpoints de transicao. Cobrem os
bugs que passavam verdes por falta de teste de router:
  - as transicoes agora partem do estado REAL carregado do banco (fake), e nao
    de status/valor/forma vindos do cliente;
  - a gravacao e condicional ao status esperado (fecha a corrida): uma segunda
    transicao a partir de um estado ja alterado responde 409;
  - ``criar_venda`` retorna o valor EFETIVAMENTE persistido (preco do pacote),
    e nao o valor enviado pelo cliente.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.vendas.schemas import FormaPagamento, StatusPagamento
from app.vendas.service import Venda


class FakeVendasRepo:
    """Fake em memoria da camada de persistencia de vendas."""

    def __init__(self) -> None:
        self.vendas: dict[int, Venda] = {}
        self.proximo_id = 1
        # Valor que a "procedure" persiste (preco_base do pacote), que pode
        # divergir do valor_total enviado pelo cliente.
        self.preco_persistido = 2500.00

    def buscar_venda(self, id_venda: int, settings=None):
        return self.vendas.get(id_venda)

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
        return id_venda, self.preco_persistido

    def atualizar_status(
        self, id_venda, novo_status, status_esperado=None, settings=None
    ):
        venda = self.vendas.get(id_venda)
        if venda is None:
            return False
        if status_esperado is not None and venda.status_pagamento != status_esperado:
            return False  # corrida: estado mudou
        from dataclasses import replace

        self.vendas[id_venda] = replace(venda, status_pagamento=novo_status)
        return True


@pytest.fixture()
def fake_repo(monkeypatch: pytest.MonkeyPatch) -> FakeVendasRepo:
    repo = FakeVendasRepo()
    from app.vendas import repository

    monkeypatch.setattr(repository, "buscar_venda", repo.buscar_venda)
    monkeypatch.setattr(repository, "registrar_venda", repo.registrar_venda)
    monkeypatch.setattr(repository, "atualizar_status", repo.atualizar_status)
    return repo


@pytest.fixture()
def client() -> TestClient:
    import app.main as main

    return TestClient(main.app)


def _criar(client: TestClient, valor_total: float = 999.0) -> int:
    resp = client.post(
        "/vendas",
        json={
            "fk_conta_turista": 1,
            "fk_pacote": 1,
            "valor_total": valor_total,
            "forma_pagamento": "credito",
        },
    )
    assert resp.status_code == 201
    return resp.json()


def test_criar_venda_retorna_valor_persistido(
    client: TestClient, fake_repo: FakeVendasRepo
) -> None:
    """A resposta usa o valor do banco (preco do pacote), nao o do cliente."""
    corpo = _criar(client, valor_total=1.0)
    assert corpo["valor_total"] == fake_repo.preco_persistido
    assert corpo["status_pagamento"] == StatusPagamento.PENDENTE.value


def test_pagar_a_partir_do_estado_persistido(
    client: TestClient, fake_repo: FakeVendasRepo
) -> None:
    id_venda = _criar(client)["id_venda"]
    resp = client.post(f"/vendas/{id_venda}/pagar")
    assert resp.status_code == 200
    assert resp.json()["status_pagamento"] == StatusPagamento.PAGO.value
    assert fake_repo.vendas[id_venda].status_pagamento == StatusPagamento.PAGO


def test_reembolsar_venda_pendente_e_rejeitado(
    client: TestClient, fake_repo: FakeVendasRepo
) -> None:
    """Nao da para 'reembolsar' uma venda que no banco esta Pendente."""
    id_venda = _criar(client)["id_venda"]
    resp = client.post(f"/vendas/{id_venda}/reembolsar")
    assert resp.status_code == 409  # transicao invalida a partir do estado real
    assert fake_repo.vendas[id_venda].status_pagamento == StatusPagamento.PENDENTE


def test_pagar_venda_ja_paga_e_rejeitado(
    client: TestClient, fake_repo: FakeVendasRepo
) -> None:
    id_venda = _criar(client)["id_venda"]
    assert client.post(f"/vendas/{id_venda}/pagar").status_code == 200
    # Segunda tentativa: estado real ja e 'Pago' -> transicao invalida.
    resp = client.post(f"/vendas/{id_venda}/pagar")
    assert resp.status_code == 409


def test_fluxo_pago_para_estornado(
    client: TestClient, fake_repo: FakeVendasRepo
) -> None:
    id_venda = _criar(client)["id_venda"]
    client.post(f"/vendas/{id_venda}/pagar")
    resp = client.post(f"/vendas/{id_venda}/reembolsar")
    assert resp.status_code == 200
    assert resp.json()["status_pagamento"] == StatusPagamento.ESTORNADO.value


def test_cancelar_venda_pendente(
    client: TestClient, fake_repo: FakeVendasRepo
) -> None:
    id_venda = _criar(client)["id_venda"]
    resp = client.post(f"/vendas/{id_venda}/cancelar")
    assert resp.status_code == 200
    assert resp.json()["status_pagamento"] == StatusPagamento.CANCELADO.value


def test_transicao_venda_inexistente_404(
    client: TestClient, fake_repo: FakeVendasRepo
) -> None:
    resp = client.post("/vendas/999/pagar")
    assert resp.status_code == 404


def test_update_condicional_fecha_corrida(
    client: TestClient, fake_repo: FakeVendasRepo
) -> None:
    """Se o estado muda entre a leitura e a gravacao, responde 409.

    Simula a corrida substituindo atualizar_status por uma versao que, ao ser
    chamada, encontra o status ja alterado por outra operacao concorrente.
    """
    id_venda = _criar(client)["id_venda"]

    original = fake_repo.atualizar_status

    def atualizar_com_corrida(iv, novo, status_esperado=None, settings=None):
        # Outra operacao concorrente paga a venda antes da gravacao desta.
        from dataclasses import replace

        atual = fake_repo.vendas[iv]
        if atual.status_pagamento == StatusPagamento.PENDENTE:
            fake_repo.vendas[iv] = replace(
                atual, status_pagamento=StatusPagamento.PAGO
            )
        return original(iv, novo, status_esperado=status_esperado)

    from app.vendas import repository

    repository.atualizar_status = atualizar_com_corrida
    try:
        # Tentamos cancelar (Pendente->Cancelado), mas a corrida ja marcou Pago.
        resp = client.post(f"/vendas/{id_venda}/cancelar")
        assert resp.status_code == 409
    finally:
        repository.atualizar_status = original
