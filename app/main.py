"""Ponto de entrada da API FastAPI da Wanderlust Viagens.

A instancia da aplicacao e criada aqui. Routers dos modulos de dominio
(usuarios, catalogo, vendas, recomendacao, integracoes) serao incluidos
conforme forem implementados nas proximas features. A importacao deste
modulo NAO abre conexao com banco de dados.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

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

# CORS: permite que o front-end estatico (servido em outra origem/porta) chame
# a API pelo navegador. As origens vem de settings.cors_origins
# (WANDERLUST_CORS_ORIGINS). Usamos allow_credentials=True, portanto nao
# usamos wildcard '*' em allow_origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["infra"])
def health() -> dict[str, str]:
    """Verificacao de saude da aplicacao (nao depende do banco)."""
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}


@app.get("/health/db", tags=["infra"])
def health_db() -> dict[str, str]:
    """Verifica a conectividade com o banco sem exigir um DB vivo.

    Se o banco nao estiver configurado, responde 503 (mesma semantica de
    DatabaseNotConfiguredError). Se estiver configurado, tenta abrir uma
    conexao e executar um SELECT 1 leve; em caso de falha, responde 503 com
    estado 'degradado'. Importa o driver/conexao de forma preguicosa para nao
    exigir pymssql na importacao do modulo.
    """
    if not settings.db_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Banco de dados nao configurado. Defina as variaveis "
                "WANDERLUST_DB_SERVER, WANDERLUST_DB_NAME, WANDERLUST_DB_USER "
                "e WANDERLUST_DB_PASSWORD."
            ),
        )

    from app.db.session import get_connection  # import preguicoso

    try:
        conexao = get_connection(settings)
        try:
            cursor = conexao.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
        finally:
            conexao.close()
    except Exception as exc:  # pragma: no cover - depende de DB vivo
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Banco de dados indisponivel (degradado): {exc}",
        ) from exc

    return {"status": "ok", "db": "conectado"}


# Routers dos microsservicos. Novos modulos sao registrados aqui conforme
# forem implementados nas proximas features.
app.include_router(usuarios_router)
app.include_router(catalogo_router)
app.include_router(vendas_router)
app.include_router(recomendacao_router)
app.include_router(estatisticas_router)
