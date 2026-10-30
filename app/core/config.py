"""Configuracao da aplicacao lida de variaveis de ambiente / arquivo .env.

Todas as configuracoes sao opcionais na importacao: a aplicacao sobe e os
testes rodam sem um banco de dados vivo. A conexao com o SQL Server so e
aberta quando um recurso que precisa dela for efetivamente usado.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field
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

    # --- Flag de robustez para testes -------------------------------------
    db_configured_flag: bool = Field(default=False, exclude=True)

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
