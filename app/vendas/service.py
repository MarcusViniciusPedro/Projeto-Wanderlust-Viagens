"""Maquina de estados de pagamento de uma venda (RF5), como logica pura.

Transicoes validas (os estados usam os valores exatos do CHECK do banco):

    Pendente --(confirmar_pagamento)--> Pago
    Pendente --(cancelar)------------> Cancelado
    Pago     --(reembolsar)----------> Estornado

Qualquer outra transicao e rejeitada com ``TransicaoInvalidaError``. As quatro
formas de pagamento (debito, credito, PIX, boleto) sao suportadas; o
processamento externo fica atras do stub ``GatewayPagamento``.

As funcoes recebem/retornam o estado de forma explicita, sem tocar no banco,
para serem totalmente testaveis sem SQL Server.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, FrozenSet, Optional

from app.integracoes.pagamento import GatewayPagamento
from app.vendas.schemas import FormaPagamento, StatusPagamento


class TransicaoInvalidaError(RuntimeError):
    """Levantado quando uma transicao de estado de pagamento e invalida."""


class PagamentoRecusadoError(RuntimeError):
    """Levantado quando o gateway recusa a autorizacao do pagamento."""


# Mapa de transicoes permitidas: estado atual -> estados alcancaveis.
TRANSICOES_VALIDAS: Dict[StatusPagamento, FrozenSet[StatusPagamento]] = {
    StatusPagamento.PENDENTE: frozenset(
        {StatusPagamento.PAGO, StatusPagamento.CANCELADO}
    ),
    StatusPagamento.PAGO: frozenset({StatusPagamento.ESTORNADO}),
    StatusPagamento.CANCELADO: frozenset(),
    StatusPagamento.ESTORNADO: frozenset(),
}


@dataclass(frozen=True)
class Venda:
    """Estado de uma venda para a maquina de estados de pagamento (RF5)."""

    valor_total: float
    forma_pagamento: FormaPagamento
    status_pagamento: StatusPagamento = StatusPagamento.PENDENTE
    id_venda: Optional[int] = None
    id_transacao: Optional[str] = None


def pode_transicionar(
    atual: StatusPagamento, destino: StatusPagamento
) -> bool:
    """Indica se a transicao ``atual -> destino`` e permitida."""
    return destino in TRANSICOES_VALIDAS.get(atual, frozenset())


def _exigir_transicao(atual: StatusPagamento, destino: StatusPagamento) -> None:
    if not pode_transicionar(atual, destino):
        raise TransicaoInvalidaError(
            f"Transicao invalida: '{atual.value}' -> '{destino.value}'."
        )


def iniciar_pagamento(
    valor_total: float, forma_pagamento: FormaPagamento
) -> Venda:
    """Cria uma venda no estado inicial 'Pendente' (RF5)."""
    if valor_total <= 0:
        raise ValueError("valor_total deve ser positivo.")
    return Venda(
        valor_total=valor_total,
        forma_pagamento=forma_pagamento,
        status_pagamento=StatusPagamento.PENDENTE,
    )


def confirmar_pagamento(venda: Venda, gateway: GatewayPagamento) -> Venda:
    """Transiciona 'Pendente' -> 'Pago' autorizando no gateway (RF5).

    Levanta ``TransicaoInvalidaError`` se a venda nao estiver pendente e
    ``PagamentoRecusadoError`` se o gateway nao aprovar a autorizacao.
    """
    _exigir_transicao(venda.status_pagamento, StatusPagamento.PAGO)
    resultado = gateway.autorizar(
        forma_pagamento=venda.forma_pagamento.value,
        valor=venda.valor_total,
        referencia=str(venda.id_venda or ""),
    )
    if not resultado.aprovado:
        raise PagamentoRecusadoError(
            f"Pagamento recusado pelo gateway: {resultado.detalhe}"
        )
    return replace(
        venda,
        status_pagamento=StatusPagamento.PAGO,
        id_transacao=resultado.id_transacao,
    )


def cancelar(venda: Venda) -> Venda:
    """Transiciona 'Pendente' -> 'Cancelado' (RF5).

    So e possivel cancelar uma venda ainda pendente; apos o pagamento, o fluxo
    correto e o reembolso (estorno).
    """
    _exigir_transicao(venda.status_pagamento, StatusPagamento.CANCELADO)
    return replace(venda, status_pagamento=StatusPagamento.CANCELADO)


def reembolsar(venda: Venda, gateway: GatewayPagamento) -> Venda:
    """Transiciona 'Pago' -> 'Estornado' estornando no gateway (RF5).

    Levanta ``TransicaoInvalidaError`` se a venda nao estiver paga.
    """
    _exigir_transicao(venda.status_pagamento, StatusPagamento.ESTORNADO)
    gateway.estornar(
        id_transacao=venda.id_transacao or "",
        valor=venda.valor_total,
    )
    return replace(venda, status_pagamento=StatusPagamento.ESTORNADO)
