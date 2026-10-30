"""Testes da matriz de permissoes por papel (secao 4.1 do documento)."""

from __future__ import annotations

import pytest

from app.core.authz import (
    MATRIZ_PERMISSOES,
    Papel,
    Permissao,
    PermissaoNegadaError,
    exigir_permissao,
    tem_permissao,
)


def test_turista_pode_cadastrar_consultar_reservar_comprar() -> None:
    for perm in (
        Permissao.CADASTRAR,
        Permissao.CONSULTAR_PACOTES,
        Permissao.RESERVAR,
        Permissao.COMPRAR,
    ):
        assert tem_permissao(Papel.TURISTA, perm) is True


def test_turista_nao_pode_gerenciar_catalogo() -> None:
    assert tem_permissao(Papel.TURISTA, Permissao.GERENCIAR_CATALOGO) is False
    with pytest.raises(PermissaoNegadaError):
        exigir_permissao(Papel.TURISTA, Permissao.GERENCIAR_CATALOGO)


def test_agente_pode_reservar_e_emitir_passagem() -> None:
    assert tem_permissao(Papel.AGENTE, Permissao.RESERVAR) is True
    assert tem_permissao(Papel.AGENTE, Permissao.EMITIR_PASSAGEM) is True


def test_agente_nao_pode_gerenciar_contas() -> None:
    assert tem_permissao(Papel.AGENTE, Permissao.GERENCIAR_CONTAS) is False


def test_administrador_pode_gerenciar_catalogo_agendar_contas() -> None:
    for perm in (
        Permissao.GERENCIAR_CATALOGO,
        Permissao.AGENDAR,
        Permissao.GERENCIAR_CONTAS,
    ):
        assert tem_permissao(Papel.ADMINISTRADOR, perm) is True
    # exigir_permissao nao levanta quando permitido
    exigir_permissao(Papel.ADMINISTRADOR, Permissao.GERENCIAR_CATALOGO)


def test_aceita_papel_como_string_dos_valores_do_banco() -> None:
    # Os valores devem casar com o CHECK do banco ('Turista','Agente','Administrador').
    assert tem_permissao("Turista", "comprar") is True
    assert tem_permissao("Administrador", "gerenciar_catalogo") is True
    assert tem_permissao("Agente", "emitir_passagem") is True


def test_todos_os_papeis_tem_entrada_na_matriz() -> None:
    assert set(MATRIZ_PERMISSOES.keys()) == set(Papel)
