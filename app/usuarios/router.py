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
from app.core.deps import UsuarioAtual, requer_autenticacao, requer_permissao
from app.db.session import DatabaseNotConfiguredError
from app.integracoes.sms import default_sms_sender
from app.usuarios import repository
from app.usuarios.schemas import (
    AlterarStatusContaRequest,
    ContaAdminSaida,
    LoginDesafioResposta,
    LoginRequest,
    StatusConta,
    TokenResposta,
    UsuarioAtualizar,
    UsuarioCadastro,
    UsuarioSaida,
    Verificar2FARequest,
)
from app.usuarios.service import (
    AcaoModeracao,
    Codigo2FAInvalidoError,
    CredenciaisInvalidasError,
    Desafio2FAInvalidoError,
    avaliar_guarda_moderacao,
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
    except repository.UsuarioDuplicadoError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


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
# Self-service da PROPRIA conta do turista (FEAT-003).
# Protegido por Depends(requer_autenticacao) e operando SEMPRE sobre o
# ``id_passageiro`` do JWT (nunca um id vindo do path/corpo), de modo que o
# cliente so toca a propria conta.
# ---------------------------------------------------------------------------


def _id_do_token(usuario_atual: UsuarioAtual) -> int:
    """Extrai o id_passageiro do JWT ou levanta 401 para tokens antigos.

    Tokens emitidos antes da claim ``id`` nao identificam o passageiro; sem
    isso nao e possivel resolver "a propria conta", entao exigimos novo login.
    """
    if usuario_atual.id_passageiro is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Token sem identificacao do passageiro (claim 'id'). "
                "Faca login novamente."
            ),
        )
    return usuario_atual.id_passageiro


@router.get("/me", response_model=UsuarioSaida)
def ler_perfil(
    usuario_atual: UsuarioAtual = Depends(requer_autenticacao),
) -> UsuarioSaida:
    """Retorna o perfil do PROPRIO usuario logado (self-service).

    Opera sobre o id_passageiro do JWT; o cliente nunca informa um id.
    """
    id_passageiro = _id_do_token(usuario_atual)
    try:
        perfil = repository.buscar_usuario_por_id(id_passageiro)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    if perfil is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conta nao encontrada."
        )
    return perfil


@router.put("/me", response_model=UsuarioSaida)
def atualizar_perfil(
    dados: UsuarioAtualizar,
    usuario_atual: UsuarioAtual = Depends(requer_autenticacao),
) -> UsuarioSaida:
    """Atualiza o PROPRIO perfil do usuario logado (self-service).

    O schema ``UsuarioAtualizar`` nao expoe papel/status/cpf, entao o cliente
    nao consegue escalar privilegio nem alterar a identidade por esta rota
    (defense-in-depth, RNF3/LGPD). Opera sobre o id_passageiro do JWT.
    """
    id_passageiro = _id_do_token(usuario_atual)
    try:
        perfil = repository.atualizar_usuario(id_passageiro, dados)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    if perfil is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conta nao encontrada."
        )
    return perfil


@router.delete("/me", response_model=UsuarioSaida)
def excluir_perfil(
    usuario_atual: UsuarioAtual = Depends(requer_autenticacao),
) -> UsuarioSaida:
    """Encerra a PROPRIA conta via HARD DELETE (self-service).

    Decisao de produto ('hard delete de conta'): a linha de dbo.Usuario e
    REALMENTE removida pela procedure sp_excluir_usuario, que cascateia os
    dependentes em ordem segura de FK numa unica transacao (Avaliacao,
    Preferencia, Questionario_Resposta, a cadeia Passagem/Obtem/Venda,
    Conta_turista/Conta_colaborador e Credencial). O historico de compras
    daquele usuario e removido de proposito. A resposta mantem o mesmo shape
    (representacao da conta removida). Opera sobre o id_passageiro do JWT.
    """
    id_passageiro = _id_do_token(usuario_atual)
    try:
        perfil = repository.excluir_usuario(id_passageiro)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    if perfil is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conta nao encontrada."
        )
    return perfil


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


