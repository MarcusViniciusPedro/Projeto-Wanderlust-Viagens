"""Testes de unidade da camada de dados de pacotes apos o refactor para
stored procedures (FEAT-003).

As quatro funcoes refatoradas (``criar_pacote``, ``atualizar_pacote``,
``excluir_pacote``, ``listar_pacotes``) deixaram de usar SQL inline e passaram
a chamar procedures via ``EXEC``. Um ``FakeCursor``/``FakeConnection`` em
memoria grava as instrucoes executadas e devolve resultados programados, sem
nenhum SQL Server vivo. Monkeypatchamos ``get_connection`` COMO IMPORTADO em
``app.catalogo.repository`` (o nome que o modulo realmente usa).

Os testes falhariam se o codigo voltasse a usar SQL inline (nao haveria o
``EXEC dbo.sp_...`` esperado) ou se tratasse mal o caso de 0 linhas afetadas
(atualizar -> None, excluir -> False). Sob SET NOCOUNT ON o ``cursor.rowcount``
e nao confiavel, entao as procedures devolvem ``SELECT @@ROWCOUNT`` (e o insert
devolve SCOPE_IDENTITY) e o Python le via ``fetchone()[0]`` - o fake nao
implementa ``rowcount`` de proposito, para que qualquer leitura via ``rowcount``
quebre.
"""

from __future__ import annotations

from datetime import date
from typing import Any, List, Optional

from app.catalogo import repository as repo
from app.catalogo.schemas import PacoteCriar, PacoteSaida


class FakeCursor:
    """Cursor em memoria que registra execucoes e devolve resultados fixos.

    De proposito NAO expomos ``rowcount`` util: o codigo deve ler o id gerado /
    @@ROWCOUNT via ``fetchone``.
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


def _dados_pacote() -> PacoteCriar:
    return PacoteCriar(
        preco_base=1500.0,
        data_inicio=date(2026, 1, 10),
        data_fim=date(2026, 1, 20),
        estoque=5,
        tipo_viagem="Aventura",
        nivel="Intermediario",
    )


# --------------------------------------------------------------------------
# criar_pacote
# --------------------------------------------------------------------------


def test_criar_pacote_exec_procedure_e_retorna_id(monkeypatch):
    cursor = FakeCursor(fetchone_seq=[(77,)], fetchall_seq=[])
    conn = _instalar_conn(monkeypatch, cursor)

    dados = _dados_pacote()
    saida = repo.criar_pacote(dados)

    assert isinstance(saida, PacoteSaida)
    assert saida.id_pacote == 77  # id vindo do fetchone (SCOPE_IDENTITY)
    assert saida.preco_base == 1500.0
    assert saida.tipo_viagem == "Aventura"
    assert "EXEC dbo.sp_criar_pacote" in _texto_execs(cursor)
    # Nao deve haver INSERT inline.
    assert "INSERT INTO" not in _texto_execs(cursor)
    sql, params = cursor.execucoes[0]
    assert params == (
        dados.preco_base,
        dados.data_inicio,
        dados.data_fim,
        dados.estoque,
        dados.tipo_viagem,
        dados.nivel,
    )
    assert conn.commits == 1
    assert conn.closed is True


# --------------------------------------------------------------------------
# atualizar_pacote
# --------------------------------------------------------------------------


def test_atualizar_pacote_uma_linha_retorna_objeto(monkeypatch):
    cursor = FakeCursor(fetchone_seq=[(1,)], fetchall_seq=[])
    conn = _instalar_conn(monkeypatch, cursor)

    dados = _dados_pacote()
    saida = repo.atualizar_pacote(9, dados)

    assert isinstance(saida, PacoteSaida)
    assert saida.id_pacote == 9
    assert "EXEC dbo.sp_atualizar_pacote" in _texto_execs(cursor)
    assert "UPDATE dbo.Pacote" not in _texto_execs(cursor)
    _, params = cursor.execucoes[0]
    assert params == (
        9,
        dados.preco_base,
        dados.data_inicio,
        dados.data_fim,
        dados.estoque,
        dados.tipo_viagem,
        dados.nivel,
    )
    assert conn.commits == 1


def test_atualizar_pacote_zero_linhas_retorna_none(monkeypatch):
    cursor = FakeCursor(fetchone_seq=[(0,)], fetchall_seq=[])
    _instalar_conn(monkeypatch, cursor)

    saida = repo.atualizar_pacote(9, _dados_pacote())
    assert saida is None  # @@ROWCOUNT = 0 -> pacote inexistente
    assert "EXEC dbo.sp_atualizar_pacote" in _texto_execs(cursor)


# --------------------------------------------------------------------------
# excluir_pacote
# --------------------------------------------------------------------------


def test_excluir_pacote_uma_linha_retorna_true(monkeypatch):
    cursor = FakeCursor(fetchone_seq=[(1,)], fetchall_seq=[])
    conn = _instalar_conn(monkeypatch, cursor)

    assert repo.excluir_pacote(9) is True
    sql, params = cursor.execucoes[0]
    assert "EXEC dbo.sp_excluir_pacote" in sql
    assert "DELETE FROM" not in sql
    assert params == (9,)
    assert conn.commits == 1


def test_excluir_pacote_zero_linhas_retorna_false(monkeypatch):
    cursor = FakeCursor(fetchone_seq=[(0,)], fetchall_seq=[])
    _instalar_conn(monkeypatch, cursor)

    assert repo.excluir_pacote(9) is False
    assert "EXEC dbo.sp_excluir_pacote" in _texto_execs(cursor)


# --------------------------------------------------------------------------
# listar_pacotes
# --------------------------------------------------------------------------


def test_listar_pacotes_exec_sp_e_mapeia(monkeypatch):
    cursor = FakeCursor(
        fetchone_seq=[],
        fetchall_seq=[
            [
                (
                    1,
                    1500.0,
                    date(2026, 1, 10),
                    date(2026, 1, 20),
                    5,
                    "Aventura",
                    "Intermediario",
                ),
                (
                    2,
                    999.9,
                    date(2026, 2, 1),
                    date(2026, 2, 5),
                    0,
                    "Praia",
                    None,
                ),
            ]
        ],
    )
    conn = _instalar_conn(monkeypatch, cursor)

    pacotes = repo.listar_pacotes()

    assert "EXEC dbo.sp_listar_pacotes" in _texto_execs(cursor)
    assert "SELECT" not in _texto_execs(cursor)  # sem SELECT inline
    assert len(pacotes) == 2
    assert all(isinstance(p, PacoteSaida) for p in pacotes)
    assert pacotes[0].id_pacote == 1
    assert pacotes[0].preco_base == 1500.0
    assert pacotes[0].tipo_viagem == "Aventura"
    assert pacotes[1].estoque == 0
    assert pacotes[1].nivel is None
    assert conn.closed is True


def test_listar_pacotes_vazio(monkeypatch):
    cursor = FakeCursor(fetchone_seq=[], fetchall_seq=[[]])
    _instalar_conn(monkeypatch, cursor)
    assert repo.listar_pacotes() == []
    assert "EXEC dbo.sp_listar_pacotes" in _texto_execs(cursor)
