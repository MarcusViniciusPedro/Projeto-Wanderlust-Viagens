"""Acesso a dados de usuarios/credenciais via camada app.db (SQL Server).

Sem banco configurado, ``get_connection`` levanta
``DatabaseNotConfiguredError``, que os endpoints convertem em erro HTTP claro.
A logica central de autenticacao fica em ``service.py`` (funcoes puras), de
forma que os testes nao dependem deste modulo nem de um DB vivo.
"""

from __future__ import annotations

from typing import List, Optional

from app.core.authz import Papel
from app.core.config import Settings
from app.core.security import gerar_segredo_totp, hash_senha
from app.db.session import get_connection
from app.usuarios.schemas import (
    ContaAdminSaida,
    StatusConta,
    UsuarioAtualizar,
    UsuarioCadastro,
    UsuarioSaida,
)
from app.usuarios.service import CredencialUsuario


def criar_usuario(
    dados: UsuarioCadastro, settings: Optional[Settings] = None
) -> UsuarioSaida:
    """Insere um usuario e sua credencial (senha com hash, segredo TOTP)."""
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO dbo.Usuario
                (nome, nome_social, pronome, data_nascimento, cpf, cep,
                 email, telefone, papel)
            OUTPUT INSERTED.id_passageiro
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                dados.nome,
                dados.nome_social,
                dados.pronome,
                dados.data_nascimento,
                dados.cpf,
                dados.cep,
                str(dados.email),
                dados.telefone,
                dados.papel.value,
            ),
        )
        id_passageiro = cursor.fetchone()[0]
        cursor.execute(
            """
            INSERT INTO dbo.Credencial (id_usuario, senha_hash, totp_secret, two_factor)
            VALUES (%s, %s, %s, 1)
            """,
            (id_passageiro, hash_senha(dados.senha), gerar_segredo_totp()),
        )
        conn.commit()
    finally:
        conn.close()

    return UsuarioSaida(
        id_passageiro=id_passageiro,
        nome=dados.nome,
        nome_social=dados.nome_social,
        pronome=dados.pronome,
        email=str(dados.email),
        telefone=dados.telefone,
        papel=dados.papel,
    )


def buscar_credencial_por_email(
    email: str, settings: Optional[Settings] = None
) -> Optional[CredencialUsuario]:
    """Carrega a credencial de autenticacao de um usuario pelo email."""
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT u.id_passageiro, u.email, c.senha_hash, c.totp_secret,
                   u.papel, u.telefone, c.two_factor
            FROM dbo.Usuario u
            JOIN dbo.Credencial c ON c.id_usuario = u.id_passageiro
            WHERE u.email = %s
            """,
            (email,),
        )
        linha = cursor.fetchone()
    finally:
        conn.close()

    if linha is None:
        return None
    return CredencialUsuario(
        id_usuario=linha[0],
        email=linha[1],
        senha_hash=linha[2],
        totp_secret=linha[3],
        papel=Papel(linha[4]),
        telefone=linha[5],
        two_factor=bool(linha[6]),
    )


# ---------------------------------------------------------------------------
# Self-service do proprio turista (FEAT-003): ler/atualizar/excluir a PROPRIA
# conta. Todas as operacoes recebem ``id_passageiro`` vindo do JWT (nunca do
# path), garantindo que o cliente so toca a propria conta.
# ---------------------------------------------------------------------------


def buscar_usuario_por_id(
    id_passageiro: int, settings: Optional[Settings] = None
) -> Optional[UsuarioSaida]:
    """Carrega o perfil publico de um usuario pelo id, ou None se nao existir."""
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id_passageiro, nome, nome_social, pronome, email, telefone, papel
            FROM dbo.Usuario
            WHERE id_passageiro = %s
            """,
            (id_passageiro,),
        )
        linha = cursor.fetchone()
    finally:
        conn.close()

    if linha is None:
        return None
    return UsuarioSaida(
        id_passageiro=linha[0],
        nome=linha[1],
        nome_social=linha[2],
        pronome=linha[3],
        email=linha[4],
        telefone=linha[5],
        papel=Papel(linha[6]),
    )


def atualizar_usuario(
    id_passageiro: int,
    dados: UsuarioAtualizar,
    settings: Optional[Settings] = None,
) -> Optional[UsuarioSaida]:
    """Atualiza os campos editaveis do proprio perfil (atualizacao parcial).

    So monta o UPDATE com os campos efetivamente enviados (nao-None). O schema
    ``UsuarioAtualizar`` nao expoe papel/status/cpf, entao mesmo que o cliente
    tente injeta-los no corpo, eles sao ignorados (defense-in-depth, RNF3). Sem
    nenhum campo para atualizar, apenas devolve o perfil atual. Retorna None
    quando o id nao existe.
    """
    atualizacoes = dados.model_dump(exclude_unset=True, exclude_none=True)
    if not atualizacoes:
        return buscar_usuario_por_id(id_passageiro, settings)

    # Lista branca de colunas editaveis: espelha exatamente os campos do schema
    # e protege contra qualquer chave inesperada no dicionario.
    _COLUNAS_EDITAVEIS = {
        "nome",
        "nome_social",
        "pronome",
        "cep",
        "email",
        "telefone",
    }
    pares = [(c, v) for c, v in atualizacoes.items() if c in _COLUNAS_EDITAVEIS]
    if not pares:
        return buscar_usuario_por_id(id_passageiro, settings)

    set_clause = ", ".join(f"{coluna} = %s" for coluna, _ in pares)
    valores = [valor for _, valor in pares]
    valores.append(id_passageiro)

    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE dbo.Usuario SET {set_clause} WHERE id_passageiro = %s",
            tuple(valores),
        )
        afetadas = cursor.rowcount
        conn.commit()
    finally:
        conn.close()

    if afetadas == 0:
        return None
    return buscar_usuario_por_id(id_passageiro, settings)


