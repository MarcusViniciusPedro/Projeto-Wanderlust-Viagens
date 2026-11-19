"""Testes do e-mail de confirmacao + propaganda (RF6)."""

from __future__ import annotations

from app.integracoes.email import (
    DetalhesViagem,
    PacotePropaganda,
    StubEmailSender,
    enviar_confirmacao,
    montar_email_confirmacao,
)


def _detalhes() -> DetalhesViagem:
    return DetalhesViagem(
        id_venda=42,
        destino="Rio de Janeiro",
        data_inicio="2025-01-10",
        data_fim="2025-01-17",
        valor_total=3500.0,
        tipo_viagem="Praia",
        nivel="Conforto",
    )


def _recomendados() -> list[PacotePropaganda]:
    return [
        PacotePropaganda(id_pacote=2, descricao="Pacote Salvador", preco_base=2800.0),
        PacotePropaganda(id_pacote=3, descricao="Pacote Fortaleza", preco_base=2600.0),
    ]


def test_conteudo_inclui_detalhes_da_viagem() -> None:
    email = montar_email_confirmacao(_detalhes(), _recomendados())
    assert "Rio de Janeiro" in email.assunto
    assert "#42" in email.corpo
    assert "2025-01-10" in email.corpo
    assert "2025-01-17" in email.corpo
    assert "3500.00" in email.corpo
    assert "Praia" in email.corpo
    assert "Conforto" in email.corpo


def test_conteudo_inclui_propaganda_de_outros_pacotes() -> None:
    email = montar_email_confirmacao(_detalhes(), _recomendados())
    assert "recomendacoes" in email.corpo.lower()
    assert "Pacote Salvador" in email.corpo
    assert "Pacote Fortaleza" in email.corpo
    assert "2800.00" in email.corpo


def test_propaganda_vazia_tem_mensagem_padrao() -> None:
    email = montar_email_confirmacao(_detalhes(), [])
    assert "novas ofertas" in email.corpo.lower()


def test_enviar_confirmacao_usa_o_stub() -> None:
    sender = StubEmailSender()
    enviado = enviar_confirmacao(
        sender, "turista@example.com", _detalhes(), _recomendados()
    )
    assert sender.ultimo is not None
    assert sender.ultimo.destino == "turista@example.com"
    assert sender.ultimo.assunto == enviado.assunto
    assert "Pacote Salvador" in sender.ultimo.corpo
