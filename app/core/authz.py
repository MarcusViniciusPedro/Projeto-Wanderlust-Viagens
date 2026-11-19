"""Controle de acesso por papel (secao 4.1 do documento, RNF3).

Define os papeis do sistema e a matriz de permissoes associada a cada um. A
matriz e uma estrutura de dados pura e testavel, independente de HTTP ou banco.

Mapeamento da secao 4.1:
  - Turista: cadastrar-se, consultar pacotes, reservar, comprar.
  - Agente de Viagens: reservar, emitir passagem.
  - Administrador: gerenciar catalogo, agendar, gerenciar contas.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, FrozenSet


class Papel(str, Enum):
    """Papeis de usuario. Os valores coincidem com o CHECK do banco de dados
    (coluna ``Usuario.papel``: 'Turista', 'Agente', 'Administrador')."""

    TURISTA = "Turista"
    AGENTE = "Agente"  # Agente de Viagens
    ADMINISTRADOR = "Administrador"


class Permissao(str, Enum):
    """Permissoes/acoes controladas (secao 4.1)."""

    CADASTRAR = "cadastrar"
    CONSULTAR_PACOTES = "consultar_pacotes"
    RESERVAR = "reservar"
    COMPRAR = "comprar"
    EMITIR_PASSAGEM = "emitir_passagem"
    GERENCIAR_CATALOGO = "gerenciar_catalogo"
    AGENDAR = "agendar"
    GERENCIAR_CONTAS = "gerenciar_contas"


# Matriz de permissoes por papel (secao 4.1). Estrutura pura e testavel.
MATRIZ_PERMISSOES: Dict[Papel, FrozenSet[Permissao]] = {
    Papel.TURISTA: frozenset(
        {
            Permissao.CADASTRAR,
            Permissao.CONSULTAR_PACOTES,
            Permissao.RESERVAR,
            Permissao.COMPRAR,
        }
    ),
    Papel.AGENTE: frozenset(
        {
            Permissao.CONSULTAR_PACOTES,
            Permissao.RESERVAR,
            Permissao.EMITIR_PASSAGEM,
        }
    ),
    Papel.ADMINISTRADOR: frozenset(
        {
            Permissao.GERENCIAR_CATALOGO,
            Permissao.AGENDAR,
            Permissao.GERENCIAR_CONTAS,
        }
    ),
}


class PermissaoNegadaError(PermissionError):
    """Levantado quando um papel tenta uma acao que nao lhe e permitida."""


def _para_papel(papel: "Papel | str") -> Papel:
    """Normaliza uma string ou Papel para o enum Papel."""
    return papel if isinstance(papel, Papel) else Papel(papel)


def tem_permissao(papel: "Papel | str", permissao: "Permissao | str") -> bool:
    """Indica se ``papel`` possui ``permissao`` conforme a matriz da secao 4.1."""
    papel_enum = _para_papel(papel)
    permissao_enum = (
        permissao if isinstance(permissao, Permissao) else Permissao(permissao)
    )
    return permissao_enum in MATRIZ_PERMISSOES.get(papel_enum, frozenset())


def exigir_permissao(papel: "Papel | str", permissao: "Permissao | str") -> None:
    """Garante que ``papel`` possui ``permissao``; levanta erro caso contrario."""
    if not tem_permissao(papel, permissao):
        papel_enum = _para_papel(papel)
        raise PermissaoNegadaError(
            f"O papel '{papel_enum.value}' nao tem permissao para '{permissao}'."
        )