def _aplicar_guarda_moderacao(
    id_alvo: int,
    id_admin_atual: int,
    acao: AcaoModeracao,
    novo_status: StatusConta | None = None,
) -> ContaAdminSaida:
    """Carrega a conta alvo + contagem de admins e aplica a guarda anti-lockout.

    Centraliza o fluxo compartilhado por PATCH status e DELETE: busca a conta
    (404 se nao existir), conta os admins ativos e delega a decisao a funcao
    pura ``avaliar_guarda_moderacao``. Levanta 403 (auto-alvo) ou 409 (ultimo
    admin ativo) quando a operacao e negada. Retorna a conta alvo quando
    permitida, para o chamador seguir com a operacao.
    """
    try:
        alvo = repository.buscar_conta(id_alvo)
        if alvo is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conta nao encontrada.",
            )
        admins_ativos = repository.contar_admins_ativos()
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    decisao = avaliar_guarda_moderacao(
        id_alvo=id_alvo,
        id_admin_atual=id_admin_atual,
        papel_alvo=alvo.papel,
        acao=acao,
        admins_ativos=admins_ativos,
        novo_status=novo_status,
    )
    if not decisao.permitido:
        raise HTTPException(
            status_code=decisao.codigo_http or status.HTTP_409_CONFLICT,
            detail=decisao.motivo,
        )
    return alvo


@router.patch(
    "/admin/contas/{id_passageiro}/status",
    response_model=ContaAdminSaida,
    dependencies=[Depends(requer_permissao(Permissao.GERENCIAR_CONTAS))],
)
def alterar_status_conta(
    id_passageiro: int,
    dados: AlterarStatusContaRequest,
    usuario_atual: UsuarioAtual = Depends(requer_autenticacao),
) -> ContaAdminSaida:
    """Altera o status de uma conta: banir/denunciar/reativar (secao 4.1).

    Reativar e enviar ``novo_status = Ativo``. O ``motivo`` e opcional e serve
    para registro operacional; nao expoe nem altera dados pessoais da conta.

    Guarda anti-lockout: quando o novo status remove o admin do estado ativo
    (banir/denunciar), um admin nao pode moderar a PROPRIA conta (403) e o
    ultimo administrador ativo nao pode ser banido/denunciado (409). Reativar
    (Ativo) nunca e bloqueado.
    """
    id_admin = _id_do_token(usuario_atual)
    acao = (
        AcaoModeracao.REATIVAR
        if dados.novo_status == StatusConta.ATIVO
        else AcaoModeracao.BANIR
    )
    _aplicar_guarda_moderacao(
        id_alvo=id_passageiro,
        id_admin_atual=id_admin,
        acao=acao,
        novo_status=dados.novo_status,
    )

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
def excluir_conta(
    id_passageiro: int,
    usuario_atual: UsuarioAtual = Depends(requer_autenticacao),
) -> ContaAdminSaida:
    """Apaga uma conta via HARD DELETE (Gerenciar Contas, 4.1).

    Decisao de produto ('hard delete de conta'): a linha de dbo.Usuario e
    REALMENTE removida pela procedure sp_excluir_usuario, que cascateia os
    dependentes em ordem segura de FK numa unica transacao (Avaliacao,
    Preferencia, Questionario_Resposta, a cadeia Passagem/Obtem/Venda,
    Conta_turista/Conta_colaborador e Credencial). O historico de compras
    daquele usuario e removido de proposito. Retorna a representacao (sem dados
    pessoais) da conta removida, mantendo o shape da resposta.

    Guarda anti-lockout: um admin nao pode excluir a PROPRIA conta (403) e o
    ultimo administrador ativo nao pode ser excluido (409).
    """
    id_admin = _id_do_token(usuario_atual)
    _aplicar_guarda_moderacao(
        id_alvo=id_passageiro,
        id_admin_atual=id_admin,
        acao=AcaoModeracao.EXCLUIR,
    )

    try:
        conta = repository.excluir_conta(id_passageiro)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    if conta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conta nao encontrada."
        )
    return conta
