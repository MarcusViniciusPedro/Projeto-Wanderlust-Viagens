"""Rotas HTTP de vendas e pagamentos (RF5).

Endpoints:
  POST /vendas                 - cria uma venda (estado inicial 'Pendente')
  POST /vendas/{id}/pagar      - confirma o pagamento ('Pendente' -> 'Pago')
  POST /vendas/{id}/cancelar   - cancela ('Pendente' -> 'Cancelado')
  POST /vendas/{id}/reembolsar - reembolsa ('Pago' -> 'Estornado')

A maquina de estados (transicoes validas/invalidas) vive em ``service.py``
(logica pura e testavel). Sem banco configurado, ``DatabaseNotConfiguredError``
vira HTTP 503; transicoes invalidas viram HTTP 409.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.db.session import DatabaseNotConfiguredError
from app.integracoes.pagamento import default_gateway_pagamento
from app.vendas import repository
from app.vendas.schemas import (
    CriarVendaRequest,
    StatusPagamento,
    VendaSaida,
)
from app.vendas.service import (
    PagamentoRecusadoError,
    TransicaoInvalidaError,
    Venda,
    cancelar,
    confirmar_pagamento,
    iniciar_pagamento,
    reembolsar,
)

router = APIRouter(prefix="/vendas", tags=["vendas"])


def _erro_db_indisponivel() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "Banco de dados nao configurado. Configure as variaveis "
            "WANDERLUST_DB_* para habilitar a persistencia."
        ),
    )


@router.post("", response_model=VendaSaida, status_code=status.HTTP_201_CREATED)
def criar_venda(dados: CriarVendaRequest) -> VendaSaida:
    """Cria uma venda no estado 'Pendente' (RF5)."""
    venda = iniciar_pagamento(dados.valor_total, dados.forma_pagamento)
    try:
        id_venda = repository.registrar_venda(
            fk_conta_turista=dados.fk_conta_turista,
            fk_pacote=dados.fk_pacote,
            forma_pagamento=dados.forma_pagamento.value,
            fk_conta_colaborador=dados.fk_conta_colaborador,
        )
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    return VendaSaida(
        id_venda=id_venda,
        valor_total=venda.valor_total,
        status_pagamento=venda.status_pagamento,
        forma_pagamento=venda.forma_pagamento,
    )


def _transicionar(
    id_venda: int, origem: Venda, destino_status: StatusPagamento
) -> None:
    """Persiste o novo status; converte erro de DB em HTTP 503."""
    try:
        repository.atualizar_status(id_venda, destino_status)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc


@router.post("/{id_venda}/pagar", response_model=VendaSaida)
def pagar(id_venda: int, forma_pagamento: str, valor_total: float) -> VendaSaida:
    """Confirma o pagamento de uma venda pendente (RF5)."""
    from app.vendas.schemas import FormaPagamento

    venda = Venda(
        id_venda=id_venda,
        valor_total=valor_total,
        forma_pagamento=FormaPagamento(forma_pagamento),
        status_pagamento=StatusPagamento.PENDENTE,
    )
    try:
        paga = confirmar_pagamento(venda, default_gateway_pagamento)
    except TransicaoInvalidaError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PagamentoRecusadoError as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(exc)
        ) from exc

    _transicionar(id_venda, venda, StatusPagamento.PAGO)
    return VendaSaida(
        id_venda=id_venda,
        valor_total=paga.valor_total,
        status_pagamento=paga.status_pagamento,
        forma_pagamento=paga.forma_pagamento,
    )


@router.post("/{id_venda}/cancelar", response_model=VendaSaida)
def cancelar_venda(id_venda: int, forma_pagamento: str, valor_total: float) -> VendaSaida:
    """Cancela uma venda pendente (RF5)."""
    from app.vendas.schemas import FormaPagamento

    venda = Venda(
        id_venda=id_venda,
        valor_total=valor_total,
        forma_pagamento=FormaPagamento(forma_pagamento),
        status_pagamento=StatusPagamento.PENDENTE,
    )
    try:
        cancelada = cancelar(venda)
    except TransicaoInvalidaError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    _transicionar(id_venda, venda, StatusPagamento.CANCELADO)
    return VendaSaida(
        id_venda=id_venda,
        valor_total=cancelada.valor_total,
        status_pagamento=cancelada.status_pagamento,
        forma_pagamento=cancelada.forma_pagamento,
    )


@router.post("/{id_venda}/reembolsar", response_model=VendaSaida)
def reembolsar_venda(
    id_venda: int, forma_pagamento: str, valor_total: float
) -> VendaSaida:
    """Reembolsa (estorna) uma venda ja paga (RF5)."""
    from app.vendas.schemas import FormaPagamento

    venda = Venda(
        id_venda=id_venda,
        valor_total=valor_total,
        forma_pagamento=FormaPagamento(forma_pagamento),
        status_pagamento=StatusPagamento.PAGO,
    )
    try:
        estornada = reembolsar(venda, default_gateway_pagamento)
    except TransicaoInvalidaError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    _transicionar(id_venda, venda, StatusPagamento.ESTORNADO)
    return VendaSaida(
        id_venda=id_venda,
        valor_total=estornada.valor_total,
        status_pagamento=estornada.status_pagamento,
        forma_pagamento=estornada.forma_pagamento,
    )
