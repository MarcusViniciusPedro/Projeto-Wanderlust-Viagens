"""Logica de busca de pacotes (RF3) como funcao pura e testavel.

A filtragem opera sobre uma lista de ``PacoteSaida`` ja carregada (por exemplo,
pela camada de banco em ``repository.py``), de modo que a regra de negocio pode
ser exercitada sem um SQL Server vivo. Os criterios espelham os filtros do
documento: tipo de viagem, nivel e janela de datas (data_inicio/data_fim).
"""

from __future__ import annotations

from datetime import date
from typing import Iterable, List, Optional

from app.catalogo.schemas import PacoteSaida


def _casa_texto(valor_pacote: Optional[str], filtro: Optional[str]) -> bool:
    """Comparacao de texto tolerante a caixa/espacos; filtro vazio = qualquer."""
    if not filtro:
        return True
    if valor_pacote is None:
        return False
    return valor_pacote.strip().casefold() == filtro.strip().casefold()


def _dentro_da_janela(
    pacote: PacoteSaida,
    data_inicio: Optional[date],
    data_fim: Optional[date],
) -> bool:
    """Verifica se o pacote cabe na janela de datas solicitada.

    - ``data_inicio`` (piso): o pacote so entra se iniciar em ou apos essa data.
    - ``data_fim`` (teto): o pacote so entra se terminar em ou antes dessa data.
    Ambos opcionais e independentes.
    """
    if data_inicio is not None and pacote.data_inicio < data_inicio:
        return False
    if data_fim is not None and pacote.data_fim > data_fim:
        return False
    return True


def filtrar_pacotes(
    pacotes: Iterable[PacoteSaida],
    *,
    tipo_viagem: Optional[str] = None,
    nivel: Optional[str] = None,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    somente_disponiveis: bool = True,
) -> List[PacoteSaida]:
    """Filtra pacotes por tipo, nivel e janela de datas (RF3).

    Quando ``somente_disponiveis`` e True, pacotes com estoque <= 0 sao
    descartados. Retorna uma lista ordenada por preco_base (crescente) e, em
    empate, por data_inicio, para um resultado estavel/deterministico.
    """
    selecionados = [
        p
        for p in pacotes
        if _casa_texto(p.tipo_viagem, tipo_viagem)
        and _casa_texto(p.nivel, nivel)
        and _dentro_da_janela(p, data_inicio, data_fim)
        and (not somente_disponiveis or p.estoque > 0)
    ]
    selecionados.sort(key=lambda p: (p.preco_base, p.data_inicio))
    return selecionados
