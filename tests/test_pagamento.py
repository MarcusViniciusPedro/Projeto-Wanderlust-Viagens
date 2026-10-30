"""Testes da maquina de estados de pagamento (RF5): transicoes e formas."""

from __future__ import annotations

import pytest

from app.integracoes.pagamento import StubGatewayPagamento
from app.vendas.schemas import FormaPagamento, StatusPagamento
from app.vendas.service import (
    PagamentoRecusadoError,
    TransicaoInvalidaError,
    cancelar,
    confirmar_pagamento,
    iniciar_pagamento,
    reembolsar,
)


@pytest.mark.parametrize(
    "forma",
    [
        FormaPagamento.DEBITO,
        FormaPagamento.CREDITO,
        FormaPagamento.PIX,
        FormaPagamento.BOLETO,
    ],
)
def test_fluxo_feliz_todas_as_formas(forma: FormaPagamento) -> None:
    gateway = StubGatewayPagamento()
    venda = iniciar_pagamento(1500.0, forma)
    assert venda.status_pagamento is StatusPagamento.PENDENTE

    paga = confirmar_pagamento(venda, gateway)
    assert paga.status_pagamento is StatusPagamento.PAGO
    assert paga.id_transacao is not None
    # Gateway foi efetivamente acionado para a forma correta.
    assert gateway.operacoes[-1].forma_pagamento == forma.value


def test_cancelar_venda_pendente() -> None:
    venda = iniciar_pagamento(1000.0, FormaPagamento.PIX)
    cancelada = cancelar(venda)
    assert cancelada.status_pagamento is StatusPagamento.CANCELADO


def test_reembolsar_venda_paga() -> None:
    gateway = StubGatewayPagamento()
    venda = iniciar_pagamento(1000.0, FormaPagamento.CREDITO)
    paga = confirmar_pagamento(venda, gateway)
    estornada = reembolsar(paga, gateway)
    assert estornada.status_pagamento is StatusPagamento.ESTORNADO
    assert gateway.operacoes[-1].tipo == "estornar"


def test_nao_pode_reembolsar_venda_pendente() -> None:
    gateway = StubGatewayPagamento()
    venda = iniciar_pagamento(1000.0, FormaPagamento.BOLETO)
    with pytest.raises(TransicaoInvalidaError):
        reembolsar(venda, gateway)


def test_nao_pode_cancelar_venda_paga() -> None:
    gateway = StubGatewayPagamento()
    venda = iniciar_pagamento(1000.0, FormaPagamento.DEBITO)
    paga = confirmar_pagamento(venda, gateway)
    with pytest.raises(TransicaoInvalidaError):
        cancelar(paga)


def test_nao_pode_pagar_venda_cancelada() -> None:
    gateway = StubGatewayPagamento()
    venda = iniciar_pagamento(1000.0, FormaPagamento.PIX)
    cancelada = cancelar(venda)
    with pytest.raises(TransicaoInvalidaError):
        confirmar_pagamento(cancelada, gateway)


def test_nao_pode_reembolsar_duas_vezes() -> None:
    gateway = StubGatewayPagamento()
    venda = iniciar_pagamento(1000.0, FormaPagamento.CREDITO)
    paga = confirmar_pagamento(venda, gateway)
    estornada = reembolsar(paga, gateway)
    with pytest.raises(TransicaoInvalidaError):
        reembolsar(estornada, gateway)


def test_pagamento_recusado_pelo_gateway() -> None:
    gateway = StubGatewayPagamento(aprovar=False)
    venda = iniciar_pagamento(1000.0, FormaPagamento.CREDITO)
    with pytest.raises(PagamentoRecusadoError):
        confirmar_pagamento(venda, gateway)


def test_valor_invalido_rejeitado() -> None:
    with pytest.raises(ValueError):
        iniciar_pagamento(0.0, FormaPagamento.PIX)
