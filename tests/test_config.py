"""Testes de baseline: a app importa e configura sem banco de dados vivo."""

from __future__ import annotations

import pytest

from app.core.config import Settings, get_settings


def test_importa_app_main_sem_db() -> None:
    """Importar app.main nao deve exigir nem abrir conexao com o banco."""
    import app.main as main  # import tardio para validar que nao conecta

    assert main.app.title == "Wanderlust Viagens API"


def test_settings_carrega_com_defaults() -> None:
    """Settings deve instanciar mesmo sem variaveis de ambiente definidas."""
    settings = Settings()
    assert settings.app_name == "Wanderlust Viagens API"
    assert settings.jwt_algorithm == "HS256"


def test_get_settings_memoizado() -> None:
    """get_settings deve retornar sempre a mesma instancia (cache)."""
    assert get_settings() is get_settings()


def test_db_nao_configurado_por_padrao() -> None:
    """Sem variaveis de DB, db_configured deve ser False (app roda sem banco)."""
    settings = Settings(
        db_server=None, db_name=None, db_user=None, db_password=None
    )
    assert settings.db_configured is False


def test_get_connection_sem_config_levanta_erro() -> None:
    """Usar o banco sem configuracao levanta erro claro (nao conecta a toa)."""
    from app.db.session import DatabaseNotConfiguredError, get_connection

    settings = Settings(
        db_server=None, db_name=None, db_user=None, db_password=None
    )
    with pytest.raises(DatabaseNotConfiguredError):
        get_connection(settings)


def test_health_endpoint() -> None:
    """O endpoint /health responde sem depender do banco."""
    from fastapi.testclient import TestClient

    import app.main as main

    client = TestClient(main.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
