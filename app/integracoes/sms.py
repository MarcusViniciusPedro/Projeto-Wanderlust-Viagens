"""Abstracao de envio de SMS para o fluxo de 2FA (RF2).

O envio real de SMS fica atras de uma interface (``SMSSender``). Em producao,
uma implementacao usaria ``Settings.sms_api_key`` / ``Settings.sms_sender``
(nunca segredos hardcoded). Para desenvolvimento e testes, ``StubSMSSender``
registra em memoria as mensagens enviadas para que o codigo possa ser lido sem
depender de um provedor externo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Protocol


@dataclass(frozen=True)
class MensagemSMS:
    """Representa um SMS enviado (ou capturado pelo stub)."""

    destino: str
    conteudo: str


class SMSSender(Protocol):
    """Interface de envio de SMS."""

    def enviar(self, destino: str, conteudo: str) -> None:
        """Envia uma mensagem de texto para ``destino``."""
        ...


@dataclass
class StubSMSSender:
    """Implementacao de teste: captura as mensagens em memoria.

    Permite que os testes leiam o codigo de 2FA enviado sem acessar um
    provedor real. A ultima mensagem fica acessivel via ``ultima_mensagem``.
    """

    enviadas: List[MensagemSMS] = field(default_factory=list)

    def enviar(self, destino: str, conteudo: str) -> None:
        self.enviadas.append(MensagemSMS(destino=destino, conteudo=conteudo))

    @property
    def ultima_mensagem(self) -> MensagemSMS | None:
        """Retorna a ultima mensagem enviada, ou None se nenhuma foi enviada."""
        return self.enviadas[-1] if self.enviadas else None

    def limpar(self) -> None:
        """Remove todas as mensagens capturadas."""
        self.enviadas.clear()


# Sender padrao do processo: stub em memoria enquanto nao ha provedor real
# configurado. Mantido aqui para que o servico de 2FA possa capturar codigos
# em desenvolvimento/testes sem exigir rede.
default_sms_sender: SMSSender = StubSMSSender()
