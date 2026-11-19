"""Modelos de dados do AIV (Assistente Inteligente de Viagens).

Estruturas puras (dataclasses) usadas pelas heuristicas deterministicas de
orcamento (RF4), recomendacao (RF7) e feedback agregado (RF8). Mantidas
desacopladas de HTTP/banco para permitir testes sem SQL Server.

Os campos espelham o schema do banco:
  - Preferencia(fk_turista, tipo_viagem, nivel, orcamento_max, estacao_preferida)
  - Pacote(id_pacote, preco_base, data_inicio, data_fim, tipo_viagem, nivel)
  - Avaliacao(fk_pacote, nota 1..5, comentario)
  - IA_Feedback(fk_pacote, score_agregado, total_avaliacoes, resumo)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional


@dataclass(frozen=True)
class Preferencia:
    """Perfil de preferencias do turista (consolidado do questionario, RF4)."""

    tipo_viagem: Optional[str] = None
    nivel: Optional[str] = None
    orcamento_max: Optional[float] = None
    estacao_preferida: Optional[str] = None


@dataclass(frozen=True)
class PacoteParaRecomendacao:
    """Dados de um pacote relevantes para orcamento e recomendacao."""

    id_pacote: int
    preco_base: float
    tipo_viagem: Optional[str] = None
    nivel: Optional[str] = None
    data_inicio: Optional[date] = None
    data_fim: Optional[date] = None
    # Insumos do IA_Feedback (RF8); opcionais quando ainda nao ha avaliacoes.
    score_avaliacoes: Optional[float] = None  # 0..5
    total_avaliacoes: int = 0


@dataclass(frozen=True)
class Avaliacao:
    """Avaliacao de um pacote por um turista (nota 1..5), RF8."""

    nota: int
    comentario: Optional[str] = None


@dataclass(frozen=True)
class ItemRecomendado:
    """Pacote pontuado pelo AIV com o detalhamento do score (RF7)."""

    id_pacote: int
    score: float
    dentro_do_orcamento: bool
    componentes: dict = field(default_factory=dict)


@dataclass(frozen=True)
class FeedbackAgregado:
    """Resultado da agregacao de avaliacoes de um pacote (RF8)."""

    fk_pacote: int
    score_agregado: Optional[float]
    total_avaliacoes: int
    resumo: str
