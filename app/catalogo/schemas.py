"""Modelos Pydantic do modulo de catalogo (RF3) e visualizacao (RF9).

Os campos espelham a tabela ``dbo.Pacote`` (id_pacote, preco_base, data_inicio,
data_fim, estoque, tipo_viagem, nivel) e ``dbo.Destino`` (cidade, estado, pais).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


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


# ---------------------------------------------------------------------------
# Gerenciar Catalogo (admin, secao 4.1): CRUD de Pacote e Destino.
# Os campos espelham exatamente as colunas de dbo.Pacote e dbo.Destino.
# ---------------------------------------------------------------------------


class PacoteCriar(BaseModel):
    """Dados de entrada para criar um pacote (Gerenciar Catalogo, secao 4.1)."""

    preco_base: float = Field(gt=0)
    data_inicio: date
    data_fim: date
    estoque: int = Field(ge=0)
    tipo_viagem: Optional[str] = Field(default=None, max_length=50)
    nivel: Optional[str] = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def _validar_periodo(self) -> "PacoteCriar":
        if self.data_fim < self.data_inicio:
            raise ValueError("data_fim deve ser maior ou igual a data_inicio.")
        return self


class PacoteAtualizar(PacoteCriar):
    """Dados de entrada para atualizar um pacote (substituicao completa)."""


class DestinoCriar(BaseModel):
    """Dados de entrada para criar um destino (Gerenciar Catalogo, secao 4.1)."""

    cidade: str = Field(min_length=1, max_length=100)
    estado: str = Field(min_length=1, max_length=50)
    pais: str = Field(min_length=1, max_length=50)
    categoria: Optional[str] = Field(default=None, max_length=50)
    descricao: Optional[str] = None


class DestinoAtualizar(DestinoCriar):
    """Dados de entrada para atualizar um destino (substituicao completa)."""


class DestinoSaida(BaseModel):
    """Representacao de um destino do catalogo (dbo.Destino)."""

    id_destino: int
    cidade: str
    estado: str
    pais: str
    categoria: Optional[str] = None
    descricao: Optional[str] = None


# ---------------------------------------------------------------------------
# Agendar Viagem (admin, secao 4.1): CRUD de Viagem vinculada a um Destino.
# Os campos espelham exatamente as colunas de dbo.Viagem.
# ---------------------------------------------------------------------------


class ViagemCriar(BaseModel):
    """Dados de entrada para agendar uma viagem (Agendar Viagem, secao 4.1)."""

    data_partida: datetime
    data_chegada: datetime
    meio_transporte: str = Field(min_length=1, max_length=50)
    duracao: Optional[str] = Field(default=None, max_length=30)
    fk_Destino_id_destino: int

    @model_validator(mode="after")
    def _validar_periodo(self) -> "ViagemCriar":
        if self.data_chegada < self.data_partida:
            raise ValueError(
                "data_chegada deve ser maior ou igual a data_partida."
            )
        return self


class ViagemSaida(BaseModel):
    """Representacao de uma viagem agendada (dbo.Viagem)."""

    id_viagem: int
    data_partida: datetime
    data_chegada: datetime
    meio_transporte: str
    duracao: Optional[str] = None
    fk_Destino_id_destino: int
