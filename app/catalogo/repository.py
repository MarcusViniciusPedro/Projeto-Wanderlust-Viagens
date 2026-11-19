"""Acesso a dados do catalogo (pacotes e destinos) via camada app.db.

A logica de filtragem (RF3) vive em ``service.filtrar_pacotes`` (funcao pura).
Este modulo apenas carrega os dados do SQL Server; sem banco configurado,
``get_connection`` levanta ``DatabaseNotConfiguredError``, convertido em erro
HTTP claro pelo router.
"""

from __future__ import annotations

from typing import List, Optional

from app.catalogo.schemas import PacoteSaida
from app.core.config import Settings
from app.db.session import get_connection
from app.integracoes.streetview import Destino


def listar_pacotes(settings: Optional[Settings] = None) -> List[PacoteSaida]:
    """Carrega todos os pacotes do catalogo."""
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id_pacote, preco_base, data_inicio, data_fim,
                   estoque, tipo_viagem, nivel
            FROM dbo.Pacote
            """
        )
        linhas = cursor.fetchall()
    finally:
        conn.close()

    return [
        PacoteSaida(
            id_pacote=linha[0],
            preco_base=float(linha[1]),
            data_inicio=linha[2],
            data_fim=linha[3],
            estoque=linha[4],
            tipo_viagem=linha[5],
            nivel=linha[6],
        )
        for linha in linhas
    ]


def buscar_destino(
    id_destino: int, settings: Optional[Settings] = None
) -> Optional[Destino]:
    """Carrega um destino pelo id (para a visualizacao 3D/Street View, RF9)."""
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id_destino, cidade, estado, pais
            FROM dbo.Destino
            WHERE id_destino = %s
            """,
            (id_destino,),
        )
        linha = cursor.fetchone()
    finally:
        conn.close()

    if linha is None:
        return None
    return Destino(
        id_destino=linha[0],
        cidade=linha[1],
        estado=linha[2],
        pais=linha[3],
    )
