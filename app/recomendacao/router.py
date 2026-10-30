"""Rotas HTTP do AIV: orcamento (RF4) e recomendacao (RF7).

Endpoints:
  POST /recomendacao/orcamento   - estima o custo total de um pacote (RF4)
  POST /recomendacao/ranking     - ranqueia pacotes por preferencia (RF7)

As rotas operam sobre dados enviados no corpo da requisicao e delegam a
heuristica deterministica em ``service.py`` (funcoes puras). Nao dependem de
banco de dados, de modo que o AIV pode ser demonstrado isoladamente.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.recomendacao.schemas import (
    PacoteParaRecomendacao,
    Preferencia,
)
from app.recomendacao.service import estimar_orcamento, recomendar

router = APIRouter(prefix="/recomendacao", tags=["recomendacao"])


class OrcamentoRequest(BaseModel):
    """Entrada da estimativa de orcamento por IA (RF4)."""

    preco_base: float = Field(ge=0)
    dias: Optional[int] = None
    regime_alimentacao: Optional[str] = None
    nivel: Optional[str] = None
    numero_pessoas: int = Field(default=1, ge=1)
    alta_temporada: bool = False


class OrcamentoResposta(BaseModel):
    """Resposta da estimativa de orcamento (RF4)."""

    total_estimado: float


class PreferenciaIn(BaseModel):
    """Preferencias do turista para a recomendacao (RF7)."""

    tipo_viagem: Optional[str] = None
    nivel: Optional[str] = None
    orcamento_max: Optional[float] = None
    estacao_preferida: Optional[str] = None


class PacoteIn(BaseModel):
    """Pacote candidato a recomendacao (RF7)."""

    id_pacote: int
    preco_base: float
    tipo_viagem: Optional[str] = None
    nivel: Optional[str] = None
    score_avaliacoes: Optional[float] = None
    total_avaliacoes: int = 0


class RankingRequest(BaseModel):
    """Entrada do ranking de recomendacao (RF7)."""

    preferencia: PreferenciaIn
    pacotes: List[PacoteIn]
    limite: Optional[int] = None


class ItemRankingResposta(BaseModel):
    """Item do ranking retornado (RF7)."""

    id_pacote: int
    score: float
    dentro_do_orcamento: bool


@router.post("/orcamento", response_model=OrcamentoResposta)
def orcamento(dados: OrcamentoRequest) -> OrcamentoResposta:
    """Estima o custo total de um pacote de forma deterministica (RF4)."""
    total = estimar_orcamento(
        dados.preco_base,
        dias=dados.dias,
        regime_alimentacao=dados.regime_alimentacao,
        nivel=dados.nivel,
        numero_pessoas=dados.numero_pessoas,
        alta_temporada=dados.alta_temporada,
    )
    return OrcamentoResposta(total_estimado=total)


@router.post("/ranking", response_model=List[ItemRankingResposta])
def ranking(dados: RankingRequest) -> List[ItemRankingResposta]:
    """Ranqueia pacotes conforme preferencias e avaliacoes (RF7)."""
    preferencia = Preferencia(
        tipo_viagem=dados.preferencia.tipo_viagem,
        nivel=dados.preferencia.nivel,
        orcamento_max=dados.preferencia.orcamento_max,
        estacao_preferida=dados.preferencia.estacao_preferida,
    )
    pacotes = [
        PacoteParaRecomendacao(
            id_pacote=p.id_pacote,
            preco_base=p.preco_base,
            tipo_viagem=p.tipo_viagem,
            nivel=p.nivel,
            score_avaliacoes=p.score_avaliacoes,
            total_avaliacoes=p.total_avaliacoes,
        )
        for p in dados.pacotes
    ]
    itens = recomendar(pacotes, preferencia, limite=dados.limite)
    return [
        ItemRankingResposta(
            id_pacote=it.id_pacote,
            score=it.score,
            dentro_do_orcamento=it.dentro_do_orcamento,
        )
        for it in itens
    ]
