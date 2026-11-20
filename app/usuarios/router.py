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

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.authz import Permissao
from app.core.deps import requer_permissao
from app.db.session import DatabaseNotConfiguredError
from app.integracoes.sms import default_sms_sender
from app.usuarios import repository
from app.usuarios.schemas import (
    AlterarStatusContaRequest,
    ContaAdminSaida,
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

    claims = decodificar_token(token)
    return TokenResposta(
        access_token=token,
        papel=claims["papel"],
        id_passageiro=claims.get("id"),
    )


# ---------------------------------------------------------------------------
# Gerenciar Contas (Administrador, secao 4.1 / RNF3 / LGPD).
# Exige a permissao GERENCIAR_CONTAS (403 para quem nao tem; 401 sem token).
# As respostas (ContaAdminSaida) NAO expoem cpf, senha ou demais dados
# pessoais: o admin modera contas, nao le/edita dados pessoais.
# ---------------------------------------------------------------------------


@router.get(
    "/admin/contas",
    response_model=List[ContaAdminSaida],
    dependencies=[Depends(requer_permissao(Permissao.GERENCIAR_CONTAS))],
)
def listar_contas() -> List[ContaAdminSaida]:
    """Lista as contas para moderacao (Gerenciar Contas, secao 4.1).

    Nao retorna dados pessoais sensiveis (cpf/senha/etc.), apenas o minimo
    para moderar: id, nome, email, papel e status.
    """
    try:
        return repository.listar_contas()
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc


@router.patch(
    "/admin/contas/{id_passageiro}/status",
    response_model=ContaAdminSaida,
    dependencies=[Depends(requer_permissao(Permissao.GERENCIAR_CONTAS))],
)
def alterar_status_conta(
    id_passageiro: int, dados: AlterarStatusContaRequest
) -> ContaAdminSaida:
    """Altera o status de uma conta: banir/denunciar/reativar (secao 4.1).

    Reativar e enviar ``novo_status = Ativo``. O ``motivo`` e opcional e serve
    para registro operacional; nao expoe nem altera dados pessoais da conta.
    """
    try:
        conta = repository.alterar_status_conta(id_passageiro, dados.novo_status)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    if conta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conta nao encontrada."
        )
    return conta


@router.delete(
    "/admin/contas/{id_passageiro}",
    response_model=ContaAdminSaida,
    dependencies=[Depends(requer_permissao(Permissao.GERENCIAR_CONTAS))],
)
def excluir_conta(id_passageiro: int) -> ContaAdminSaida:
    """Apaga uma conta via SOFT DELETE/anonimizacao (Gerenciar Contas, 4.1).

    Escolha de projeto (documentada tambem no repository e nas FEAT findings):
    as FKs de dbo.Venda sao ON DELETE NO ACTION, entao um hard delete de um
    Usuario com vendas violaria as FKs e destruiria o historico financeiro.
    Por isso a conta e marcada como 'Banido' e tem os campos pessoais
    anonimizados, preservando a integridade das vendas e alinhando-se a LGPD.
    Retorna a visao (sem dados pessoais) da conta anonimizada.
    """
    try:
        conta = repository.excluir_conta(id_passageiro)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    if conta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conta nao encontrada."
        )
    return conta
