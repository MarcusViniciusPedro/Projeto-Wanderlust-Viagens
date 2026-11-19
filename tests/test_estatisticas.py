"""Testes da agregacao mensal de turistas por destino (RF10)."""

from __future__ import annotations

import pytest

from app.estatisticas.service import (
    EventoTuristaDestino,
    agregar_turistas_por_mes,
    total_por_destino,
)


def test_agregacao_produz_12_meses_por_destino() -> None:
    eventos = [
        EventoTuristaDestino(destino="Paris", mes=1, quantidade=3),
        EventoTuristaDestino(destino="Paris", mes=12, quantidade=2),
        EventoTuristaDestino(destino="Toquio", mes=6, quantidade=5),
    ]
    agregado = agregar_turistas_por_mes(eventos)

    assert set(agregado.keys()) == {"Paris", "Toquio"}
    assert len(agregado["Paris"]) == 12
    assert agregado["Paris"][0] == 3  # janeiro
    assert agregado["Paris"][11] == 2  # dezembro
    assert agregado["Toquio"][5] == 5  # junho


def test_agregacao_soma_eventos_no_mesmo_mes() -> None:
    eventos = [
        EventoTuristaDestino(destino="Roma", mes=3, quantidade=1),
        EventoTuristaDestino(destino="Roma", mes=3, quantidade=4),
    ]
    agregado = agregar_turistas_por_mes(eventos)
    assert agregado["Roma"][2] == 5


def test_total_por_destino() -> None:
    eventos = [
        EventoTuristaDestino(destino="Lisboa", mes=1, quantidade=2),
        EventoTuristaDestino(destino="Lisboa", mes=7, quantidade=3),
    ]
    agregado = agregar_turistas_por_mes(eventos)
    assert total_por_destino(agregado) == {"Lisboa": 5}


def test_mes_invalido_levanta_erro() -> None:
    with pytest.raises(ValueError):
        agregar_turistas_por_mes([EventoTuristaDestino(destino="X", mes=0)])
    with pytest.raises(ValueError):
        agregar_turistas_por_mes([EventoTuristaDestino(destino="X", mes=13)])


def test_ordem_de_destinos_e_estavel() -> None:
    eventos = [
        EventoTuristaDestino(destino="Z", mes=1),
        EventoTuristaDestino(destino="A", mes=1),
    ]
    agregado = agregar_turistas_por_mes(eventos)
    assert list(agregado.keys()) == ["Z", "A"]
