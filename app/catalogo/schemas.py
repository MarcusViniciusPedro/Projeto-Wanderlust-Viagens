"""Modelos Pydantic do modulo de catalogo (RF3) e visualizacao (RF9).

Os campos espelham a tabela ``dbo.Pacote`` (id_pacote, preco_base, data_inicio,
data_fim, estoque, tipo_viagem, nivel) e ``dbo.Destino`` (cidade, estado, pais).
"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


class PacoteSaida(BaseModel):
    """Representacao publica de um pacote de viagem (RF3)."""

    id_pacote: int
    preco_base: float
    data_inicio: date
    data_fim: date
    estoque: int
    tipo_viagem: Optional[str] = None
    nivel: Optional[str] = None


class FiltroBusca(BaseModel):
    """Filtros de busca de pacotes (RF3): tipo, nivel e janela de datas."""

    tipo_viagem: Optional[str] = Field(default=None, max_length=50)
    nivel: Optional[str] = Field(default=None, max_length=50)
    data_inicio: Optional[date] = None
    data_fim: Optional[date] = None
    somente_disponiveis: bool = True


class ResultadoBusca(BaseModel):
    """Resposta da busca de pacotes."""

    total: int
    pacotes: List[PacoteSaida]


class StreetViewSaida(BaseModel):
    """Resposta da visualizacao 3D/Street View de um destino (RF9)."""

    id_destino: Optional[int] = None
    local: str
    url: str
    embed_html: str
