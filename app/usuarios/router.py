"""Rotas HTTP de autenticacao (RF1/RF2).

Endpoints:
  POST /auth/cadastro        - cadastro de usuario (RF1)
  POST /auth/login           - etapa 1 do 2FA: valida senha e envia codigo
  POST /auth/2fa/verificar   - etapa 2 do 2FA: valida codigo e emite JWT

A persistencia passa pela camada ``app.db``. Sem banco configurado,
``DatabaseNotConfiguredError`` e convertido em HTTP 503 com mensagem clara. A
logica central (hash, 2FA, authz) vive em funcoes puras testaveis sem DB.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.db.session import DatabaseNotConfiguredError
from app.integracoes.sms import default_sms_sender
from app.usuarios import repository
from app.usuarios.schemas import (
    LoginDesafioResposta,
    LoginRequest,
    TokenResposta,
    UsuarioCadastro,
    UsuarioSaida,
    Verificar2FARequest,
)
from app.usuarios.service import (
    Codigo2FAInvalidoError,
    CredenciaisInvalidasError,
    concluir_login,
    iniciar_login,
)

router = APIRouter(prefix="/auth", tags=["autenticacao"])


def _erro_db_indisponivel() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "Banco de dados nao configurado. Configure as variaveis "
            "WANDERLUST_DB_* para habilitar a persistencia."
        ),
    )


@router.post(
    "/cadastro",
    response_model=UsuarioSaida,
    status_code=status.HTTP_201_CREATED,
)
def cadastrar(dados: UsuarioCadastro) -> UsuarioSaida:
    """Cadastra um novo usuario (RF1)."""
    try:
        return repository.criar_usuario(dados)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc


@router.post("/login", response_model=LoginDesafioResposta)
def login(dados: LoginRequest) -> LoginDesafioResposta:
    """Etapa 1 do login (RF2): valida senha e dispara o codigo 2FA por SMS."""
    try:
        credencial = repository.buscar_credencial_por_email(str(dados.email))
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    try:
        iniciar_login(credencial, dados.senha, default_sms_sender)
    except CredenciaisInvalidasError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc
    return LoginDesafioResposta()


@router.post("/2fa/verificar", response_model=TokenResposta)
def verificar_2fa(dados: Verificar2FARequest) -> TokenResposta:
    """Etapa 2 do login (RF2): valida o codigo 2FA e emite o token JWT."""
    try:
        credencial = repository.buscar_credencial_por_email(str(dados.email))
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    try:
        token = concluir_login(credencial, dados.codigo)
    except CredenciaisInvalidasError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc
    except Codigo2FAInvalidoError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    assert credencial is not None  # garantido por concluir_login acima
    return TokenResposta(access_token=token, papel=credencial.papel)
