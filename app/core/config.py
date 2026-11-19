"""Configuracao da aplicacao lida de variaveis de ambiente / arquivo .env.

Todas as configuracoes sao opcionais na importacao: a aplicacao sobe e os
testes rodam sem um banco de dados vivo. A conexao com o SQL Server so e
aberta quando um recurso que precisa dela for efetivamente usado.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracoes carregadas de variaveis de ambiente (prefixo WANDERLUST_)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="WANDERLUST_",
        extra="ignore",
    )

    # --- Aplicacao ---------------------------------------------------------
    app_name: str = "Wanderlust Viagens API"
    app_version: str = "0.1.0"

    # --- CORS --------------------------------------------------------------
    # Origens permitidas para o front-end chamar a API pelo navegador.
    # O padrao cobre os servidores locais mais comuns de dev (Live Server na
    # 5500 e a propria API/uvicorn na 8000). Aceita lista JSON ou string
    # separada por virgula via WANDERLUST_CORS_ORIGINS.
    cors_origins: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:5500",
            "http://127.0.0.1:5500",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
    )

    # --- Banco de dados SQL Server (opcional) -----------------------------
    db_server: Optional[str] = None
    db_port: int = 1433
    db_name: Optional[str] = None
    db_user: Optional[str] = None
    db_password: Optional[str] = None

    # --- Autenticacao / seguranca -----------------------------------------
    jwt_secret: Optional[str] = None
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    totp_issuer: str = "Wanderlust Viagens"

    # --- Integracoes externas (stubs; vazio = desativado) -----------------
    sms_api_key: Optional[str] = None
    sms_sender: Optional[str] = None
    email_api_key: Optional[str] = None
    email_from: Optional[str] = None
    payment_api_key: Optional[str] = None
    payment_base_url: Optional[str] = None
    streetview_api_key: Optional[str] = None
    # URL base da visualizacao 3D/Street View (RF9). Configuravel para nao
    # depender de um provedor real por padrao; usada para montar o embed.
    streetview_base_url: str = "https://www.google.com/maps/embed/v1/streetview"

    # --- Flag de robustez para testes -------------------------------------
    db_configured_flag: bool = Field(default=False, exclude=True)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> object:
        """Aceita tambem string separada por virgula alem de lista JSON.

        Se o valor vier como string sem formato de lista JSON, divide por
        virgula e remove espacos, permitindo WANDERLUST_CORS_ORIGINS=
        "http://a,http://b" sem precisar de aspas/colchetes.
        """
        if isinstance(value, str):
            texto = value.strip()
            if not texto.startswith("["):
                return [item.strip() for item in texto.split(",") if item.strip()]
        return value

    @property
    def db_configured(self) -> bool:
        """Indica se ha informacao suficiente para conectar ao banco."""
        return all(
            value is not None
            for value in (self.db_server, self.db_name, self.db_user, self.db_password)
        )


@lru_cache
def get_settings() -> Settings:
    """Retorna a instancia unica de Settings (memoizada)."""
    return Settings()
