"""Testes de unidade da camada de dados de usuarios apos o refactor para
stored procedures (FEAT-002).

As quatro funcoes refatoradas (``atualizar_usuario``, ``excluir_usuario``,
``excluir_conta``, ``listar_contas``) deixaram de usar SQL inline e passaram a
chamar procedures via ``EXEC``. Aqui um ``FakeCursor``/``FakeConnection`` em
memoria grava as instrucoes executadas e devolve resultados programados, sem
nenhum SQL Server vivo. Monkeypatchamos ``get_connection`` COMO IMPORTADO em
``app.usuarios.repository`` (o nome que o modulo realmente usa).

Os testes falhariam se o codigo voltasse a usar SQL inline (nao haveria o
``EXEC dbo.sp_...`` esperado) ou se tratasse mal o caso de 0 linhas afetadas
(deve virar ``None``, nunca um objeto). Sob SET NOCOUNT ON o ``cursor.rowcount``
e nao confiavel, entao as procedures devolvem ``SELECT @@ROWCOUNT`` e o Python
le via ``fetchone()[0]`` - o fake nao implementa ``rowcount`` de proposito, para
que qualquer leitura via ``rowcount`` quebre.
"""

from __future__ import annotations

from typing import Any, List, Optional

import pytest

from app.core.authz import Papel
from app.usuarios import repository as repo
from app.usuarios.schemas import ContaAdminSaida, StatusConta, UsuarioAtualizar


class FakeCursor:
    """Cursor em memoria que registra execucoes e devolve resultados fixos.

    ``resultados`` e uma fila: cada ``execute`` que produz linhas consome o
    proximo item (``_prox_fetchone`` / ``_prox_fetchall``). De proposito NAO
    expomos ``rowcount`` util: o codigo deve ler @@ROWCOUNT via ``fetchone``.
    """

    def __init__(self, fetchone_seq: List[Any], fetchall_seq: List[Any]):
        self.execucoes: List[tuple] = []
        self._fetchone_seq = list(fetchone_seq)
        self._fetchall_seq = list(fetchall_seq)

    def execute(self, sql: str, params: Optional[tuple] = None) -> None:
        self.execucoes.append((sql, params))

    def fetchone(self) -> Any:
        return self._fetchone_seq.pop(0)

    def fetchall(self) -> Any:
        return self._fetchall_seq.pop(0)

    @property
    def rowcount(self) -> int:  # pragma: no cover - deve estourar se usado
        raise AssertionError(
            "cursor.rowcount nao e confiavel sob SET NOCOUNT ON; "
            "o codigo deve ler @@ROWCOUNT via fetchone()."
        )


class FakeConnection:
    def __init__(self, cursor: FakeCursor):
        self._cursor = cursor
        self.commits = 0
        self.closed = False

    def cursor(self) -> FakeCursor:
        return self._cursor

    def commit(self) -> None:
        self.commits += 1

    def close(self) -> None:
        self.closed = True


def _instalar_conn(monkeypatch, cursor: FakeCursor) -> FakeConnection:
    conn = FakeConnection(cursor)
    monkeypatch.setattr(repo, "get_connection", lambda settings=None: conn)
    return conn


def _texto_execs(cursor: FakeCursor) -> str:
    return " || ".join(sql for sql, _ in cursor.execucoes)


# --------------------------------------------------------------------------
# atualizar_usuario
# --------------------------------------------------------------------------


