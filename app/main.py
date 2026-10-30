"""Ponto de entrada da API FastAPI da Wanderlust Viagens.

A instancia da aplicacao e criada aqui. Routers dos modulos de dominio
(usuarios, catalogo, vendas, recomendacao, integracoes) serao incluidos
conforme forem implementados nas proximas features. A importacao deste
modulo NAO abre conexao com banco de dados.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.catalogo.router import router as catalogo_router
from app.core.config import get_settings
from app.estatisticas.router import router as estatisticas_router
from app.recomendacao.router import router as recomendacao_router
from app.usuarios.router import router as usuarios_router
from app.vendas.router import router as vendas_router

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


# Routers dos microsservicos. Novos modulos sao registrados aqui conforme
# forem implementados nas proximas features.
app.include_router(usuarios_router)
app.include_router(catalogo_router)
app.include_router(vendas_router)
app.include_router(recomendacao_router)
app.include_router(estatisticas_router)
