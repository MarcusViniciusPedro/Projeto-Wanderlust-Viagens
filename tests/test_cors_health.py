"""Testes de CORS e verificacao de conectividade do banco (sem DB vivo)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings


def _client() -> TestClient:
    import app.main as main

    return TestClient(main.app)


def test_cors_header_para_origem_permitida() -> None:
    """Uma requisicao com Origin permitido recebe Access-Control-Allow-Origin."""
    client = _client()
    origem = "http://localhost:5500"
    resp = client.get("/health", headers={"Origin": origem})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == origem


def test_preflight_cors_para_origem_permitida() -> None:
    """Preflight OPTIONS responde com os cabecalhos CORS para origem permitida."""
    client = _client()
    origem = "http://127.0.0.1:5500"
    resp = client.options(
        "/health",
        headers={
            "Origin": origem,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == origem


def test_health_db_sem_config_retorna_503() -> None:
    """GET /health/db sem configuracao de DB retorna 503 com mensagem clara."""
    client = _client()
    resp = client.get("/health/db")
    assert resp.status_code == 503
    assert "nao configurado" in resp.json()["detail"].lower()


def test_settings_expoe_cors_origins_defaults() -> None:
    """Settings expoe cors_origins com os defaults esperados de dev local."""
    settings = Settings()
    assert settings.cors_origins == [
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]


def test_cors_origins_aceita_csv() -> None:
    """cors_origins aceita string separada por virgula (alem de lista JSON)."""
    settings = Settings(cors_origins="http://a.example, http://b.example")
    assert settings.cors_origins == ["http://a.example", "http://b.example"]