def test_atualizar_usuario_exec_procedure_atualizacao_parcial(monkeypatch):
    # Atualizacao parcial ATOMICA: um unico EXEC, sem leitura previa do perfil.
    # Os campos nao enviados viajam como NULL ("nao alterar"); a procedure os
    # preserva via COALESCE. A primeira (e unica) leitura do cursor e o
    # @@ROWCOUNT da procedure.
    cursor = FakeCursor(
        fetchone_seq=[(1,)],  # @@ROWCOUNT da procedure
        fetchall_seq=[],
    )
    conn = _instalar_conn(monkeypatch, cursor)

    # buscar_usuario_por_id (chamado no fim, read-after-write) retorna o perfil
    # atualizado para montar a resposta.
    def fake_buscar(id_passageiro, settings=None):
        from app.usuarios.schemas import UsuarioSaida

        return UsuarioSaida(
            id_passageiro=id_passageiro,
            nome="Ana Maria",
            email="ana@old.com",
            papel=Papel.TURISTA,
        )

    monkeypatch.setattr(repo, "buscar_usuario_por_id", fake_buscar)

    dados = UsuarioAtualizar(nome="Ana Maria")
    saida = repo.atualizar_usuario(7, dados)

    assert saida is not None
    assert saida.nome == "Ana Maria"
    # Houve UM unico EXEC da procedure de atualizacao, sem SELECT de pre-leitura.
    assert "EXEC dbo.sp_atualizar_usuario" in _texto_execs(cursor)
    assert len(cursor.execucoes) == 1
    # O EXEC envia o campo enviado e NULL (nao-alterar) para os demais, deixando
    # o COALESCE da procedure preservar as colunas nao enviadas no banco.
    exec_sql, exec_params = cursor.execucoes[0]
    assert "EXEC dbo.sp_atualizar_usuario" in exec_sql
    assert exec_params == (
        7,
        "Ana Maria",  # enviado
        None,  # nome_social nao enviado -> NULL -> COALESCE preserva
        None,  # pronome
        None,  # cep
        None,  # email
        None,  # telefone
    )
    assert conn.commits == 1
    assert conn.closed is True


def test_atualizar_usuario_multiplos_campos_envia_apenas_enviados(monkeypatch):
    # Com varios campos enviados, cada um vai na sua posicao e os ausentes
    # permanecem NULL (nao-alterar).
    cursor = FakeCursor(fetchone_seq=[(1,)], fetchall_seq=[])
    _instalar_conn(monkeypatch, cursor)

    from app.usuarios.schemas import UsuarioSaida

    monkeypatch.setattr(
        repo,
        "buscar_usuario_por_id",
        lambda id_passageiro, settings=None: UsuarioSaida(
            id_passageiro=id_passageiro, nome="Novo", papel=Papel.TURISTA
        ),
    )

    dados = UsuarioAtualizar(nome="Novo", telefone="11988887777")
    repo.atualizar_usuario(7, dados)

    exec_params = cursor.execucoes[0][1]
    assert exec_params == (7, "Novo", None, None, None, None, "11988887777")


def test_atualizar_usuario_zero_linhas_retorna_none(monkeypatch):
    cursor = FakeCursor(
        fetchone_seq=[(0,)],  # @@ROWCOUNT = 0 -> id inexistente
        fetchall_seq=[],
    )
    _instalar_conn(monkeypatch, cursor)

    # Com 0 linhas afetadas o id nao existe; buscar_usuario_por_id NAO deve ser
    # chamado (se for, devolveria algo nao-None e o assert de None quebraria).
    monkeypatch.setattr(
        repo,
        "buscar_usuario_por_id",
        lambda *a, **k: pytest.fail("nao deveria buscar com 0 linhas"),
    )

    saida = repo.atualizar_usuario(7, UsuarioAtualizar(nome="Ana"))
    assert saida is None  # 0 linhas -> None
    assert "EXEC dbo.sp_atualizar_usuario" in _texto_execs(cursor)


def test_atualizar_usuario_sem_campos_devolve_perfil_atual(monkeypatch):
    # Corpo vazio (nenhum campo enviado): nao executa a procedure, apenas
    # devolve o perfil atual via buscar_usuario_por_id.
    cursor = FakeCursor(fetchone_seq=[], fetchall_seq=[])
    _instalar_conn(monkeypatch, cursor)

    from app.usuarios.schemas import UsuarioSaida

    monkeypatch.setattr(
        repo,
        "buscar_usuario_por_id",
        lambda id_passageiro, settings=None: UsuarioSaida(
            id_passageiro=id_passageiro, nome="Ana", papel=Papel.TURISTA
        ),
    )

    saida = repo.atualizar_usuario(7, UsuarioAtualizar())
    assert saida is not None
    assert saida.nome == "Ana"
    # Sem campos para atualizar nao ha EXEC da procedure.
    assert "EXEC dbo.sp_atualizar_usuario" not in _texto_execs(cursor)


