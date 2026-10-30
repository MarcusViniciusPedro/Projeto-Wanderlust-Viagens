"""Fabrica de conexoes com o SQL Server (preguicosa e configuravel).

Importante: nada aqui conecta ao banco na importacao. A conexao so e aberta
quando ``get_connection`` for chamada. Se a configuracao do banco estiver
ausente, um erro claro e levantado em vez de falhar silenciosamente ou na
importacao do modulo. Isso permite que a app e os testes rodem sem DB vivo.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from app.core.config import Settings, get_settings

if TYPE_CHECKING:  # pragma: no cover - apenas para type checking
    pass


class DatabaseNotConfiguredError(RuntimeError):
    """Levantado quando o banco e usado sem configuracao completa."""


def get_connection(settings: Optional[Settings] = None) -> Any:
    """Abre e retorna uma conexao pymssql com o SQL Server.

    A importacao do driver ``pymssql`` tambem e preguicosa (feita aqui dentro)
    para que o modulo possa ser importado em ambientes sem o driver carregado.

    Levanta ``DatabaseNotConfiguredError`` se faltar configuracao de conexao.
    """
    settings = settings or get_settings()

    if not settings.db_configured:
        raise DatabaseNotConfiguredError(
            "Banco de dados nao configurado. Defina as variaveis WANDERLUST_DB_SERVER, "
            "WANDERLUST_DB_NAME, WANDERLUST_DB_USER e WANDERLUST_DB_PASSWORD."
        )

    import pymssql  # import preguicoso: nao exigir driver na importacao do modulo

    return pymssql.connect(
        server=settings.db_server,
        port=str(settings.db_port),
        database=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
    )
