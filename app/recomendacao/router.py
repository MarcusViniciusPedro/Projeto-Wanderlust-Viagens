"""Rotas HTTP do AIV: orcamento (RF4), recomendacao (RF7) e feedback (RF8).

Endpoints sem banco (operam sobre o corpo da requisicao):
  POST /recomendacao/orcamento   - estima o custo total de um pacote (RF4)
  POST /recomendacao/ranking     - ranqueia pacotes por preferencia (RF7)
  POST /recomendacao/feedback    - agrega avaliacoes de um pacote (RF8)

Endpoints DB-backed (coletam/persistem dados que o AIV usa para personalizar):
  GET  /recomendacao/para-mim                    - ranking personalizado do turista
  GET  /recomendacao/preferencias/me             - le a propria Preferencia
  PUT  /recomendacao/preferencias/me             - grava a propria Preferencia
  POST /recomendacao/avaliacoes                  - envia a propria Avaliacao
  GET  /recomendacao/pacotes/{fk_pacote}/feedback - agrega avaliacoes persistidas

As rotas sem banco delegam a heuristica deterministica em ``service.py``
(funcoes puras). As rotas DB-backed coletam os dados no ``repository.py`` e
reutilizam o MESMO service puro (sem duplicar a heuristica). Sem banco
configurado, elas degradam para HTTP 503. As rotas protegidas usam
``requer_autenticacao`` e operam SEMPRE sobre o id do turista do JWT, nunca
sobre um id vindo do corpo/caminho.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.deps import UsuarioAtual, requer_autenticacao
from app.db.session import DatabaseNotConfiguredError
from app.recomendacao import repository
from app.recomendacao.repository import AvaliacaoDuplicadaError
from app.recomendacao.schemas import (
    Avaliacao,
    PacoteParaRecomendacao,
    Preferencia,
)
from app.recomendacao.service import agregar_feedback, estimar_orcamento, recomendar

router = APIRouter(prefix="/recomendacao", tags=["recomendacao"])


def _erro_db_indisponivel() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "Banco de dados nao configurado. Configure as variaveis "
            "WANDERLUST_DB_* para habilitar a persistencia."
        ),
    )


def _id_do_token(usuario_atual: UsuarioAtual) -> int:
    """Extrai o id_turista do JWT ou levanta 401 para tokens sem a claim 'id'.

    Tokens antigos (sem ``id``) nao identificam o turista; sem isso nao da para
    resolver "a propria Preferencia/Avaliacao", entao exigimos novo login.
    """
    if usuario_atual.id_passageiro is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Token sem identificacao do passageiro (claim 'id'). "
                "Faca login novamente."
            ),
        )
    return usuario_atual.id_passageiro


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


class AvaliacaoIn(BaseModel):
    """Avaliacao de um pacote (nota 1..5) para a agregacao de feedback (RF8)."""

    nota: int = Field(ge=1, le=5)
    comentario: Optional[str] = None


class FeedbackRequest(BaseModel):
    """Entrada da agregacao de feedback por IA (RF8)."""

    fk_pacote: int
    avaliacoes: List[AvaliacaoIn] = Field(default_factory=list)


class FeedbackResposta(BaseModel):
    """Resposta da agregacao de feedback (RF8)."""

    fk_pacote: int
    score_agregado: Optional[float]
    total_avaliacoes: int
    resumo: str


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


@router.post("/feedback", response_model=FeedbackResposta)
def feedback(dados: FeedbackRequest) -> FeedbackResposta:
    """Agrega as avaliacoes de um pacote em score + resumo textual (RF8).

    Expoe por HTTP a mesma heuristica deterministica que a trigger
    ``tr_avaliacao_atualiza_ia_feedback`` aplica no banco, dando paridade de
    API com os demais RFs. Nao depende de banco: recebe as avaliacoes no corpo.
    """
    avaliacoes = [
        Avaliacao(nota=a.nota, comentario=a.comentario) for a in dados.avaliacoes
    ]
    resultado = agregar_feedback(dados.fk_pacote, avaliacoes)
    return FeedbackResposta(
        fk_pacote=resultado.fk_pacote,
        score_agregado=resultado.score_agregado,
        total_avaliacoes=resultado.total_avaliacoes,
        resumo=resultado.resumo,
    )


# ---------------------------------------------------------------------------
# AIV DB-backed: recomendacao personalizada para o turista logado (RF7).
# Coleta os pacotes do catalogo (com a reputacao de IA_Feedback) e a
# Preferencia salva do turista e reutiliza o service puro ``recomendar``.
# ---------------------------------------------------------------------------


@router.get("/para-mim", response_model=List[ItemRankingResposta])
def recomendar_para_mim(
    limite: Optional[int] = None,
    usuario_atual: UsuarioAtual = Depends(requer_autenticacao),
) -> List[ItemRankingResposta]:
    """Ranking personalizado para o PROPRIO turista logado (RF7, DB-backed).

    Coleta os pacotes do catalogo (com a reputacao de IA_Feedback) e a
    Preferencia salva do turista do JWT, e delega ao service puro
    ``recomendar`` (sem duplicar a heuristica). Turista sem Preferencia salva
    ainda recebe um ranking: usa-se uma Preferencia vazia, de modo que o score
    passa a depender so da reputacao/orcamento neutro.
    """
    fk_turista = _id_do_token(usuario_atual)
    try:
        preferencia = repository.buscar_preferencia_turista(fk_turista)
        pacotes = repository.listar_pacotes_para_recomendacao()
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    if preferencia is None:
        preferencia = Preferencia()

    itens = recomendar(pacotes, preferencia, limite=limite)
    return [
        ItemRankingResposta(
            id_pacote=it.id_pacote,
            score=it.score,
            dentro_do_orcamento=it.dentro_do_orcamento,
        )
        for it in itens
    ]


# ---------------------------------------------------------------------------
# Preferencia self-service: o turista le/grava a PROPRIA Preferencia.
# fk_turista vem SEMPRE do JWT (nunca do corpo). Como fk_turista e UNIQUE, a
# escrita e um upsert (uma Preferencia por turista).
# ---------------------------------------------------------------------------


class PreferenciaUpsert(BaseModel):
    """Entrada da gravacao da propria Preferencia (nao expoe fk_turista)."""

    tipo_viagem: Optional[str] = None
    nivel: Optional[str] = None
    orcamento_max: Optional[float] = Field(default=None, ge=0)
    estacao_preferida: Optional[str] = None
    observacoes: Optional[str] = None


class PreferenciaSaida(BaseModel):
    """Resposta com a Preferencia do turista."""

    tipo_viagem: Optional[str] = None
    nivel: Optional[str] = None
    orcamento_max: Optional[float] = None
    estacao_preferida: Optional[str] = None


@router.get("/preferencias/me", response_model=PreferenciaSaida)
def ler_preferencia(
    usuario_atual: UsuarioAtual = Depends(requer_autenticacao),
) -> PreferenciaSaida:
    """Le a PROPRIA Preferencia do turista logado (self-service).

    404 quando o turista ainda nao salvou nenhuma Preferencia.
    """
    fk_turista = _id_do_token(usuario_atual)
    try:
        preferencia = repository.buscar_preferencia_turista(fk_turista)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    if preferencia is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Preferencia nao encontrada. Grave suas preferencias primeiro.",
        )
    return PreferenciaSaida(
        tipo_viagem=preferencia.tipo_viagem,
        nivel=preferencia.nivel,
        orcamento_max=preferencia.orcamento_max,
        estacao_preferida=preferencia.estacao_preferida,
    )


@router.put("/preferencias/me", response_model=PreferenciaSaida)
def gravar_preferencia(
    dados: PreferenciaUpsert,
    usuario_atual: UsuarioAtual = Depends(requer_autenticacao),
) -> PreferenciaSaida:
    """Grava a PROPRIA Preferencia do turista logado (upsert, self-service)."""
    fk_turista = _id_do_token(usuario_atual)
    try:
        preferencia = repository.upsert_preferencia(
            fk_turista,
            tipo_viagem=dados.tipo_viagem,
            nivel=dados.nivel,
            orcamento_max=dados.orcamento_max,
            estacao_preferida=dados.estacao_preferida,
            observacoes=dados.observacoes,
        )
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    return PreferenciaSaida(
        tipo_viagem=preferencia.tipo_viagem,
        nivel=preferencia.nivel,
        orcamento_max=preferencia.orcamento_max,
        estacao_preferida=preferencia.estacao_preferida,
    )


# ---------------------------------------------------------------------------
# Avaliacao self-service: o turista envia a PROPRIA Avaliacao e qualquer um
# le o feedback agregado persistido de um pacote (RF8, DB-backed).
# fk_turista vem SEMPRE do JWT; UNIQUE(fk_turista, fk_pacote) => 409 duplicado.
# ---------------------------------------------------------------------------


class AvaliacaoRegistro(BaseModel):
    """Entrada do envio da propria Avaliacao (nao expoe fk_turista)."""

    fk_pacote: int
    nota: int = Field(ge=1, le=5)
    comentario: Optional[str] = None


class AvaliacaoRegistrada(BaseModel):
    """Resposta da Avaliacao registrada."""

    id_avaliacao: int
    fk_pacote: int
    nota: int
    comentario: Optional[str] = None


@router.post(
    "/avaliacoes",
    response_model=AvaliacaoRegistrada,
    status_code=status.HTTP_201_CREATED,
)
def avaliar_pacote(
    dados: AvaliacaoRegistro,
    usuario_atual: UsuarioAtual = Depends(requer_autenticacao),
) -> AvaliacaoRegistrada:
    """Registra a PROPRIA Avaliacao do turista para um pacote (RF8, DB-backed).

    O ``fk_turista`` vem do JWT (nunca do corpo). A restricao
    UNIQUE(fk_turista, fk_pacote) impede avaliacao duplicada: nesse caso a rota
    responde HTTP 409.
    """
    fk_turista = _id_do_token(usuario_atual)
    try:
        id_avaliacao = repository.registrar_avaliacao(
            fk_turista, dados.fk_pacote, dados.nota, dados.comentario
        )
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc
    except AvaliacaoDuplicadaError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

    return AvaliacaoRegistrada(
        id_avaliacao=id_avaliacao,
        fk_pacote=dados.fk_pacote,
        nota=dados.nota,
        comentario=dados.comentario,
    )


@router.get("/pacotes/{fk_pacote}/feedback", response_model=FeedbackResposta)
def feedback_do_pacote(fk_pacote: int) -> FeedbackResposta:
    """Agrega as avaliacoes PERSISTIDAS de um pacote em score + resumo (RF8).

    Complementa o ``POST /recomendacao/feedback`` (que recebe tudo no corpo):
    aqui as avaliacoes vem do banco e sao passadas ao MESMO service puro
    ``agregar_feedback``. 503 sem banco.
    """
    try:
        avaliacoes = repository.listar_avaliacoes_do_pacote(fk_pacote)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    resultado = agregar_feedback(fk_pacote, avaliacoes)
    return FeedbackResposta(
        fk_pacote=resultado.fk_pacote,
        score_agregado=resultado.score_agregado,
        total_avaliacoes=resultado.total_avaliacoes,
        resumo=resultado.resumo,
    )
