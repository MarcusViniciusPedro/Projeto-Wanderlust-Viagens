"""Acesso a dados do catalogo (pacotes e destinos) via camada app.db.

A logica de filtragem (RF3) vive em ``service.filtrar_pacotes`` (funcao pura).
Este modulo apenas carrega os dados do SQL Server; sem banco configurado,
``get_connection`` levanta ``DatabaseNotConfiguredError``, convertido em erro
HTTP claro pelo router.
"""

from __future__ import annotations

from typing import List, Optional

from app.catalogo.schemas import (
    DestinoCriar,
    DestinoSaida,
    PacoteCriar,
    PacoteSaida,
    ViagemCriar,
    ViagemSaida,
)
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


# ---------------------------------------------------------------------------
# Gerenciar Catalogo (admin, secao 4.1): escrita de Pacote.
# Inserts usam OUTPUT INSERTED.<pk> (padrao de usuarios.criar_usuario) e
# parametrizacao %s (pymssql). Sem banco configurado, get_connection levanta
# DatabaseNotConfiguredError, convertido em HTTP 503 pelo router.
# ---------------------------------------------------------------------------


def criar_pacote(
    dados: PacoteCriar, settings: Optional[Settings] = None
) -> PacoteSaida:
    """Insere um pacote e retorna a representacao com o id gerado."""
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO dbo.Pacote
                (preco_base, data_inicio, data_fim, estoque, tipo_viagem, nivel)
            OUTPUT INSERTED.id_pacote
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                dados.preco_base,
                dados.data_inicio,
                dados.data_fim,
                dados.estoque,
                dados.tipo_viagem,
                dados.nivel,
            ),
        )
        id_pacote = cursor.fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    return PacoteSaida(
        id_pacote=id_pacote,
        preco_base=float(dados.preco_base),
        data_inicio=dados.data_inicio,
        data_fim=dados.data_fim,
        estoque=dados.estoque,
        tipo_viagem=dados.tipo_viagem,
        nivel=dados.nivel,
    )


def buscar_pacote(
    id_pacote: int, settings: Optional[Settings] = None
) -> Optional[PacoteSaida]:
    """Carrega um pacote pelo id (ou None se nao existir)."""
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id_pacote, preco_base, data_inicio, data_fim,
                   estoque, tipo_viagem, nivel
            FROM dbo.Pacote
            WHERE id_pacote = %s
            """,
            (id_pacote,),
        )
        linha = cursor.fetchone()
    finally:
        conn.close()

    if linha is None:
        return None
    return PacoteSaida(
        id_pacote=linha[0],
        preco_base=float(linha[1]),
        data_inicio=linha[2],
        data_fim=linha[3],
        estoque=linha[4],
        tipo_viagem=linha[5],
        nivel=linha[6],
    )


def atualizar_pacote(
    id_pacote: int, dados: PacoteCriar, settings: Optional[Settings] = None
) -> Optional[PacoteSaida]:
    """Atualiza um pacote existente. Retorna o pacote atualizado ou None."""
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE dbo.Pacote
            SET preco_base = %s,
                data_inicio = %s,
                data_fim = %s,
                estoque = %s,
                tipo_viagem = %s,
                nivel = %s
            WHERE id_pacote = %s
            """,
            (
                dados.preco_base,
                dados.data_inicio,
                dados.data_fim,
                dados.estoque,
                dados.tipo_viagem,
                dados.nivel,
                id_pacote,
            ),
        )
        afetadas = cursor.rowcount
        conn.commit()
    finally:
        conn.close()

    if afetadas == 0:
        return None
    return PacoteSaida(
        id_pacote=id_pacote,
        preco_base=float(dados.preco_base),
        data_inicio=dados.data_inicio,
        data_fim=dados.data_fim,
        estoque=dados.estoque,
        tipo_viagem=dados.tipo_viagem,
        nivel=dados.nivel,
    )


def excluir_pacote(id_pacote: int, settings: Optional[Settings] = None) -> bool:
    """Remove um pacote pelo id. Retorna True se alguma linha foi removida."""
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM dbo.Pacote WHERE id_pacote = %s",
            (id_pacote,),
        )
        afetadas = cursor.rowcount
        conn.commit()
    finally:
        conn.close()

    return afetadas > 0


# ---------------------------------------------------------------------------
# Gerenciar Catalogo (admin, secao 4.1): escrita de Destino.
# ---------------------------------------------------------------------------


