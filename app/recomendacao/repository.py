"""Acesso a dados do AIV (avaliacoes) via app.db.

A inteligencia (orcamento, recomendacao, feedback) vive em ``service.py``
(funcoes PURAS). Este modulo persiste/coleta as ``Avaliacao`` dos pacotes, que
alimentam a agregacao de feedback (RF8).

Sem banco configurado, ``get_connection`` levanta
``DatabaseNotConfiguredError``, convertido em HTTP 503 pelo router. A
parametrizacao usa ``%s`` (pymssql); nomes de tabelas/colunas espelham
``sql/01_schema.sql`` e ``sql/02_aiv_tables.sql``.
"""

from __future__ import annotations

from typing import List, Optional

from app.core.config import Settings
from app.db.session import get_connection
from app.recomendacao.schemas import Avaliacao


class AvaliacaoDuplicadaError(RuntimeError):
    """Levantado quando o turista ja avaliou o pacote (UNIQUE fk_turista,fk_pacote)."""


def registrar_avaliacao(
    fk_turista: int,
    fk_pacote: int,
    nota: int,
    comentario: Optional[str] = None,
    settings: Optional[Settings] = None,
) -> int:
    """Insere uma avaliacao do turista para um pacote e retorna o id gerado.

    A restricao UNIQUE(fk_turista, fk_pacote) garante uma avaliacao por par. O
    INSERT e a guarda AUTORITATIVA contra duplicatas: se ele violar a restricao
    (``pymssql.IntegrityError``), a violacao e traduzida em
    ``AvaliacaoDuplicadaError`` (convertida em HTTP 409 pelo router). O SELECT
    previo e apenas um atalho para responder 409 sem tentar o INSERT no caso
    comum; ele NAO protege contra concorrencia (dois pedidos podem passar pelo
    SELECT e so o INSERT barra o segundo), por isso o tratamento no INSERT.
    """
    # Import preguicoso do driver (como em app.db.session): manter o modulo
    # importavel sem o pymssql instalado/sem banco vivo.
    import pymssql

    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 1 FROM dbo.Avaliacao
            WHERE fk_turista = %s AND fk_pacote = %s
            """,
            (fk_turista, fk_pacote),
        )
        if cursor.fetchone() is not None:
            raise AvaliacaoDuplicadaError(
                "Voce ja avaliou este pacote. Use a atualizacao da avaliacao."
            )
        try:
            cursor.execute(
                """
                INSERT INTO dbo.Avaliacao
                    (fk_turista, fk_pacote, nota, comentario)
                OUTPUT INSERTED.id_avaliacao
                VALUES (%s, %s, %s, %s)
                """,
                (fk_turista, fk_pacote, nota, comentario),
            )
            id_avaliacao = cursor.fetchone()[0]
            conn.commit()
        except pymssql.IntegrityError as exc:
            # Corrida: outro pedido inseriu o mesmo par entre o SELECT e o
            # INSERT e a UNIQUE(fk_turista, fk_pacote) barrou este. Desfaz e
            # traduz para o erro de duplicata (409), nunca 500.
            conn.rollback()
            raise AvaliacaoDuplicadaError(
                "Voce ja avaliou este pacote. Use a atualizacao da avaliacao."
            ) from exc
    finally:
        conn.close()

    return id_avaliacao


def listar_avaliacoes_do_pacote(
    fk_pacote: int, settings: Optional[Settings] = None
) -> List[Avaliacao]:
    """Carrega as avaliacoes persistidas de um pacote (insumo do agregar_feedback)."""
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT nota, comentario
            FROM dbo.Avaliacao
            WHERE fk_pacote = %s
            """,
            (fk_pacote,),
        )
        linhas = cursor.fetchall()
    finally:
        conn.close()

    return [Avaliacao(nota=linha[0], comentario=linha[1]) for linha in linhas]
