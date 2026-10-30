"""AIV - Assistente Inteligente de Viagens (heuristica deterministica).

Este modulo concentra as tres funcoes de inteligencia do sistema, todas
PURAS e TESTAVEIS (sem modelo de ML externo, sem banco, sem rede):

  RF4 - estimar_orcamento: estima o custo total de um pacote a partir do
        preco_base e de fatores multiplicativos (duracao, hospedagem/regime,
        numero de pessoas, temporada).

  RF7 - recomendar: ranqueia pacotes por um score ponderado que combina a
        aderencia as preferencias do turista (tipo/nivel/orcamento) com o
        historico de avaliacoes (IA_Feedback).

  RF8 - agregar_feedback: agrega as avaliacoes de um pacote em um score (0..5)
        e um resumo textual deterministico (insumo da tabela IA_Feedback).

Os pesos e heuristicas estao documentados em constantes e comentarios abaixo,
de forma que o comportamento seja transparente e reproduzivel.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from app.recomendacao.schemas import (
    Avaliacao,
    FeedbackAgregado,
    ItemRecomendado,
    PacoteParaRecomendacao,
    Preferencia,
)

# =====================================================================
# RF4 - Orcamento por IA
# ---------------------------------------------------------------------
# A estimativa parte do preco_base e aplica fatores multiplicativos
# deterministicos. Todos os fatores tem valor neutro (1.0) quando o
# insumo correspondente nao e informado, garantindo que a estimativa
# minima seja exatamente o preco_base * numero de pessoas.
# =====================================================================

# Acrescimo por dia de viagem alem do primeiro (duracao). Ex.: 3% ao dia.
FATOR_POR_DIA_EXTRA = 0.03

# Fatores por regime de alimentacao da hospedagem (quanto mais completo, maior).
FATORES_REGIME: Dict[str, float] = {
    "sem_refeicao": 1.00,
    "cafe_da_manha": 1.08,
    "meia_pensao": 1.18,
    "pensao_completa": 1.28,
    "all_inclusive": 1.40,
}

# Fatores por nivel de hospedagem/pacote (conforto proporciona preco maior).
FATORES_NIVEL: Dict[str, float] = {
    "economico": 1.00,
    "conforto": 1.25,
    "luxo": 1.60,
}

# Acrescimo de alta temporada quando a estacao do pacote coincide com a
# estacao preferida do turista (demanda maior => preco maior).
FATOR_ALTA_TEMPORADA = 1.15


def _fator_duracao(dias: Optional[int]) -> float:
    """Fator multiplicativo pela duracao (em dias) da viagem."""
    if not dias or dias <= 1:
        return 1.0
    return 1.0 + (dias - 1) * FATOR_POR_DIA_EXTRA


def _fator_regime(regime: Optional[str]) -> float:
    """Fator multiplicativo pelo regime de alimentacao da hospedagem."""
    if not regime:
        return 1.0
    return FATORES_REGIME.get(regime.strip().casefold(), 1.0)


def _fator_nivel(nivel: Optional[str]) -> float:
    """Fator multiplicativo pelo nivel de conforto do pacote/hospedagem."""
    if not nivel:
        return 1.0
    return FATORES_NIVEL.get(nivel.strip().casefold(), 1.0)


def estimar_orcamento(
    preco_base: float,
    *,
    dias: Optional[int] = None,
    regime_alimentacao: Optional[str] = None,
    nivel: Optional[str] = None,
    numero_pessoas: int = 1,
    alta_temporada: bool = False,
) -> float:
    """Estima o custo total de um pacote (RF4), de forma deterministica.

    Formula:
        total = preco_base
                * fator_duracao(dias)
                * fator_regime(regime_alimentacao)
                * fator_nivel(nivel)
                * (fator_alta_temporada se alta_temporada senao 1.0)
                * numero_pessoas

    Com todos os insumos neutros e numero_pessoas=1, o total e exatamente o
    preco_base. O resultado e arredondado em 2 casas (centavos).
    """
    if preco_base < 0:
        raise ValueError("preco_base nao pode ser negativo.")
    if numero_pessoas < 1:
        raise ValueError("numero_pessoas deve ser >= 1.")

    total = preco_base
    total *= _fator_duracao(dias)
    total *= _fator_regime(regime_alimentacao)
    total *= _fator_nivel(nivel)
    if alta_temporada:
        total *= FATOR_ALTA_TEMPORADA
    total *= numero_pessoas
    return round(total, 2)


# =====================================================================
# RF7 - Recomendacao (scoring ponderado)
# ---------------------------------------------------------------------
# O score final de cada pacote (0..1 antes de normalizar os pesos) e a
# soma ponderada de quatro componentes. Os pesos somam 1.0:
#   - PESO_TIPO    : aderencia do tipo_viagem a preferencia.
#   - PESO_NIVEL   : aderencia do nivel a preferencia.
#   - PESO_ORCAMENTO: pacote dentro do orcamento_max do turista.
#   - PESO_AVALIACOES: reputacao (score_avaliacoes normalizado de 0..5 -> 0..1).
# Pacotes fora do orcamento NAO sao descartados, apenas penalizados, para
# ainda oferecerem alternativas; o ranking e estavel (desempate por id).
# =====================================================================

PESO_TIPO = 0.35
PESO_NIVEL = 0.20
PESO_ORCAMENTO = 0.25
PESO_AVALIACOES = 0.20

# Peso de confianca: avaliacoes com pouca amostra contam menos. A confianca
# satura ao atingir este numero de avaliacoes.
AVALIACOES_PARA_CONFIANCA_PLENA = 10


def _igual(a: Optional[str], b: Optional[str]) -> bool:
    """Igualdade textual tolerante a caixa/espacos."""
    if a is None or b is None:
        return False
    return a.strip().casefold() == b.strip().casefold()


def _componente_avaliacoes(pacote: PacoteParaRecomendacao) -> float:
    """Reputacao normalizada (0..1) ponderada pela confianca da amostra."""
    if pacote.score_avaliacoes is None or pacote.total_avaliacoes <= 0:
        # Sem avaliacoes: neutro (0.5) para nao punir pacotes novos.
        return 0.5
    base = max(0.0, min(pacote.score_avaliacoes, 5.0)) / 5.0
    confianca = min(pacote.total_avaliacoes, AVALIACOES_PARA_CONFIANCA_PLENA) / (
        AVALIACOES_PARA_CONFIANCA_PLENA
    )
    # Interpola entre neutro (0.5) e a reputacao real conforme a confianca.
    return 0.5 + (base - 0.5) * confianca


def pontuar_pacote(
    pacote: PacoteParaRecomendacao, preferencia: Preferencia
) -> ItemRecomendado:
    """Calcula o score ponderado de um pacote para um turista (RF7)."""
    comp_tipo = 1.0 if _igual(pacote.tipo_viagem, preferencia.tipo_viagem) else 0.0
    comp_nivel = 1.0 if _igual(pacote.nivel, preferencia.nivel) else 0.0

    dentro_orcamento = (
        preferencia.orcamento_max is None
        or pacote.preco_base <= preferencia.orcamento_max
    )
    comp_orcamento = 1.0 if dentro_orcamento else 0.0

    comp_aval = _componente_avaliacoes(pacote)

    score = (
        PESO_TIPO * comp_tipo
        + PESO_NIVEL * comp_nivel
        + PESO_ORCAMENTO * comp_orcamento
        + PESO_AVALIACOES * comp_aval
    )
    componentes = {
        "tipo": round(PESO_TIPO * comp_tipo, 4),
        "nivel": round(PESO_NIVEL * comp_nivel, 4),
        "orcamento": round(PESO_ORCAMENTO * comp_orcamento, 4),
        "avaliacoes": round(PESO_AVALIACOES * comp_aval, 4),
    }
    return ItemRecomendado(
        id_pacote=pacote.id_pacote,
        score=round(score, 4),
        dentro_do_orcamento=dentro_orcamento,
        componentes=componentes,
    )


def recomendar(
    pacotes: Iterable[PacoteParaRecomendacao],
    preferencia: Preferencia,
    *,
    limite: Optional[int] = None,
) -> List[ItemRecomendado]:
    """Ranqueia pacotes por aderencia as preferencias/avaliacoes (RF7).

    Retorna a lista ordenada por score decrescente; empates sao resolvidos
    pelo id_pacote (crescente) para um resultado estavel/deterministico.
    """
    itens = [pontuar_pacote(p, preferencia) for p in pacotes]
    itens.sort(key=lambda it: (-it.score, it.id_pacote))
    if limite is not None:
        itens = itens[:limite]
    return itens


# =====================================================================
# RF8 - Feedback agregado por IA
# ---------------------------------------------------------------------
# Agrega as avaliacoes de um pacote em um score medio (0..5) e um resumo
# textual deterministico. O resumo classifica o pacote em faixas fixas de
# score, de modo que a mesma entrada sempre produz o mesmo texto.
# =====================================================================

FAIXAS_RESUMO = (
    (4.5, "Excelente: avaliacoes muito positivas"),
    (4.0, "Muito bom: avaliacoes positivas"),
    (3.0, "Bom: avaliacoes satisfatorias"),
    (2.0, "Regular: avaliacoes mistas"),
    (0.0, "Fraco: avaliacoes majoritariamente negativas"),
)


def _classificar(score: float) -> str:
    """Retorna o rotulo textual deterministico para um score (0..5)."""
    for piso, rotulo in FAIXAS_RESUMO:
        if score >= piso:
            return rotulo
    return FAIXAS_RESUMO[-1][1]


def agregar_feedback(
    fk_pacote: int, avaliacoes: Iterable[Avaliacao]
) -> FeedbackAgregado:
    """Agrega avaliacoes de um pacote em score + resumo textual (RF8).

    Sem avaliacoes, o score e None e o resumo indica a ausencia de dados. Com
    avaliacoes, o score e a media aritmetica das notas (0..5) arredondada em 2
    casas, e o resumo combina a classificacao com a contagem de avaliacoes.
    """
    notas = [a.nota for a in avaliacoes]
    total = len(notas)
    if total == 0:
        return FeedbackAgregado(
            fk_pacote=fk_pacote,
            score_agregado=None,
            total_avaliacoes=0,
            resumo="Sem avaliacoes ainda.",
        )

    score = round(sum(notas) / total, 2)
    rotulo = _classificar(score)
    plural = "avaliacao" if total == 1 else "avaliacoes"
    resumo = f"{rotulo} (media {score:.2f} em {total} {plural})."
    return FeedbackAgregado(
        fk_pacote=fk_pacote,
        score_agregado=score,
        total_avaliacoes=total,
        resumo=resumo,
    )
