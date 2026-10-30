"""Rotas HTTP do catalogo: busca de pacotes (RF3) e visualizacao 3D (RF9).

Endpoints:
  GET /catalogo/pacotes            - busca de pacotes com filtros (RF3)
  GET /catalogo/destinos/{id}/streetview - URL/embed de Street View (RF9)

A logica de filtragem e de montagem de URL vive em funcoes puras testaveis.
Sem banco configurado, ``DatabaseNotConfiguredError`` vira HTTP 503.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.catalogo import repository
from app.catalogo.schemas import ResultadoBusca, StreetViewSaida
from app.catalogo.service import filtrar_pacotes
from app.db.session import DatabaseNotConfiguredError
from app.integracoes.streetview import (
    montar_embed_html,
    montar_url_streetview,
)

router = APIRouter(prefix="/catalogo", tags=["catalogo"])


def _erro_db_indisponivel() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "Banco de dados nao configurado. Configure as variaveis "
            "WANDERLUST_DB_* para habilitar a persistencia."
        ),
    )


@router.get("/pacotes", response_model=ResultadoBusca)
def buscar_pacotes(
    tipo_viagem: Optional[str] = Query(default=None),
    nivel: Optional[str] = Query(default=None),
    data_inicio: Optional[date] = Query(default=None),
    data_fim: Optional[date] = Query(default=None),
    somente_disponiveis: bool = Query(default=True),
) -> ResultadoBusca:
    """Busca pacotes por tipo, nivel e janela de datas (RF3)."""
    try:
        pacotes = repository.listar_pacotes()
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    filtrados = filtrar_pacotes(
        pacotes,
        tipo_viagem=tipo_viagem,
        nivel=nivel,
        data_inicio=data_inicio,
        data_fim=data_fim,
        somente_disponiveis=somente_disponiveis,
    )
    return ResultadoBusca(total=len(filtrados), pacotes=filtrados)


@router.get("/destinos/{id_destino}/streetview", response_model=StreetViewSaida)
def streetview_destino(id_destino: int) -> StreetViewSaida:
    """Retorna a URL/embed de Street View (visualizacao 3D) de um destino (RF9)."""
    try:
        destino = repository.buscar_destino(id_destino)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    if destino is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Destino nao encontrado."
        )

    url = montar_url_streetview(destino)
    local = ", ".join(p for p in (destino.cidade, destino.estado, destino.pais) if p)
    return StreetViewSaida(
        id_destino=destino.id_destino,
        local=local,
        url=url,
        embed_html=montar_embed_html(url, local),
    )
