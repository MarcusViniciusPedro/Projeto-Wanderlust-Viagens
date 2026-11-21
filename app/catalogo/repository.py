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
    HospedagemCriar,
    HospedagemSaida,
    PacoteCriar,
    PacoteSaida,
)
from app.core.config import Settings
from app.db.session import get_connection


def listar_pacotes(settings: Optional[Settings] = None) -> List[PacoteSaida]:
    """Carrega todos os pacotes do catalogo."""
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        # Leitura via procedure: sp_listar_pacotes devolve TODAS as linhas com
        # as mesmas colunas/ordem; a filtragem (RF3) continua em service.py.
        cursor.execute("EXEC dbo.sp_listar_pacotes")
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
            fk_destino=linha[7],
            cidade=linha[8],
            estado=linha[9],
            descricao=linha[10],
        )
        for linha in linhas
    ]


# ---------------------------------------------------------------------------
# Gerenciar Catalogo (admin, secao 4.1): escrita de Pacote.
# As quatro operacoes de Pacote (criar/alterar/excluir/listar) vivem em
# stored procedures (sql/04_programmability.sql) e sao chamadas via EXEC com
# parametrizacao %s (pymssql). A procedure de insercao devolve o id gerado via
# SELECT CAST(SCOPE_IDENTITY() AS INT) (mesma convencao de sp_registrar_venda),
# lido via fetchone()[0]. As de update/delete devolvem SELECT @@ROWCOUNT (sob
# SET NOCOUNT ON o cursor.rowcount do pymssql e nao confiavel). Sem banco
# configurado, get_connection levanta DatabaseNotConfiguredError, convertido em
# HTTP 503 pelo router.
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
            EXEC dbo.sp_criar_pacote
                @preco_base=%s,
                @data_inicio=%s,
                @data_fim=%s,
                @estoque=%s,
                @tipo_viagem=%s,
                @nivel=%s,
                @fk_destino=%s
            """,
            (
                dados.preco_base,
                dados.data_inicio,
                dados.data_fim,
                dados.estoque,
                dados.tipo_viagem,
                dados.nivel,
                dados.fk_destino,
            ),
        )
        # Procedure devolve SELECT CAST(SCOPE_IDENTITY() AS INT); leia o id dai.
        id_pacote = cursor.fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    # cidade/estado/descricao ficam None no retorno de escrita; so a leitura
    # (sp_listar_pacotes/buscar_pacote) faz o JOIN com Destino.
    return PacoteSaida(
        id_pacote=id_pacote,
        preco_base=float(dados.preco_base),
        data_inicio=dados.data_inicio,
        data_fim=dados.data_fim,
        estoque=dados.estoque,
        tipo_viagem=dados.tipo_viagem,
        nivel=dados.nivel,
        fk_destino=dados.fk_destino,
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
            SELECT p.id_pacote, p.preco_base, p.data_inicio, p.data_fim,
                   p.estoque, p.tipo_viagem, p.nivel, p.fk_destino,
                   d.cidade, d.estado, d.descricao
            FROM dbo.Pacote p
            JOIN dbo.Destino d ON d.id_destino = p.fk_destino
            WHERE p.id_pacote = %s
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
        fk_destino=linha[7],
        cidade=linha[8],
        estado=linha[9],
        descricao=linha[10],
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
            EXEC dbo.sp_atualizar_pacote
                @id_pacote=%s,
                @preco_base=%s,
                @data_inicio=%s,
                @data_fim=%s,
                @estoque=%s,
                @tipo_viagem=%s,
                @nivel=%s,
                @fk_destino=%s
            """,
            (
                id_pacote,
                dados.preco_base,
                dados.data_inicio,
                dados.data_fim,
                dados.estoque,
                dados.tipo_viagem,
                dados.nivel,
                dados.fk_destino,
            ),
        )
        # Procedure sob SET NOCOUNT ON devolve SELECT @@ROWCOUNT; leia dai.
        afetadas = cursor.fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    if afetadas == 0:
        return None
    # cidade/estado/descricao ficam None no retorno de escrita; so a leitura
    # faz o JOIN com Destino.
    return PacoteSaida(
        id_pacote=id_pacote,
        preco_base=float(dados.preco_base),
        data_inicio=dados.data_inicio,
        data_fim=dados.data_fim,
        estoque=dados.estoque,
        tipo_viagem=dados.tipo_viagem,
        nivel=dados.nivel,
        fk_destino=dados.fk_destino,
    )


def excluir_pacote(id_pacote: int, settings: Optional[Settings] = None) -> bool:
    """Remove um pacote pelo id. Retorna True se alguma linha foi removida."""
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute("EXEC dbo.sp_excluir_pacote %s", (id_pacote,))
        # Procedure sob SET NOCOUNT ON devolve SELECT @@ROWCOUNT; leia dai.
        afetadas = cursor.fetchone()[0]
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


