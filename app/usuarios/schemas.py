"""Modelos Pydantic (schemas) do modulo de usuarios.

Inclui campos de design inclusivo (``nome_social`` e ``pronome``, RNF1) e o
enum de papel reaproveitado de ``app.core.authz`` para manter consistencia com
os valores do banco de dados ('Turista', 'Agente', 'Administrador').
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field

from app.core.authz import Papel

# Validacao leve de e-mail sem depender de pacote externo (email-validator).
# Suficiente para o escopo de back-end; a validacao definitiva fica no banco.
_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

__all__ = [
    "Papel",
    "UsuarioCadastro",
    "UsuarioSaida",
    "LoginRequest",
    "LoginDesafioResposta",
    "Verificar2FARequest",
    "TokenResposta",
]


class UsuarioCadastro(BaseModel):
    """Dados de entrada para cadastro de usuario (RF1)."""

    nome: str = Field(min_length=1, max_length=150)
    data_nascimento: date
    cpf: str = Field(min_length=11, max_length=14)
    email: str = Field(max_length=254, pattern=_EMAIL_PATTERN)
    senha: str = Field(min_length=8, max_length=128)
    # Design inclusivo (RNF1): opcionais, respeitados na exibicao.
    nome_social: Optional[str] = Field(default=None, max_length=150)
    pronome: Optional[str] = Field(default=None, max_length=30)
    cep: Optional[str] = Field(default=None, max_length=9)
    telefone: Optional[str] = Field(default=None, max_length=20)
    papel: Papel = Papel.TURISTA


class UsuarioSaida(BaseModel):
    """Representacao publica de um usuario (sem dados sensiveis)."""

    id_passageiro: int
    nome: str
    nome_social: Optional[str] = None
    pronome: Optional[str] = None
    email: Optional[str] = None
    telefone: Optional[str] = None
    papel: Papel

    @property
    def nome_exibicao(self) -> str:
        """Nome a exibir: prioriza o nome social quando informado (RNF1)."""
        return self.nome_social or self.nome


class LoginRequest(BaseModel):
    """Etapa 1 do login: credenciais de acesso (RF1/RF2)."""

    email: str = Field(max_length=254, pattern=_EMAIL_PATTERN)
    senha: str


class LoginDesafioResposta(BaseModel):
    """Resposta da etapa 1 do login (RF2).

    ``token_desafio`` reamarra a etapa 2 a etapa 1: foi emitido apenas apos a
    senha ser validada e precisa ser reapresentado em ``POST /auth/2fa/verificar``
    junto com o codigo. Assim, nao e possivel obter o JWT so com e-mail + codigo.
    """

    desafio_2fa: bool = True
    token_desafio: str
    detalhe: str = "Codigo de verificacao enviado por SMS."


class Verificar2FARequest(BaseModel):
    """Etapa 2 do login: desafio da etapa 1 + codigo 2FA (RF2).

    O e-mail NAO e aceito aqui de proposito: a identidade vem do
    ``token_desafio`` (claim ``sub``), que so e emitido apos a senha ser
    validada na etapa 1.
    """

    token_desafio: str
    codigo: str


class TokenResposta(BaseModel):
    """Resposta com o token de acesso emitido apos o 2FA."""

    access_token: str
    token_type: str = "bearer"
    papel: Papel