def excluir_usuario(
    id_passageiro: int, settings: Optional[Settings] = None
) -> Optional[UsuarioSaida]:
    """Encerra a PROPRIA conta via SOFT DELETE/anonimizacao (LGPD/RNF3).

    Mesma politica da exclusao administrativa (FEAT-002): as FKs de dbo.Venda
    para Conta_turista sao ON DELETE NO ACTION, entao um hard delete de um
    Usuario com vendas violaria as FKs e apagaria o historico financeiro. Em
    vez disso a conta e marcada como 'Banido' (estado terminal) e os campos
    pessoais sao anonimizados, preservando a integridade das vendas. Retorna a
    visao publica da conta anonimizada ou None quando o id nao existe.
    """
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE dbo.Usuario
            SET status = %s,
                nome = %s,
                nome_social = NULL,
                pronome = NULL,
                email = NULL,
                telefone = NULL,
                cep = NULL,
                cpf = %s
            WHERE id_passageiro = %s
            """,
            (
                StatusConta.BANIDO.value,
                "Conta removida",
                f"removido-{id_passageiro}",
                id_passageiro,
            ),
        )
        afetadas = cursor.rowcount
        conn.commit()
    finally:
        conn.close()

    if afetadas == 0:
        return None
    return buscar_usuario_por_id(id_passageiro, settings)


# ---------------------------------------------------------------------------
# Gerenciar Contas (Administrador, secao 4.1 / RNF3 / LGPD).
# As leituras abaixo projetam SOMENTE campos nao sensiveis (id, nome, email,
# papel, status). cpf, senha, data de nascimento, cep e telefone NUNCA sao
# retornados aqui: o admin modera contas, nao le/edita dados pessoais.
# ---------------------------------------------------------------------------


def listar_contas(settings: Optional[Settings] = None) -> List[ContaAdminSaida]:
    """Lista contas para moderacao, sem dados pessoais sensiveis (RNF3)."""
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id_passageiro, nome, email, papel, status
            FROM dbo.Usuario
            ORDER BY id_passageiro
            """
        )
        linhas = cursor.fetchall()
    finally:
        conn.close()

    return [
        ContaAdminSaida(
            id_passageiro=linha[0],
            nome=linha[1],
            email=linha[2],
            papel=Papel(linha[3]),
            status=StatusConta(linha[4]),
        )
        for linha in linhas
    ]


def buscar_conta(
    id_passageiro: int, settings: Optional[Settings] = None
) -> Optional[ContaAdminSaida]:
    """Carrega uma conta (visao de moderacao) pelo id, ou None se nao existir."""
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id_passageiro, nome, email, papel, status
            FROM dbo.Usuario
            WHERE id_passageiro = %s
            """,
            (id_passageiro,),
        )
        linha = cursor.fetchone()
    finally:
        conn.close()

    if linha is None:
        return None
    return ContaAdminSaida(
        id_passageiro=linha[0],
        nome=linha[1],
        email=linha[2],
        papel=Papel(linha[3]),
        status=StatusConta(linha[4]),
    )


def contar_admins_ativos(settings: Optional[Settings] = None) -> int:
    """Conta administradores com status 'Ativo' (guarda anti-lockout).

    Usado para impedir que o ultimo administrador ativo seja banido/excluido.
    """
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM dbo.Usuario
            WHERE papel = %s AND status = %s
            """,
            (Papel.ADMINISTRADOR.value, StatusConta.ATIVO.value),
        )
        linha = cursor.fetchone()
    finally:
        conn.close()

    return int(linha[0]) if linha else 0


def alterar_status_conta(
    id_passageiro: int,
    novo_status: StatusConta,
    settings: Optional[Settings] = None,
) -> Optional[ContaAdminSaida]:
    """Altera o status de uma conta (banir/denunciar/reativar).

    Retorna a visao atualizada da conta ou None quando o id nao existe.
    """
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE dbo.Usuario
            SET status = %s
            WHERE id_passageiro = %s
            """,
            (novo_status.value, id_passageiro),
        )
        afetadas = cursor.rowcount
        conn.commit()
    finally:
        conn.close()

    if afetadas == 0:
        return None
    return buscar_conta(id_passageiro, settings)


def excluir_conta(
    id_passageiro: int, settings: Optional[Settings] = None
) -> Optional[ContaAdminSaida]:
    """Apaga uma conta via SOFT DELETE (anonimizacao), alinhado a LGPD/RNF3.

    As FKs de dbo.Venda para Conta_turista/Conta_colaborador usam ON DELETE
    NO ACTION; um hard delete de um Usuario com vendas violaria as FKs e
    destruiria o historico financeiro. Em vez disso, a conta e marcada como
    'Banido' (status terminal) e os campos pessoais sao anonimizados (nome,
    email, cpf, cep, telefone, nome_social, pronome), preservando a integridade
    referencial das vendas. Retorna a visao da conta anonimizada ou None quando
    o id nao existe.
    """
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE dbo.Usuario
            SET status = %s,
                nome = %s,
                nome_social = NULL,
                pronome = NULL,
                email = NULL,
                telefone = NULL,
                cep = NULL,
                cpf = %s
            WHERE id_passageiro = %s
            """,
            (
                StatusConta.BANIDO.value,
                "Conta removida",
                f"removido-{id_passageiro}",
                id_passageiro,
            ),
        )
        afetadas = cursor.rowcount
        conn.commit()
    finally:
        conn.close()

    if afetadas == 0:
        return None
    return buscar_conta(id_passageiro, settings)
