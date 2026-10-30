"""Gateway de pagamento atras de uma interface stub configuravel (RF5).

O processamento real de pagamentos (debito, credito, PIX, boleto) fica atras de
uma interface (``GatewayPagamento``). Em producao, uma implementacao usaria
``Settings.payment_api_key`` / ``Settings.payment_base_url`` (nunca segredos
hardcoded). Para desenvolvimento e testes, ``StubGatewayPagamento`` aprova de
forma deterministica e registra as operacoes em memoria, permitindo exercitar a
maquina de estados de ``app.vendas`` sem rede.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Protocol


@dataclass(frozen=True)
class ResultadoPagamento:
    """Resultado de uma operacao no gateway (autorizacao ou estorno)."""

    aprovado: bool
    id_transacao: str
    detalhe: str = ""


@dataclass(frozen=True)
class OperacaoPagamento:
    """Registro de uma operacao enviada ao gateway (capturada pelo stub)."""

    tipo: str  # 'autorizar' ou 'estornar'
    forma_pagamento: str
    valor: float
    referencia: str


class GatewayPagamento(Protocol):
    """Interface de um gateway de pagamento."""

    def autorizar(
        self, forma_pagamento: str, valor: float, referencia: str
    ) -> ResultadoPagamento:
        """Autoriza/captura um pagamento."""
        ...

    def estornar(self, id_transacao: str, valor: float) -> ResultadoPagamento:
        """Estorna (reembolsa) um pagamento ja capturado."""
        ...


@dataclass
class StubGatewayPagamento:
    """Gateway de teste: aprova deterministicamente e registra operacoes.

    Util para exercitar a maquina de estados sem um provedor real. O atributo
    ``aprovar`` permite simular recusa de autorizacao em testes.
    """

    aprovar: bool = True
    operacoes: List[OperacaoPagamento] = field(default_factory=list)
    _contador: int = 0

    def autorizar(
        self, forma_pagamento: str, valor: float, referencia: str
    ) -> ResultadoPagamento:
        self.operacoes.append(
            OperacaoPagamento("autorizar", forma_pagamento, valor, referencia)
        )
        self._contador += 1
        return ResultadoPagamento(
            aprovado=self.aprovar,
            id_transacao=f"stub-tx-{self._contador}",
            detalhe="aprovado" if self.aprovar else "recusado",
        )

    def estornar(self, id_transacao: str, valor: float) -> ResultadoPagamento:
        self.operacoes.append(
            OperacaoPagamento("estornar", "", valor, id_transacao)
        )
        return ResultadoPagamento(
            aprovado=True, id_transacao=id_transacao, detalhe="estornado"
        )


# Gateway padrao do processo: stub em memoria enquanto nao ha provedor real.
default_gateway_pagamento: GatewayPagamento = StubGatewayPagamento()
