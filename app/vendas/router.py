"""Rotas HTTP de vendas e pagamentos (RF5).

Endpoints:
  POST /vendas                 - cria uma venda (estado inicial 'Pendente')
  POST /vendas/{id}/pagar      - confirma o pagamento ('Pendente' -> 'Pago')
  POST /vendas/{id}/cancelar   - cancela ('Pendente' -> 'Cancelado')
  POST /vendas/{id}/reembolsar - reembolsa ('Pago' -> 'Estornado')

A maquina de estados (transicoes validas/invalidas) vive em ``service.py``
(logica pura e testavel). Os endpoints de transicao NAO confiam em
status/valor/forma vindos do cliente: carregam a venda real do banco
(``repository.buscar_venda``) e transicionam a partir do estado persistido. A
escrita e condicional ao status esperado (``WHERE status_pagamento = ...``)
para fechar a corrida entre leitura e gravacao.

Sem banco configurado, ``DatabaseNotConfiguredError`` vira HTTP 503;
transicoes invalidas viram HTTP 409; venda inexistente vira HTTP 404.
"""

from __future__ import annotations

from typing import Callable

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


def _carregar_venda(id_venda: int) -> Venda:
    """Carrega a venda real do banco; 404 se nao existir, 503 se sem DB."""
    try:
        venda = repository.buscar_venda(id_venda)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc
    if venda is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Venda {id_venda} nao encontrada.",
        )
    return venda


def _persistir_transicao(
    id_venda: int, origem: StatusPagamento, destino: StatusPagamento
) -> None:
    """Grava o novo status de forma condicional ao status atual esperado.

    Se o UPDATE condicional nao afetar nenhuma linha, outra operacao mudou o
    estado no intervalo (corrida) e respondemos 409.
    """
    try:
        aplicou = repository.atualizar_status(
            id_venda, destino, status_esperado=origem
        )
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc
    if not aplicou:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "O estado da venda mudou durante a operacao. "
                "Recarregue e tente novamente."
            ),
        )


@router.post("", response_model=VendaSaida, status_code=status.HTTP_201_CREATED)
def criar_venda(dados: CriarVendaRequest) -> VendaSaida:
    """Cria uma venda no estado 'Pendente' (RF5).

    O ``valor_total`` retornado e o valor EFETIVAMENTE persistido (preco_base do
    pacote, gravado pela procedure), nao o valor enviado pelo cliente.
    """
    # Valida a forma de pagamento (e o valor informado) pela logica pura antes
    # de tocar no banco; o valor definitivo vem do banco apos o registro.
    iniciar_pagamento(dados.valor_total, dados.forma_pagamento)
    try:
        id_venda, valor_persistido = repository.registrar_venda(
            fk_conta_turista=dados.fk_conta_turista,
            fk_pacote=dados.fk_pacote,
            forma_pagamento=dados.forma_pagamento.value,
            fk_conta_colaborador=dados.fk_conta_colaborador,
        )
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    return VendaSaida(
        id_venda=id_venda,
        valor_total=valor_persistido,
        status_pagamento=StatusPagamento.PENDENTE,
        forma_pagamento=dados.forma_pagamento,
    )


def _transicao_resposta(
    id_venda: int,
    transicao: Callable[[Venda], Venda],
    destino: StatusPagamento,
) -> VendaSaida:
    """Fluxo comum: carrega a venda real, transiciona e persiste condicional."""
    origem = _carregar_venda(id_venda)
    try:
        nova = transicao(origem)
    except TransicaoInvalidaError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except PagamentoRecusadoError as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(exc)
        ) from exc

    _persistir_transicao(id_venda, origem.status_pagamento, destino)
    return VendaSaida(
        id_venda=id_venda,
        valor_total=nova.valor_total,
        status_pagamento=nova.status_pagamento,
        forma_pagamento=nova.forma_pagamento,
    )


@router.post("/{id_venda}/pagar", response_model=VendaSaida)
def pagar(id_venda: int) -> VendaSaida:
    """Confirma o pagamento de uma venda pendente (RF5).

    Carrega a venda real do banco; o valor/forma vem do estado persistido.
    """
    return _transicao_resposta(
        id_venda,
        lambda venda: confirmar_pagamento(venda, default_gateway_pagamento),
        StatusPagamento.PAGO,
    )


@router.post("/{id_venda}/cancelar", response_model=VendaSaida)
def cancelar_venda(id_venda: int) -> VendaSaida:
    """Cancela uma venda pendente (RF5)."""
    return _transicao_resposta(
        id_venda,
        cancelar,
        StatusPagamento.CANCELADO,
    )


@router.post("/{id_venda}/reembolsar", response_model=VendaSaida)
def reembolsar_venda(id_venda: int) -> VendaSaida:
    """Reembolsa (estorna) uma venda ja paga (RF5)."""
    return _transicao_resposta(
        id_venda,
        lambda venda: reembolsar(venda, default_gateway_pagamento),
        StatusPagamento.ESTORNADO,
    )
