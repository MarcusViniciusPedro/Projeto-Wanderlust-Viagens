"""Estatisticas de incidencia de turistas por destino ao longo do ano (RF10).

A agregacao e uma funcao PURA e testavel: recebe eventos (destino, mes) e
produz uma estrutura pronta para grafico, no formato
``{destino: [12 contagens]}`` (indice 0 = janeiro ... indice 11 = dezembro).

Conceitualmente alinhada a VIEW ``vw_turistas_por_destino_ano`` criada no SQL
(FEAT-002), que liga Venda -> Passagem -> Viagem -> Destino e agrupa por ano.
Aqui a granularidade e mensal, para alimentar um grafico anual por destino.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List

MESES_NO_ANO = 12


@dataclass(frozen=True)
class EventoTuristaDestino:
    """Um turista registrado em um destino, em um mes (1..12) de um ano."""

    destino: str
    mes: int
    quantidade: int = 1


def agregar_turistas_por_mes(
    eventos: Iterable[EventoTuristaDestino],
) -> Dict[str, List[int]]:
    """Agrega a incidencia de turistas por destino em 12 contagens mensais (RF10).

    Retorna ``{destino: [jan, fev, ..., dez]}``. Meses fora da faixa 1..12
    levantam ``ValueError``. Destinos sao mantidos em ordem de primeira
    aparicao para um resultado deterministico.
    """
    resultado: Dict[str, List[int]] = {}
    for evento in eventos:
        if not 1 <= evento.mes <= MESES_NO_ANO:
            raise ValueError(
                f"mes invalido: {evento.mes} (esperado 1..12)."
            )
        contagens = resultado.setdefault(evento.destino, [0] * MESES_NO_ANO)
        contagens[evento.mes - 1] += evento.quantidade
    return resultado


def total_por_destino(
    agregado: Dict[str, List[int]],
) -> Dict[str, int]:
    """Soma anual por destino a partir do agregado mensal (conveniencia)."""
    return {destino: sum(contagens) for destino, contagens in agregado.items()}
