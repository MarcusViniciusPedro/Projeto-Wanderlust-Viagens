"""Testes do AIV: ranking por preferencia (RF7) e feedback agregado (RF8)."""

from __future__ import annotations

from app.recomendacao.schemas import (
    Avaliacao,
    PacoteParaRecomendacao,
    Preferencia,
)
from app.recomendacao.service import agregar_feedback, recomendar


def test_ranking_prioriza_aderencia_as_preferencias() -> None:
    preferencia = Preferencia(
        tipo_viagem="Praia", nivel="Luxo", orcamento_max=5000.0
    )
    pacotes = [
        # Casa tipo+nivel e dentro do orcamento -> deve ser o 1o.
        PacoteParaRecomendacao(
            id_pacote=1, preco_base=4000.0, tipo_viagem="Praia", nivel="Luxo"
        ),
        # Casa apenas tipo.
        PacoteParaRecomendacao(
            id_pacote=2, preco_base=3000.0, tipo_viagem="Praia", nivel="Economico"
        ),
        # Nao casa nada e acima do orcamento.
        PacoteParaRecomendacao(
            id_pacote=3, preco_base=9000.0, tipo_viagem="Aventura", nivel="Conforto"
        ),
    ]
    ranking = recomendar(pacotes, preferencia)
    assert [it.id_pacote for it in ranking] == [1, 2, 3]
    assert ranking[0].score > ranking[1].score > ranking[2].score


def test_ranking_penaliza_fora_do_orcamento() -> None:
    preferencia = Preferencia(tipo_viagem="Praia", nivel="Luxo", orcamento_max=1000.0)
    dentro = PacoteParaRecomendacao(
        id_pacote=1, preco_base=900.0, tipo_viagem="Praia", nivel="Luxo"
    )
    fora = PacoteParaRecomendacao(
        id_pacote=2, preco_base=5000.0, tipo_viagem="Praia", nivel="Luxo"
    )
    ranking = recomendar([fora, dentro], preferencia)
    assert ranking[0].id_pacote == 1
    assert ranking[0].dentro_do_orcamento is True
    assert ranking[1].dentro_do_orcamento is False


def test_ranking_usa_avaliacoes_como_desempate() -> None:
    preferencia = Preferencia(tipo_viagem="Praia", nivel="Luxo", orcamento_max=5000.0)
    bem_avaliado = PacoteParaRecomendacao(
        id_pacote=1,
        preco_base=3000.0,
        tipo_viagem="Praia",
        nivel="Luxo",
        score_avaliacoes=5.0,
        total_avaliacoes=10,
    )
    mal_avaliado = PacoteParaRecomendacao(
        id_pacote=2,
        preco_base=3000.0,
        tipo_viagem="Praia",
        nivel="Luxo",
        score_avaliacoes=1.0,
        total_avaliacoes=10,
    )
    ranking = recomendar([mal_avaliado, bem_avaliado], preferencia)
    assert ranking[0].id_pacote == 1


def test_ranking_e_estavel_por_id_em_empate() -> None:
    preferencia = Preferencia()
    a = PacoteParaRecomendacao(id_pacote=5, preco_base=100.0)
    b = PacoteParaRecomendacao(id_pacote=2, preco_base=100.0)
    ranking = recomendar([a, b], preferencia)
    assert [it.id_pacote for it in ranking] == [2, 5]


def test_feedback_agrega_media_e_resumo() -> None:
    avaliacoes = [Avaliacao(nota=5), Avaliacao(nota=4), Avaliacao(nota=3)]
    fb = agregar_feedback(fk_pacote=1, avaliacoes=avaliacoes)
    assert fb.fk_pacote == 1
    assert fb.score_agregado == 4.0
    assert fb.total_avaliacoes == 3
    assert "4.00" in fb.resumo
    assert "3 avaliacoes" in fb.resumo


def test_feedback_sem_avaliacoes() -> None:
    fb = agregar_feedback(fk_pacote=7, avaliacoes=[])
    assert fb.score_agregado is None
    assert fb.total_avaliacoes == 0
    assert "Sem avaliacoes" in fb.resumo


def test_feedback_classifica_excelente_vs_fraco() -> None:
    excelente = agregar_feedback(1, [Avaliacao(nota=5), Avaliacao(nota=5)])
    fraco = agregar_feedback(2, [Avaliacao(nota=1), Avaliacao(nota=2)])
    assert "Excelente" in excelente.resumo
    assert "Fraco" in fraco.resumo
