"""Testes da estimativa de orcamento por IA (RF4): determinismo e limites."""

from __future__ import annotations

import pytest

from app.recomendacao.service import (
    FATOR_ALTA_TEMPORADA,
    FATOR_POR_DIA_EXTRA,
    FATORES_NIVEL,
    FATORES_REGIME,
    estimar_orcamento,
)


def test_orcamento_minimo_e_preco_base() -> None:
    # Sem fatores e 1 pessoa, o total e exatamente o preco_base.
    assert estimar_orcamento(1000.0) == 1000.0


def test_orcamento_e_deterministico() -> None:
    a = estimar_orcamento(
        1000.0, dias=5, regime_alimentacao="meia_pensao", nivel="conforto"
    )
    b = estimar_orcamento(
        1000.0, dias=5, regime_alimentacao="meia_pensao", nivel="conforto"
    )
    assert a == b


def test_orcamento_aplica_fatores_multiplicativos() -> None:
    preco = 1000.0
    dias = 5
    esperado = preco
    esperado *= 1.0 + (dias - 1) * FATOR_POR_DIA_EXTRA
    esperado *= FATORES_REGIME["pensao_completa"]
    esperado *= FATORES_NIVEL["luxo"]
    esperado *= FATOR_ALTA_TEMPORADA
    esperado *= 2  # numero_pessoas
    esperado = round(esperado, 2)

    obtido = estimar_orcamento(
        preco,
        dias=dias,
        regime_alimentacao="pensao_completa",
        nivel="luxo",
        numero_pessoas=2,
        alta_temporada=True,
    )
    assert obtido == esperado


def test_mais_pessoas_aumenta_total() -> None:
    um = estimar_orcamento(1000.0, numero_pessoas=1)
    tres = estimar_orcamento(1000.0, numero_pessoas=3)
    assert tres == pytest.approx(um * 3)


def test_regime_desconhecido_e_neutro() -> None:
    assert estimar_orcamento(1000.0, regime_alimentacao="inexistente") == 1000.0


def test_valores_invalidos_levantam_erro() -> None:
    with pytest.raises(ValueError):
        estimar_orcamento(-1.0)
    with pytest.raises(ValueError):
        estimar_orcamento(1000.0, numero_pessoas=0)
