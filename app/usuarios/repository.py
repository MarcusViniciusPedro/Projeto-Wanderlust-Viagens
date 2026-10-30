"""Acesso a dados de usuarios/credenciais via camada app.db (SQL Server).

Sem banco configurado, ``get_connection`` levanta
``DatabaseNotConfiguredError``, que os endpoints convertem em erro HTTP claro.
A logica central de autenticacao fica em ``service.py`` (funcoes puras), de
forma que os testes nao dependem deste modulo nem de um DB vivo.
"""

from __future__ import annotations

from typing import Optional

from app.core.authz import Papel
from app.core.config import Settings
from app.core.security import gerar_segredo_totp, hash_senha
from app.db.session import get_connection
from app.usuarios.schemas import UsuarioCadastro, UsuarioSaida
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
