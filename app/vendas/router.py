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

from typing import Callable, List

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import UsuarioAtual, requer_autenticacao
from app.db.session import DatabaseNotConfiguredError
from app.integracoes.pagamento import default_gateway_pagamento
from app.vendas import repository
from app.vendas.schemas import (
    CriarCompraClienteRequest,
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


# ---------------------------------------------------------------------------
# Self-service do PROPRIO turista sobre as PROPRIAS compras (FEAT-003).
# Protegido por Depends(requer_autenticacao); o dono e sempre o id_passageiro
# do JWT. O cliente nunca informa fk_conta_turista: as rotas usam o id do
# token para listar/criar/validar posse, impedindo tocar compras de outro.
# ---------------------------------------------------------------------------


def _id_turista_do_token(usuario_atual: UsuarioAtual) -> int:
    """Extrai o id do turista do JWT ou levanta 401 para tokens antigos."""
    if usuario_atual.id_passageiro is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Token sem identificacao do passageiro (claim 'id'). "
                "Faca login novamente."
            ),
        )
    return usuario_atual.id_passageiro


def _venda_para_saida(venda: Venda) -> VendaSaida:
    return VendaSaida(
        id_venda=venda.id_venda,
        valor_total=venda.valor_total,
        status_pagamento=venda.status_pagamento,
        forma_pagamento=venda.forma_pagamento,
    )


@router.get("/minhas", response_model=List[VendaSaida])
def listar_minhas_compras(
    usuario_atual: UsuarioAtual = Depends(requer_autenticacao),
) -> List[VendaSaida]:
    """Lista as PROPRIAS compras do turista logado (RF5, self-service).

    Usa o id_passageiro do JWT como ``fk_conta_turista``; nunca um id do path.
    """
    id_turista = _id_turista_do_token(usuario_atual)
    try:
        vendas = repository.listar_vendas_por_turista(id_turista)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc
    return [_venda_para_saida(venda) for venda in vendas]


@router.post(
    "/minhas",
    response_model=VendaSaida,
    status_code=status.HTTP_201_CREATED,
)
def criar_minha_compra(
    dados: CriarCompraClienteRequest,
    usuario_atual: UsuarioAtual = Depends(requer_autenticacao),
) -> VendaSaida:
    """Cria uma compra do PROPRIO turista no estado 'Pendente' (RF5).

    Vincula ``fk_conta_turista`` ao id_passageiro do JWT, impedindo criar uma
    venda em nome de outro turista. A baixa/pagamento segue a maquina de
    estados ja existente (POST /vendas/{id}/pagar, /cancelar, /reembolsar); esta
    rota nao duplica a logica de pagamento. O valor retornado e o valor
    efetivamente persistido (preco_base do pacote).
    """
    id_turista = _id_turista_do_token(usuario_atual)
    # Valida a forma de pagamento (e o valor informado) pela logica pura antes
    # de tocar no banco; o valor definitivo vem do banco apos o registro.
    iniciar_pagamento(dados.valor_total, dados.forma_pagamento)
    try:
        id_venda, valor_persistido = repository.registrar_venda(
            fk_conta_turista=id_turista,
            fk_pacote=dados.fk_pacote,
            forma_pagamento=dados.forma_pagamento.value,
        )
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    return VendaSaida(
        id_venda=id_venda,
        valor_total=valor_persistido,
        status_pagamento=StatusPagamento.PENDENTE,
        forma_pagamento=dados.forma_pagamento,
    )


@router.get("/{id_venda}", response_model=VendaSaida)
def obter_minha_compra(
    id_venda: int,
    usuario_atual: UsuarioAtual = Depends(requer_autenticacao),
) -> VendaSaida:
    """Obtem uma compra PROPRIA do turista logado (RF5, checagem de posse).

    404 se a venda nao existir; 403 se existir mas pertencer a outro turista.
    """
    id_turista = _id_turista_do_token(usuario_atual)
    resultado = _carregar_venda_com_dono(id_venda)
    venda, dono = resultado
    _exigir_posse(dono, id_turista)
    return _venda_para_saida(venda)


def _carregar_venda_com_dono(id_venda: int) -> "tuple[Venda, int]":
    """Carrega (venda, dono); 404 se nao existir, 503 se sem DB."""
    try:
        resultado = repository.buscar_venda_com_dono(id_venda)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc
    if resultado is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Venda {id_venda} nao encontrada.",
        )
    return resultado


def _exigir_posse(dono: int, id_turista: int) -> None:
    """Levanta 403 quando a venda pertence a outro turista."""
    if dono != id_turista:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta compra pertence a outro turista.",
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
    """Cancela uma venda pendente (RF5).

    Rota operacional/administrativa sem checagem de posse. Para o cliente
    cancelar a PROPRIA compra com checagem de posse, use
    POST /vendas/minhas/{id_venda}/cancelar.
    """
    return _transicao_resposta(
        id_venda,
        cancelar,
        StatusPagamento.CANCELADO,
    )


@router.post("/minhas/{id_venda}/cancelar", response_model=VendaSaida)
def cancelar_minha_compra(
    id_venda: int,
    usuario_atual: UsuarioAtual = Depends(requer_autenticacao),
) -> VendaSaida:
    """Cancela a PROPRIA compra do turista logado (RF5, checagem de posse).

    404 se a venda nao existir; 403 se pertencer a outro turista. Reutiliza a
    maquina de estados de ``service.py`` (transicao 'Pendente' -> 'Cancelado'),
    sem duplicar a logica de pagamento. A escrita e condicional ao status
    esperado, fechando a corrida entre leitura e gravacao.
    """
    id_turista = _id_turista_do_token(usuario_atual)
    venda, dono = _carregar_venda_com_dono(id_venda)
    _exigir_posse(dono, id_turista)
    try:
        nova = cancelar(venda)
    except TransicaoInvalidaError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    _persistir_transicao(
        id_venda, venda.status_pagamento, StatusPagamento.CANCELADO
    )
    return _venda_para_saida(nova)


@router.post("/{id_venda}/reembolsar", response_model=VendaSaida)
def reembolsar_venda(id_venda: int) -> VendaSaida:
    """Reembolsa (estorna) uma venda ja paga (RF5)."""
    return _transicao_resposta(
        id_venda,
        lambda venda: reembolsar(venda, default_gateway_pagamento),
        StatusPagamento.ESTORNADO,
    )
