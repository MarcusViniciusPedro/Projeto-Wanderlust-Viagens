"""Envio de e-mail de confirmacao de viagem + propaganda (RF6), com stub.

Na confirmacao de uma venda, o sistema monta um e-mail com os detalhes da
viagem comprada e uma secao de propaganda com outros pacotes recomendados pelo
AIV. O envio real fica atras de uma interface (``EmailSender``) que, em
producao, usaria ``Settings.email_api_key`` / ``Settings.email_from`` (nunca
segredos hardcoded). ``StubEmailSender`` captura os e-mails em memoria para os
testes lerem o conteudo sem depender de um provedor externo.

A funcao ``montar_email_confirmacao`` e PURA e testavel: produz o assunto e o
corpo a partir dos detalhes da viagem e da lista de pacotes recomendados.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Protocol, Sequence


@dataclass(frozen=True)
class DetalhesViagem:
    """Detalhes da viagem adquirida, para o corpo do e-mail (RF6)."""

    id_venda: int
    destino: str
    data_inicio: str
    data_fim: str
    valor_total: float
    tipo_viagem: Optional[str] = None
    nivel: Optional[str] = None


@dataclass(frozen=True)
class PacotePropaganda:
    """Pacote recomendado pelo AIV exibido como propaganda no e-mail (RF6)."""

    id_pacote: int
    descricao: str
    preco_base: float


@dataclass(frozen=True)
class Email:
    """Representa um e-mail montado (e capturado pelo stub)."""

    destino: str
    assunto: str
    corpo: str


class EmailSender(Protocol):
    """Interface de envio de e-mail."""

    def enviar(self, destino: str, assunto: str, corpo: str) -> None:
        """Envia um e-mail para ``destino``."""
        ...


@dataclass
class StubEmailSender:
    """Implementacao de teste: captura os e-mails em memoria."""

    enviados: List[Email] = field(default_factory=list)

    def enviar(self, destino: str, assunto: str, corpo: str) -> None:
        self.enviados.append(Email(destino=destino, assunto=assunto, corpo=corpo))

    @property
    def ultimo(self) -> Optional[Email]:
        """Retorna o ultimo e-mail enviado, ou None se nenhum foi enviado."""
        return self.enviados[-1] if self.enviados else None

    def limpar(self) -> None:
        """Remove todos os e-mails capturados."""
        self.enviados.clear()


def montar_email_confirmacao(
    detalhes: DetalhesViagem,
    recomendados: Sequence[PacotePropaganda],
) -> Email:
    """Monta o e-mail de confirmacao de viagem + propaganda (RF6), sem enviar.

    O corpo contem os detalhes da viagem e uma secao "Voce tambem pode gostar"
    com os pacotes recomendados pelo AIV. Funcao pura e deterministica.
    """
    assunto = f"Confirmacao da sua viagem para {detalhes.destino} - Wanderlust"

    linhas: List[str] = [
        "Ola! Sua compra foi confirmada. Boa viagem!",
        "",
        "== Detalhes da sua viagem ==",
        f"Venda: #{detalhes.id_venda}",
        f"Destino: {detalhes.destino}",
        f"Periodo: {detalhes.data_inicio} a {detalhes.data_fim}",
    ]
    if detalhes.tipo_viagem:
        linhas.append(f"Tipo: {detalhes.tipo_viagem}")
    if detalhes.nivel:
        linhas.append(f"Nivel: {detalhes.nivel}")
    linhas.append(f"Valor total: R$ {detalhes.valor_total:.2f}")

    # Secao de propaganda: outros pacotes recomendados pelo AIV (RF6).
    linhas.append("")
    linhas.append("== Voce tambem pode gostar (recomendacoes Wanderlust) ==")
    if recomendados:
        for pac in recomendados:
            linhas.append(
                f"- {pac.descricao} (a partir de R$ {pac.preco_base:.2f})"
            )
    else:
        linhas.append("- Em breve, novas ofertas selecionadas para voce.")

    corpo = "\n".join(linhas)
    return Email(destino="", assunto=assunto, corpo=corpo)


def enviar_confirmacao(
    sender: EmailSender,
    destinatario: str,
    detalhes: DetalhesViagem,
    recomendados: Sequence[PacotePropaganda],
) -> Email:
    """Monta e envia o e-mail de confirmacao via ``sender`` (RF6).

    Retorna o e-mail enviado (com o destinatario preenchido).
    """
    base = montar_email_confirmacao(detalhes, recomendados)
    sender.enviar(destino=destinatario, assunto=base.assunto, corpo=base.corpo)
    return Email(destino=destinatario, assunto=base.assunto, corpo=base.corpo)


# Sender padrao do processo: stub em memoria enquanto nao ha provedor real.
default_email_sender: EmailSender = StubEmailSender()
