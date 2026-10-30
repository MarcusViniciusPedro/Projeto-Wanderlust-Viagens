"""Acesso a dados de vendas via camada app.db (SQL Server).

A maquina de estados de pagamento (RF5) vive em ``service.py`` (logica pura).
Este modulo apenas persiste/atualiza o estado no banco. Sem banco configurado,
``get_connection`` levanta ``DatabaseNotConfiguredError``, convertido em erro
HTTP claro pelo router.
"""

from __future__ import annotations

from typing import Optional

from app.core.config import Settings
from app.db.session import get_connection
from app.vendas.schemas import StatusPagamento


def registrar_venda(
    fk_conta_turista: int,
    fk_pacote: int,
    forma_pagamento: str,
    fk_conta_colaborador: Optional[int] = None,
    settings: Optional[Settings] = None,
) -> int:
    """Registra uma venda via sp_registrar_venda e retorna o id_venda gerado."""
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            DECLARE @id_venda INT;
            EXEC dbo.sp_registrar_venda
                @fk_conta_turista=%s,
                @fk_pacote=%s,
                @forma_pagamento=%s,
                @fk_conta_colaborador=%s,
                @status_pagamento=%s,
                @id_venda_out=@id_venda OUTPUT;
            SELECT @id_venda;
            """,
            (
                fk_conta_turista,
                fk_pacote,
                forma_pagamento,
                fk_conta_colaborador,
                StatusPagamento.PENDENTE.value,
            ),
        )
        id_venda = cursor.fetchone()[0]
        conn.commit()
    finally:
        conn.close()
    return int(id_venda)


def atualizar_status(
    id_venda: int, novo_status: StatusPagamento, settings: Optional[Settings] = None
) -> None:
    """Atualiza o status_pagamento de uma venda."""
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE dbo.Venda SET status_pagamento = %s WHERE id_venda = %s",
            (novo_status.value, id_venda),
        )
        conn.commit()
    finally:
        conn.close()