def listar_destinos(settings: Optional[Settings] = None) -> List[DestinoSaida]:
    """Lista todos os destinos do catalogo (leitura completa de Destino)."""
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id_destino, cidade, estado, pais, categoria, descricao
            FROM dbo.Destino
            ORDER BY id_destino
            """
        )
        linhas = cursor.fetchall()
    finally:
        conn.close()

    return [
        DestinoSaida(
            id_destino=linha[0],
            cidade=linha[1],
            estado=linha[2],
            pais=linha[3],
            categoria=linha[4],
            descricao=linha[5],
        )
        for linha in linhas
    ]


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
# Gerenciar Catalogo (admin, secao 4.1): CRUD de Hospedagem (dbo.Hospedagem).
# ---------------------------------------------------------------------------


def criar_hospedagem(
    dados: HospedagemCriar, settings: Optional[Settings] = None
) -> HospedagemSaida:
    """Insere uma hospedagem e retorna a representacao com o id gerado."""
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO dbo.Hospedagem
                (cep, rua, numero, nome, tipo_quarto, regime_alimentacao,
                 fk_Pacote_id_pacote)
            OUTPUT INSERTED.id_hospedagem
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                dados.cep,
                dados.rua,
                dados.numero,
                dados.nome,
                dados.tipo_quarto,
                dados.regime_alimentacao,
                dados.fk_Pacote_id_pacote,
            ),
        )
        id_hospedagem = cursor.fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    return HospedagemSaida(id_hospedagem=id_hospedagem, **dados.model_dump())


def listar_hospedagens(
    fk_pacote: Optional[int] = None, settings: Optional[Settings] = None
) -> List[HospedagemSaida]:
    """Lista hospedagens, opcionalmente filtrando por pacote (fk_pacote)."""
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        if fk_pacote is None:
            cursor.execute(
                """
                SELECT id_hospedagem, cep, rua, numero, nome, tipo_quarto,
                       regime_alimentacao, fk_Pacote_id_pacote
                FROM dbo.Hospedagem
                ORDER BY id_hospedagem
                """
            )
        else:
            cursor.execute(
                """
                SELECT id_hospedagem, cep, rua, numero, nome, tipo_quarto,
                       regime_alimentacao, fk_Pacote_id_pacote
                FROM dbo.Hospedagem
                WHERE fk_Pacote_id_pacote = %s
                ORDER BY id_hospedagem
                """,
                (fk_pacote,),
            )
        linhas = cursor.fetchall()
    finally:
        conn.close()

    return [
        HospedagemSaida(
            id_hospedagem=linha[0],
            cep=linha[1],
            rua=linha[2],
            numero=linha[3],
            nome=linha[4],
            tipo_quarto=linha[5],
            regime_alimentacao=linha[6],
            fk_Pacote_id_pacote=linha[7],
        )
        for linha in linhas
    ]


def buscar_hospedagem(
    id_hospedagem: int, settings: Optional[Settings] = None
) -> Optional[HospedagemSaida]:
    """Carrega uma hospedagem pelo id (ou None se nao existir)."""
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id_hospedagem, cep, rua, numero, nome, tipo_quarto,
                   regime_alimentacao, fk_Pacote_id_pacote
            FROM dbo.Hospedagem
            WHERE id_hospedagem = %s
            """,
            (id_hospedagem,),
        )
        linha = cursor.fetchone()
    finally:
        conn.close()

    if linha is None:
        return None
    return HospedagemSaida(
        id_hospedagem=linha[0],
        cep=linha[1],
        rua=linha[2],
        numero=linha[3],
        nome=linha[4],
        tipo_quarto=linha[5],
        regime_alimentacao=linha[6],
        fk_Pacote_id_pacote=linha[7],
    )


def atualizar_hospedagem(
    id_hospedagem: int,
    dados: HospedagemCriar,
    settings: Optional[Settings] = None,
) -> Optional[HospedagemSaida]:
    """Atualiza uma hospedagem existente. Retorna a atualizada ou None."""
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE dbo.Hospedagem
            SET cep = %s,
                rua = %s,
                numero = %s,
                nome = %s,
                tipo_quarto = %s,
                regime_alimentacao = %s,
                fk_Pacote_id_pacote = %s
            WHERE id_hospedagem = %s
            """,
            (
                dados.cep,
                dados.rua,
                dados.numero,
                dados.nome,
                dados.tipo_quarto,
                dados.regime_alimentacao,
                dados.fk_Pacote_id_pacote,
                id_hospedagem,
            ),
        )
        afetadas = cursor.rowcount
        conn.commit()
    finally:
        conn.close()

    if afetadas == 0:
        return None
    return HospedagemSaida(id_hospedagem=id_hospedagem, **dados.model_dump())


def excluir_hospedagem(
    id_hospedagem: int, settings: Optional[Settings] = None
) -> bool:
    """Remove uma hospedagem pelo id. Retorna True se removeu alguma linha."""
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM dbo.Hospedagem WHERE id_hospedagem = %s",
            (id_hospedagem,),
        )
        afetadas = cursor.rowcount
        conn.commit()
    finally:
        conn.close()

    return afetadas > 0
