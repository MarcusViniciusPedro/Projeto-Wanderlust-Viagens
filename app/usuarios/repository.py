"""Acesso a dados de usuarios/credenciais via camada app.db (SQL Server).

Sem banco configurado, ``get_connection`` levanta
``DatabaseNotConfiguredError``, que os endpoints convertem em erro HTTP claro.
A logica central de autenticacao fica em ``service.py`` (funcoes puras), de
forma que os testes nao dependem deste modulo nem de um DB vivo.
"""

from __future__ import annotations

from typing import List, Optional

import pymssql

from app.core.authz import Papel
from app.core.config import Settings
from app.core.security import gerar_segredo_totp, hash_senha
from app.db.session import get_connection


class UsuarioDuplicadoError(RuntimeError):
    """E-mail ou CPF já cadastrado (violação de UNIQUE na tabela Usuario)."""
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
        try:
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
        except pymssql.IntegrityError as exc:
            conn.rollback()
            texto = str(exc).lower()
            if "cpf" in texto:
                campo = "CPF"
            elif "email" in texto:
                campo = "e-mail"
            else:
                campo = "e-mail ou CPF"
            raise UsuarioDuplicadoError(
                f"Já existe um cadastro com este {campo}."
            ) from exc
        id_passageiro = cursor.fetchone()[0]
        cursor.execute(
            """
            INSERT INTO dbo.Credencial (id_usuario, senha_hash, totp_secret, two_factor)
            VALUES (%s, %s, %s, 0)
            """,
            (id_passageiro, hash_senha(dados.senha), gerar_segredo_totp()),
        )
        # Especializacao: cadastro publico cria sempre Turista, entao insere a
        # linha correspondente em Conta_turista (necessaria para registrar vendas,
        # cujo fk_conta_turista referencia essa tabela). Papeis de colaborador
        # (Agente/Administrador) exigem 'cargo' e sao atribuidos administrativamente,
        # nao por auto-cadastro, portanto nao recebem especializacao aqui.
        if dados.papel == Papel.TURISTA:
            cursor.execute(
                "INSERT INTO dbo.Conta_turista (id_turista) VALUES (%s)",
                (id_passageiro,),
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

    So envia ao banco os campos efetivamente informados (presentes E nao-None).
    O schema ``UsuarioAtualizar`` nao expoe papel/status/cpf, entao mesmo que o
    cliente tente injeta-los no corpo, eles sao ignorados (defense-in-depth,
    RNF3). Sem nenhum campo para atualizar, apenas devolve o perfil atual.
    Retorna None quando o id nao existe.

    A atualizacao parcial e ATOMICA no banco: a procedure
    ``dbo.sp_atualizar_usuario`` recebe NULL ("nao alterar") para as colunas
    nao enviadas e aplica ``COALESCE(@param, coluna)`` num unico UPDATE. Nao ha
    leitura previa do perfil, o que elimina o read-modify-write em conexoes
    separadas que abria janela de lost-update entre atualizacoes concorrentes.
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
    pares = {c: v for c, v in atualizacoes.items() if c in _COLUNAS_EDITAVEIS}
    if not pares:
        return buscar_usuario_por_id(id_passageiro, settings)

    # Envia NULL para as colunas nao enviadas; a procedure as preserva via
    # COALESCE. Assim o UPDATE das colunas do usuario e um unico statement
    # atomico, sem depender de nenhum valor lido antes em outra conexao.
    valores = (
        id_passageiro,
        pares.get("nome"),
        pares.get("nome_social"),
        pares.get("pronome"),
        pares.get("cep"),
        pares.get("email"),
        pares.get("telefone"),
    )

    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            EXEC dbo.sp_atualizar_usuario
                @id_passageiro=%s,
                @nome=%s,
                @nome_social=%s,
                @pronome=%s,
                @cep=%s,
                @email=%s,
                @telefone=%s
            """,
            valores,
        )
        # Sob SET NOCOUNT ON o cursor.rowcount nao e confiavel: a procedure
        # devolve SELECT @@ROWCOUNT como ultima instrucao.
        afetadas = cursor.fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    if afetadas == 0:
        return None
    # Leitura APOS a escrita so para montar a resposta (UsuarioSaida). Isso nao
    # e um read-modify-write: nenhum valor lido aqui participa do UPDATE, entao
    # nao reintroduz a janela de lost-update.
    return buscar_usuario_por_id(id_passageiro, settings)


def excluir_usuario(
    id_passageiro: int, settings: Optional[Settings] = None
) -> Optional[UsuarioSaida]:
    """Encerra a PROPRIA conta via HARD DELETE (decisao de produto).

    A linha de dbo.Usuario e REALMENTE removida: a procedure
    ``dbo.sp_excluir_usuario`` apaga, numa unica transacao e em ordem segura de
    FK, todos os dependentes (Avaliacao/Preferencia/Questionario_Resposta, a
    cadeia Passagem/Obtem/Venda, Conta_turista/Conta_colaborador, Credencial) e
    por fim o proprio Usuario. O historico de compras daquele usuario e
    removido de proposito, sobrepondo a antiga politica de soft delete (LGPD).

    Como a linha deixa de existir, NAO chamamos ``buscar_usuario_por_id`` apos
    o delete. Quando @@ROWCOUNT > 0, devolvemos uma representacao da conta
    removida (nome 'Conta removida', campos pessoais nulos) montada a partir do
    id conhecido, mantendo o shape da resposta para o frontend. Retorna None
    quando @@ROWCOUNT == 0 (id nao existia).
    """
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute("EXEC dbo.sp_excluir_usuario %s", (id_passageiro,))
        # Procedure sob SET NOCOUNT ON devolve SELECT @@ROWCOUNT; leia dai.
        afetadas = cursor.fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    if afetadas == 0:
        return None
    # A linha foi apagada; nao ha o que buscar. Monta a representacao da conta
    # removida a partir do id, com campos pessoais nulos.
    return UsuarioSaida(
        id_passageiro=id_passageiro,
        nome="Conta removida",
        nome_social=None,
        pronome=None,
        email=None,
        telefone=None,
        papel=Papel.TURISTA,
    )


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
        cursor.execute("EXEC dbo.sp_listar_usuarios")
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
    """Apaga uma conta via HARD DELETE (decisao de produto).

    Usa a MESMA procedure do self-service: ``dbo.sp_excluir_usuario`` remove de
    verdade a linha de dbo.Usuario, cascateando os dependentes em ordem segura
    de FK numa unica transacao (Avaliacao/Preferencia/Questionario_Resposta,
    cadeia Passagem/Obtem/Venda, Conta_turista/Conta_colaborador, Credencial) e,
    por fim, o Usuario. O historico de compras daquele usuario e removido de
    proposito, sobrepondo a antiga politica de soft delete (LGPD).

    Como a linha deixa de existir, NAO chamamos ``buscar_conta`` apos o delete.
    Quando @@ROWCOUNT > 0, devolvemos uma representacao da conta removida (nome
    'Conta removida', status 'Banido', email nulo) montada a partir do id.
    Retorna None quando @@ROWCOUNT == 0 (id nao existia).
    """
    conn = get_connection(settings)
    try:
        cursor = conn.cursor()
        # Mesma procedure do self-service: a semantica de hard delete e identica.
        cursor.execute("EXEC dbo.sp_excluir_usuario %s", (id_passageiro,))
        # Procedure sob SET NOCOUNT ON devolve SELECT @@ROWCOUNT; leia dai.
        afetadas = cursor.fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    if afetadas == 0:
        return None
    # A linha foi apagada; nao ha o que buscar. Monta a representacao (de
    # moderacao) da conta removida a partir do id.
    return ContaAdminSaida(
        id_passageiro=id_passageiro,
        nome="Conta removida",
        email=None,
        papel=Papel.TURISTA,
        status=StatusConta.BANIDO,
    )
