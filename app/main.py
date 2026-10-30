"""Ponto de entrada da API FastAPI da Wanderlust Viagens.

A instancia da aplicacao e criada aqui. Routers dos modulos de dominio
(usuarios, catalogo, vendas, recomendacao, integracoes) serao incluidos
conforme forem implementados nas proximas features. A importacao deste
modulo NAO abre conexao com banco de dados.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="API back-end da agencia de viagens Wanderlust.",
)


@app.get("/health", tags=["infra"])
def health() -> dict[str, str]:
    """Verificacao de saude da aplicacao (nao depende do banco)."""
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}


# Os routers dos microsservicos serao registrados aqui nas proximas features:
# app.include_router(usuarios.router)
# app.include_router(catalogo.router)
# app.include_router(vendas.router)
# app.include_router(recomendacao.router)
