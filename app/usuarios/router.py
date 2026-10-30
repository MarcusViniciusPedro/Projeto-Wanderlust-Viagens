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
    Desafio2FAInvalidoError,
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
    """Etapa 1 do login (RF2): valida senha e dispara o codigo 2FA por SMS.

    Em caso de sucesso devolve um ``token_desafio`` de curta duracao que a
    etapa 2 precisa reapresentar. Sem ele, nao e possivel concluir o login.
    """
    try:
        credencial = repository.buscar_credencial_por_email(str(dados.email))
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    try:
        resultado = iniciar_login(credencial, dados.senha, default_sms_sender)
    except CredenciaisInvalidasError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc
    return LoginDesafioResposta(token_desafio=resultado.token_desafio)


@router.post("/2fa/verificar", response_model=TokenResposta)
def verificar_2fa(dados: Verificar2FARequest) -> TokenResposta:
    """Etapa 2 do login (RF2): valida o desafio + codigo 2FA e emite o JWT.

    A identidade do usuario vem do ``token_desafio`` emitido na etapa 1 (apos
    a senha), nao de um e-mail arbitrario. A busca da credencial e injetada no
    service, que extrai o e-mail do proprio token.
    """

    def carregar(email: str):
        return repository.buscar_credencial_por_email(email)

    try:
        token = concluir_login(dados.token_desafio, dados.codigo, carregar)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc
    except Desafio2FAInvalidoError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc
    except CredenciaisInvalidasError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc
    except Codigo2FAInvalidoError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    from app.core.security import decodificar_token

    papel = decodificar_token(token)["papel"]
    return TokenResposta(access_token=token, papel=papel)
