"""Modelos e enums do modulo de vendas/pagamentos (RF5).

Os valores de ``StatusPagamento`` coincidem EXATAMENTE com o CHECK do banco
(``dbo.Venda.status_pagamento IN ('Pendente','Pago','Cancelado','Estornado')``)
para manter a logica Python alinhada com a camada SQL.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class StatusPagamento(str, Enum):
    """Estados possiveis do pagamento de uma venda (valores do CHECK do banco)."""

    PENDENTE = "Pendente"
    PAGO = "Pago"
    CANCELADO = "Cancelado"
    ESTORNADO = "Estornado"


class FormaPagamento(str, Enum):
    """Formas de pagamento suportadas (RF5)."""

    DEBITO = "debito"
    CREDITO = "credito"
    PIX = "pix"
    BOLETO = "boleto"


class CriarVendaRequest(BaseModel):
    """Dados para criar uma venda (RF5)."""

    fk_conta_turista: int
    fk_pacote: int
    valor_total: float = Field(gt=0)
    forma_pagamento: FormaPagamento
    fk_conta_colaborador: Optional[int] = None


class VendaSaida(BaseModel):
    """Representacao de uma venda e seu estado de pagamento."""

    id_venda: int
    valor_total: float
    status_pagamento: StatusPagamento
    forma_pagamento: FormaPagamento
