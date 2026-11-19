"""Rotas HTTP das estatisticas de turistas por destino (RF10).

Endpoint:
  GET /estatisticas/turistas-por-destino?ano=AAAA

Retorna uma estrutura pronta para grafico: ``{destino: [12 contagens]}``. A
agregacao mensal vive em ``service.agregar_turistas_por_mes`` (funcao pura).
Sem banco configurado, ``DatabaseNotConfiguredError`` vira HTTP 503.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List

from fastapi import APIRouter, HTTPException, Query, status

from app.db.session import DatabaseNotConfiguredError
from app.estatisticas import repository
from app.estatisticas.service import agregar_turistas_por_mes

router = APIRouter(prefix="/estatisticas", tags=["estatisticas"])


@router.get("/turistas-por-destino")
def turistas_por_destino(
    ano: int = Query(default_factory=lambda: date.today().year, ge=1900, le=3000),
) -> Dict[str, List[int]]:
    """Agrega a incidencia de turistas por destino ao longo dos 12 meses (RF10)."""
    try:
        eventos = repository.carregar_eventos_ano(ano)
    except DatabaseNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Banco de dados nao configurado. Configure as variaveis "
                "WANDERLUST_DB_* para habilitar a persistencia."
            ),
        ) from exc
    return agregar_turistas_por_mes(eventos)
