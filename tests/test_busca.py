"""Testes da busca de pacotes por tipo/nivel/data (RF3)."""

from __future__ import annotations

from datetime import date

from app.catalogo.schemas import PacoteSaida
from app.catalogo.service import filtrar_pacotes


def _pacotes() -> list[PacoteSaida]:
    return [
        PacoteSaida(
            id_pacote=1,
            preco_base=1000.0,
            data_inicio=date(2025, 1, 10),
            data_fim=date(2025, 1, 17),
            estoque=5,
            tipo_viagem="Praia",
            nivel="Economico",
        ),
        PacoteSaida(
            id_pacote=2,
            preco_base=2500.0,
            data_inicio=date(2025, 3, 1),
            data_fim=date(2025, 3, 10),
            estoque=0,  # esgotado
            tipo_viagem="Praia",
            nivel="Luxo",
        ),
        PacoteSaida(
            id_pacote=3,
            preco_base=1800.0,
            data_inicio=date(2025, 7, 1),
            data_fim=date(2025, 7, 15),
            estoque=2,
            tipo_viagem="Aventura",
            nivel="Conforto",
        ),
        PacoteSaida(
            id_pacote=4,
            preco_base=900.0,
            data_inicio=date(2025, 1, 20),
            data_fim=date(2025, 1, 25),
            estoque=3,
            tipo_viagem="Praia",
            nivel="Economico",
        ),
    ]


def test_filtro_por_tipo_viagem() -> None:
    res = filtrar_pacotes(_pacotes(), tipo_viagem="Praia")
    ids = {p.id_pacote for p in res}
    # pacote 2 (Praia) esta esgotado e e descartado por somente_disponiveis
    assert ids == {1, 4}


def test_filtro_por_nivel() -> None:
    res = filtrar_pacotes(_pacotes(), nivel="Conforto")
    assert [p.id_pacote for p in res] == [3]


def test_filtro_case_insensitive() -> None:
    res = filtrar_pacotes(_pacotes(), tipo_viagem="praia", nivel="economico")
    assert {p.id_pacote for p in res} == {1, 4}


def test_filtro_por_janela_de_datas() -> None:
    res = filtrar_pacotes(
        _pacotes(),
        data_inicio=date(2025, 1, 1),
        data_fim=date(2025, 1, 31),
    )
    # Apenas pacotes que iniciam e terminam dentro de janeiro e com estoque.
    assert {p.id_pacote for p in res} == {1, 4}


def test_incluir_esgotados_quando_pedido() -> None:
    res = filtrar_pacotes(
        _pacotes(), tipo_viagem="Praia", somente_disponiveis=False
    )
    assert {p.id_pacote for p in res} == {1, 2, 4}


def test_resultado_ordenado_por_preco() -> None:
    res = filtrar_pacotes(_pacotes(), tipo_viagem="Praia")
    precos = [p.preco_base for p in res]
    assert precos == sorted(precos)