# --------------------------------------------------------------------------
# excluir_usuario / excluir_conta (soft delete via mesma procedure)
# --------------------------------------------------------------------------


def test_excluir_usuario_exec_sp_excluir(monkeypatch):
    cursor = FakeCursor(fetchone_seq=[(1,)], fetchall_seq=[])
    conn = _instalar_conn(monkeypatch, cursor)

    from app.usuarios.schemas import UsuarioSaida

    monkeypatch.setattr(
        repo,
        "buscar_usuario_por_id",
        lambda id_passageiro, settings=None: UsuarioSaida(
            id_passageiro=id_passageiro,
            nome="Conta removida",
            papel=Papel.TURISTA,
        ),
    )

    saida = repo.excluir_usuario(42)
    assert saida is not None
    sql, params = cursor.execucoes[0]
    assert "EXEC dbo.sp_excluir_usuario" in sql
    assert params == (42,)
    assert conn.commits == 1


def test_excluir_usuario_zero_linhas_retorna_none(monkeypatch):
    cursor = FakeCursor(fetchone_seq=[(0,)], fetchall_seq=[])
    _instalar_conn(monkeypatch, cursor)
    # buscar_usuario_por_id NAO deve ser chamado quando 0 linhas; se for,
    # devolveria algo nao-None e o assert de None quebraria.
    monkeypatch.setattr(
        repo,
        "buscar_usuario_por_id",
        lambda *a, **k: pytest.fail("nao deveria buscar com 0 linhas"),
    )
    assert repo.excluir_usuario(42) is None


def test_excluir_conta_usa_mesma_procedure(monkeypatch):
    cursor = FakeCursor(fetchone_seq=[(1,)], fetchall_seq=[])
    _instalar_conn(monkeypatch, cursor)

    monkeypatch.setattr(
        repo,
        "buscar_conta",
        lambda id_passageiro, settings=None: ContaAdminSaida(
            id_passageiro=id_passageiro,
            nome="Conta removida",
            papel=Papel.TURISTA,
            status=StatusConta.BANIDO,
        ),
    )

    saida = repo.excluir_conta(5)
    assert saida is not None
    assert saida.status is StatusConta.BANIDO
    sql, params = cursor.execucoes[0]
    assert "EXEC dbo.sp_excluir_usuario" in sql  # MESMA procedure do self-service
    assert params == (5,)


def test_excluir_conta_zero_linhas_retorna_none(monkeypatch):
    cursor = FakeCursor(fetchone_seq=[(0,)], fetchall_seq=[])
    _instalar_conn(monkeypatch, cursor)
    monkeypatch.setattr(
        repo,
        "buscar_conta",
        lambda *a, **k: pytest.fail("nao deveria buscar com 0 linhas"),
    )
    assert repo.excluir_conta(5) is None


# --------------------------------------------------------------------------
# listar_contas
# --------------------------------------------------------------------------


def test_listar_contas_exec_sp_listar_e_mapeia(monkeypatch):
    cursor = FakeCursor(
        fetchone_seq=[],
        fetchall_seq=[
            [
                (1, "Admin", "a@x.com", "Administrador", "Ativo"),
                (2, "Turista", "t@x.com", "Turista", "Banido"),
            ]
        ],
    )
    conn = _instalar_conn(monkeypatch, cursor)

    contas = repo.listar_contas()

    assert "EXEC dbo.sp_listar_usuarios" in _texto_execs(cursor)
    assert len(contas) == 2
    assert all(isinstance(c, ContaAdminSaida) for c in contas)
    assert contas[0].id_passageiro == 1
    assert contas[0].papel is Papel.ADMINISTRADOR
    assert contas[0].status is StatusConta.ATIVO
    assert contas[1].status is StatusConta.BANIDO
    assert conn.closed is True


def test_listar_contas_vazio(monkeypatch):
    cursor = FakeCursor(fetchone_seq=[], fetchall_seq=[[]])
    _instalar_conn(monkeypatch, cursor)
    assert repo.listar_contas() == []
    assert "EXEC dbo.sp_listar_usuarios" in _texto_execs(cursor)