def criar_destino(
    dados: DestinoCriar, settings: Optional[Settings] = None
) -> DestinoSaida:
    """Insere um destino e retorna a representacao com o id gerado."""
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO dbo.Destino
                (cidade, estado, pais, categoria, descricao)
            OUTPUT INSERTED.id_destino
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                dados.cidade,
                dados.estado,
                dados.pais,
                dados.categoria,
                dados.descricao,
            ),
        )
        id_destino = cursor.fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    return DestinoSaida(
        id_destino=id_destino,
        cidade=dados.cidade,
        estado=dados.estado,
        pais=dados.pais,
        categoria=dados.categoria,
        descricao=dados.descricao,
    )


def buscar_destino_completo(
    id_destino: int, settings: Optional[Settings] = None
) -> Optional[DestinoSaida]:
    """Carrega um destino completo pelo id (inclui categoria e descricao)."""
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id_destino, cidade, estado, pais, categoria, descricao
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
    return DestinoSaida(
        id_destino=linha[0],
        cidade=linha[1],
        estado=linha[2],
        pais=linha[3],
        categoria=linha[4],
        descricao=linha[5],
    )


def atualizar_destino(
    id_destino: int, dados: DestinoCriar, settings: Optional[Settings] = None
) -> Optional[DestinoSaida]:
    """Atualiza um destino existente. Retorna o destino atualizado ou None."""
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE dbo.Destino
            SET cidade = %s,
                estado = %s,
                pais = %s,
                categoria = %s,
                descricao = %s
            WHERE id_destino = %s
            """,
            (
                dados.cidade,
                dados.estado,
                dados.pais,
                dados.categoria,
                dados.descricao,
                id_destino,
            ),
        )
        afetadas = cursor.rowcount
        conn.commit()
    finally:
        conn.close()

    if afetadas == 0:
        return None
    return DestinoSaida(
        id_destino=id_destino,
        cidade=dados.cidade,
        estado=dados.estado,
        pais=dados.pais,
        categoria=dados.categoria,
        descricao=dados.descricao,
    )


def excluir_destino(id_destino: int, settings: Optional[Settings] = None) -> bool:
    """Remove um destino pelo id. Retorna True se alguma linha foi removida."""
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM dbo.Destino WHERE id_destino = %s",
            (id_destino,),
        )
        afetadas = cursor.rowcount
        conn.commit()
    finally:
        conn.close()

    return afetadas > 0


# ---------------------------------------------------------------------------
# Agendar Viagem (admin, secao 4.1): CRUD de Viagem (dbo.Viagem).
# ---------------------------------------------------------------------------


def criar_viagem(
    dados: ViagemCriar, settings: Optional[Settings] = None
) -> ViagemSaida:
    """Agenda uma viagem vinculada a um destino e retorna o id gerado."""
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO dbo.Viagem
                (data_partida, data_chegada, meio_transporte, duracao,
                 fk_Destino_id_destino)
            OUTPUT INSERTED.id_viagem
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                dados.data_partida,
                dados.data_chegada,
                dados.meio_transporte,
                dados.duracao,
                dados.fk_Destino_id_destino,
            ),
        )
        id_viagem = cursor.fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    return ViagemSaida(
        id_viagem=id_viagem,
        data_partida=dados.data_partida,
        data_chegada=dados.data_chegada,
        meio_transporte=dados.meio_transporte,
        duracao=dados.duracao,
        fk_Destino_id_destino=dados.fk_Destino_id_destino,
    )


def listar_viagens(settings: Optional[Settings] = None) -> List[ViagemSaida]:
    """Lista todas as viagens agendadas (Agendar Viagem, secao 4.1)."""
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id_viagem, data_partida, data_chegada, meio_transporte,
                   duracao, fk_Destino_id_destino
            FROM dbo.Viagem
            ORDER BY data_partida
            """
        )
        linhas = cursor.fetchall()
    finally:
        conn.close()

    return [
        ViagemSaida(
            id_viagem=linha[0],
            data_partida=linha[1],
            data_chegada=linha[2],
            meio_transporte=linha[3],
            duracao=linha[4],
            fk_Destino_id_destino=linha[5],
        )
        for linha in linhas
    ]


def excluir_viagem(id_viagem: int, settings: Optional[Settings] = None) -> bool:
    """Remove uma viagem pelo id. Retorna True se alguma linha foi removida."""
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM dbo.Viagem WHERE id_viagem = %s",
            (id_viagem,),
        )
        afetadas = cursor.rowcount
        conn.commit()
    finally:
        conn.close()

    return afetadas > 0
