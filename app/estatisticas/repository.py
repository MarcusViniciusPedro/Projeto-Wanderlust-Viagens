"""Acesso a dados das estatisticas de turistas por destino (RF10).

Carrega os eventos (destino, mes) de um ano a partir do banco, ligando
Venda -> Passagem -> Viagem -> Destino (mesma logica da VIEW
``vw_turistas_por_destino_ano``, porem com granularidade mensal). A agregacao
em si vive em ``service.agregar_turistas_por_mes`` (funcao pura). Sem banco
configurado, ``get_connection`` levanta ``DatabaseNotConfiguredError``.
"""

from __future__ import annotations

from typing import List, Optional

from app.core.config import Settings
from app.db.session import get_connection
from app.estatisticas.service import EventoTuristaDestino


def carregar_eventos_ano(
    ano: int, settings: Optional[Settings] = None
) -> List[EventoTuristaDestino]:
    """Carrega a incidencia (destino, mes, qtd) de turistas de um ano."""
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT d.cidade,
                   MONTH(v.data_venda)                AS mes,
                   COUNT(DISTINCT v.fk_conta_turista) AS qtd
            FROM dbo.Venda    AS v
            INNER JOIN dbo.Passagem AS pg ON pg.fk_id_venda = v.id_venda
            INNER JOIN dbo.Viagem   AS vi ON vi.id_viagem = pg.fk_id_viagem
            INNER JOIN dbo.Destino  AS d  ON d.id_destino = vi.fk_Destino_id_destino
            WHERE YEAR(v.data_venda) = %s
            GROUP BY d.cidade, MONTH(v.data_venda)
            """,
            (ano,),
        )
        linhas = cursor.fetchall()
    finally:
        conn.close()

    return [
        EventoTuristaDestino(destino=linha[0], mes=linha[1], quantidade=linha[2])
        for linha in linhas
    ]
