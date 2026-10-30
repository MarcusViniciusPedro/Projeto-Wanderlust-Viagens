"""Acesso a dados de vendas via camada app.db (SQL Server).

A maquina de estados de pagamento (RF5) vive em ``service.py`` (logica pura).
Este modulo apenas persiste/atualiza o estado no banco. Sem banco configurado,
``get_connection`` levanta ``DatabaseNotConfiguredError``, convertido em erro
HTTP claro pelo router.
"""

from __future__ import annotations

from typing import Optional

from typing import Optional as _Optional

from app.core.config import Settings
from app.db.session import get_connection
from app.vendas.schemas import FormaPagamento, StatusPagamento
from app.vendas.service import Venda


def buscar_venda(
    id_venda: int, settings: _Optional[Settings] = None
) -> _Optional[Venda]:
    """Carrega a venda real (status/valor/forma) do banco pelo id.

    Retorna ``None`` se a venda nao existir. O estado persistido (e nao a
    entrada do cliente) e o que alimenta a maquina de estados no router.
    """
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id_venda, valor_total, forma_pagamento, status_pagamento
            FROM dbo.Venda
            WHERE id_venda = %s
            """,
            (id_venda,),
        )
        linha = cursor.fetchone()
    finally:
        conn.close()

    if linha is None:
        return None
    return Venda(
        id_venda=int(linha[0]),
        valor_total=float(linha[1]),
        forma_pagamento=FormaPagamento(linha[2]),
        status_pagamento=StatusPagamento(linha[3]),
    )


def registrar_venda(
    fk_conta_turista: int,
    fk_pacote: int,
    forma_pagamento: str,
    fk_conta_colaborador: Optional[int] = None,
    settings: Optional[Settings] = None,
) -> "tuple[int, float]":
    """Registra uma venda via sp_registrar_venda.

    Retorna ``(id_venda, valor_total)`` onde ``valor_total`` e o valor
    EFETIVAMENTE persistido (o preco_base do pacote gravado pela procedure),
    e nao um valor enviado pelo cliente. Assim a resposta da API reflete o que
    ficou no banco (RF5).
    """
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
            SELECT @id_venda, (SELECT valor_total FROM dbo.Venda WHERE id_venda = @id_venda);
            """,
            (
                fk_conta_turista,
                fk_pacote,
                forma_pagamento,
                fk_conta_colaborador,
                StatusPagamento.PENDENTE.value,
            ),
        )
        linha = cursor.fetchone()
        conn.commit()
    finally:
        conn.close()
    return int(linha[0]), float(linha[1])


def atualizar_status(
    id_venda: int,
    novo_status: StatusPagamento,
    status_esperado: _Optional[StatusPagamento] = None,
    settings: Optional[Settings] = None,
) -> bool:
    """Atualiza o status_pagamento de uma venda, de forma condicional.

    Quando ``status_esperado`` e informado, o UPDATE so e aplicado se a linha
    ainda estiver nesse status (``WHERE status_pagamento = <esperado>``),
    fechando a corrida entre leitura e escrita (dois reembolsos concorrentes,
    por exemplo). Retorna ``True`` se alguma linha foi atualizada.
    """
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        if status_esperado is None:
            cursor.execute(
                "UPDATE dbo.Venda SET status_pagamento = %s WHERE id_venda = %s",
                (novo_status.value, id_venda),
            )
        else:
            cursor.execute(
                """
                UPDATE dbo.Venda
                SET status_pagamento = %s
                WHERE id_venda = %s AND status_pagamento = %s
                """,
                (novo_status.value, id_venda, status_esperado.value),
            )
        afetadas = cursor.rowcount
        conn.commit()
    finally:
        conn.close()
    return afetadas != 0
