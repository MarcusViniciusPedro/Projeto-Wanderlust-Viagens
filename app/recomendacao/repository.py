"""Acesso a dados do AIV (pacotes, preferencias e avaliacoes) via app.db.

A inteligencia (orcamento, recomendacao, feedback) vive em ``service.py``
(funcoes PURAS). Este modulo apenas coleta/persiste os dados que alimentam
essas heuristicas: pacotes do catalogo com a reputacao de ``IA_Feedback``, a
``Preferencia`` do turista e as ``Avaliacao`` dos pacotes.

Sem banco configurado, ``get_connection`` levanta
``DatabaseNotConfiguredError``, convertido em HTTP 503 pelo router. A
parametrizacao usa ``%s`` (pymssql); nomes de tabelas/colunas espelham
``sql/01_schema.sql`` e ``sql/02_aiv_tables.sql``.
"""

from __future__ import annotations

from typing import List, Optional

from app.core.config import Settings
from app.db.session import get_connection
from app.recomendacao.schemas import (
    Avaliacao,
    PacoteParaRecomendacao,
    Preferencia,
)


class AvaliacaoDuplicadaError(RuntimeError):
    """Levantado quando o turista ja avaliou o pacote (UNIQUE fk_turista,fk_pacote)."""


def listar_pacotes_para_recomendacao(
    settings: Optional[Settings] = None,
) -> List[PacoteParaRecomendacao]:
    """Coleta os pacotes do catalogo com a reputacao agregada do AIV.

    Faz LEFT JOIN de ``dbo.Pacote`` com ``dbo.IA_Feedback`` por ``fk_pacote``,
    de modo que pacotes ainda sem feedback entram com reputacao nula (o service
    os trata como neutros). Os campos mapeiam para ``PacoteParaRecomendacao``:
    ``score_avaliacoes = IA_Feedback.score_agregado`` e
    ``total_avaliacoes = IA_Feedback.total_avaliacoes``.
    """
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT p.id_pacote, p.preco_base, p.data_inicio, p.data_fim,
                   p.tipo_viagem, p.nivel,
                   f.score_agregado, f.total_avaliacoes
            FROM dbo.Pacote AS p
            LEFT JOIN dbo.IA_Feedback AS f
                ON f.fk_pacote = p.id_pacote
            """
        )
        linhas = cursor.fetchall()
    finally:
        conn.close()

    return [
        PacoteParaRecomendacao(
            id_pacote=linha[0],
            preco_base=float(linha[1]),
            data_inicio=linha[2],
            data_fim=linha[3],
            tipo_viagem=linha[4],
            nivel=linha[5],
            score_avaliacoes=float(linha[6]) if linha[6] is not None else None,
            total_avaliacoes=int(linha[7]) if linha[7] is not None else 0,
        )
        for linha in linhas
    ]


def buscar_preferencia_turista(
    fk_turista: int, settings: Optional[Settings] = None
) -> Optional[Preferencia]:
    """Carrega a Preferencia do turista (ou None se ele ainda nao salvou uma).

    Ha no maximo uma Preferencia por turista (``fk_turista`` e UNIQUE).
    """
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT tipo_viagem, nivel, orcamento_max, estacao_preferida
            FROM dbo.Preferencia
            WHERE fk_turista = %s
            """,
            (fk_turista,),
        )
        linha = cursor.fetchone()
    finally:
        conn.close()

    if linha is None:
        return None
    return Preferencia(
        tipo_viagem=linha[0],
        nivel=linha[1],
        orcamento_max=float(linha[2]) if linha[2] is not None else None,
        estacao_preferida=linha[3],
    )


def upsert_preferencia(
    fk_turista: int,
    *,
    tipo_viagem: Optional[str],
    nivel: Optional[str],
    orcamento_max: Optional[float],
    estacao_preferida: Optional[str],
    observacoes: Optional[str],
    settings: Optional[Settings] = None,
) -> Preferencia:
    """Grava a Preferencia do turista (upsert, pois ``fk_turista`` e UNIQUE).

    Faz UPDATE quando ja existe uma Preferencia do turista e INSERT caso
    contrario, sempre renovando ``atualizado_em`` com ``SYSUTCDATETIME()``.
    Retorna a Preferencia (dataclass pura) gravada.
    """
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE dbo.Preferencia
            SET tipo_viagem = %s,
                nivel = %s,
                orcamento_max = %s,
                estacao_preferida = %s,
                observacoes = %s,
                atualizado_em = SYSUTCDATETIME()
            WHERE fk_turista = %s
            """,
            (
                tipo_viagem,
                nivel,
                orcamento_max,
                estacao_preferida,
                observacoes,
                fk_turista,
            ),
        )
        if cursor.rowcount == 0:
            cursor.execute(
                """
                INSERT INTO dbo.Preferencia
                    (fk_turista, tipo_viagem, nivel, orcamento_max,
                     estacao_preferida, observacoes)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    fk_turista,
                    tipo_viagem,
                    nivel,
                    orcamento_max,
                    estacao_preferida,
                    observacoes,
                ),
            )
        conn.commit()
    finally:
        conn.close()

    return Preferencia(
        tipo_viagem=tipo_viagem,
        nivel=nivel,
        orcamento_max=float(orcamento_max) if orcamento_max is not None else None,
        estacao_preferida=estacao_preferida,
    )


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
