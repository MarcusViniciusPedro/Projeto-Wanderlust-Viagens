"""Camada de autorizacao HTTP (dependencies FastAPI).

Esta e a unica ponte entre o JWT (app.core.security) e a matriz de permissoes
pura (app.core.authz). Nenhuma regra de permissao e redefinida aqui: as
dependencies apenas extraem o portador (Bearer), decodificam o token, montam um
``UsuarioAtual`` leve e delegam a autorizacao para ``app.core.authz``.

Nao abre conexao de banco: lida somente com JWT e com a matriz pura de papeis,
de modo que a app sobe e os testes rodam sem SQL Server vivo.

Codigos HTTP:
  - 401 para token ausente ou invalido (nao autenticado).
  - 403 para autenticado sem papel/permissao exigidos (PermissaoNegadaError).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.authz import Papel, Permissao, PermissaoNegadaError, exigir_permissao
from app.core.security import TokenInvalidoError, decodificar_token

# auto_error=False: deixamos a decisao de 401 explicita e com mensagem em
# Portugues, em vez do erro padrao do HTTPBearer.
_portador = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class UsuarioAtual:
    """Identidade leve do usuario autenticado, derivada do JWT.

    ``id_passageiro`` pode ser None em tokens antigos (emitidos antes da claim
    ``id``); ``papel`` e sempre resolvido para o enum Papel.
    """

    papel: Papel
    id_passageiro: Optional[int] = None


def requer_autenticacao(
    credenciais: Optional[HTTPAuthorizationCredentials] = Depends(_portador),
) -> UsuarioAtual:
    """Exige um Bearer JWT valido e retorna o ``UsuarioAtual`` correspondente.

    Levanta HTTP 401 quando o header Authorization esta ausente ou o token e
    invalido/expirado. O papel vem da claim ``papel`` e o id do passageiro da
    claim ``id`` (opcional).
    """
    if credenciais is None or not credenciais.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais de autenticacao ausentes.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decodificar_token(credenciais.credentials)
    except TokenInvalidoError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    try:
        papel = Papel(payload.get("papel"))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token sem papel valido.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    id_bruto = payload.get("id")
    id_passageiro = int(id_bruto) if id_bruto is not None else None

    return UsuarioAtual(papel=papel, id_passageiro=id_passageiro)


def requer_papel(*papeis: Papel):
    """Fabrica uma dependency que exige um dos ``papeis`` informados.

    Primeiro autentica (401 se nao autenticado) e depois verifica o papel; se o
    papel do usuario nao estiver entre os exigidos, levanta HTTP 403. Util para
    gates simples por papel (ex.: somente Administrador).
    """

    def _dependency(
        usuario: UsuarioAtual = Depends(requer_autenticacao),
    ) -> UsuarioAtual:
        if usuario.papel not in papeis:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Papel sem permissao para acessar este recurso.",
            )
        return usuario

    return _dependency


def requer_permissao(permissao: Permissao):
    """Fabrica uma dependency que exige uma ``permissao`` da matriz (secao 4.1).

    Autentica (401 se nao autenticado) e delega a verificacao a
    ``app.core.authz.exigir_permissao``, reutilizando a MATRIZ_PERMISSOES sem
    redefinir regras. Converte ``PermissaoNegadaError`` em HTTP 403.
    """

    def _dependency(
        usuario: UsuarioAtual = Depends(requer_autenticacao),
    ) -> UsuarioAtual:
        try:
            exigir_permissao(usuario.papel, permissao)
        except PermissaoNegadaError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(exc),
            ) from exc
        return usuario

    return _dependency
