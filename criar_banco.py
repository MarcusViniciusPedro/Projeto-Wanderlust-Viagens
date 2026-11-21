"""Cria (recria) o banco e roda os scripts sql/01..06 automaticamente.

Uso:
    .venv/bin/python criar_banco.py            # dropa e recria do zero
    .venv/bin/python criar_banco.py --no-drop  # só cria (falha se já existir)

Conecta no banco de sistema 'master' usando as variáveis WANDERLUST_DB_*
(server/port/user/password) — nunca depende do banco padrão do login, então
funciona mesmo que o banco do projeto tenha sido apagado. Por padrão, dropa o
banco 'agencia_viagens' (derrubando conexões abertas) antes de recriar, de modo
que "recriar do zero" seja um único comando. Executa cada arquivo em batches
separados por linhas 'GO', em autocommit (necessário para DDL de banco).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pymssql
from dotenv import load_dotenv

load_dotenv()

SERVER = os.getenv("WANDERLUST_DB_SERVER", "localhost")
PORT = int(os.getenv("WANDERLUST_DB_PORT", "1433"))
USER = os.getenv("WANDERLUST_DB_USER", "sa")
PASSWORD = os.getenv("WANDERLUST_DB_PASSWORD", "")
DB_NAME = "agencia_viagens"  # nome criado pelo sql/01_schema.sql

ARQUIVOS = [
    "sql/01_schema.sql",
    "sql/02_aiv_tables.sql",
    "sql/03_indexes.sql",
    "sql/04_programmability.sql",
    "sql/05_seed_dml.sql",
    "sql/06_admin.sql",
]


def dividir_em_batches(texto: str) -> list[str]:
    """Separa um script T-SQL em batches por linhas contendo apenas 'GO'."""
    partes = re.split(r"(?im)^[ \t]*GO[ \t]*;?[ \t]*$", texto)
    return [p.strip() for p in partes if p.strip()]


def main() -> int:
    dropar = "--no-drop" not in sys.argv

    print(f"Conectando em {SERVER}:{PORT} como {USER} (database=master)...")
    try:
        # Conecta no 'master' (sempre existe) para poder dropar/criar o banco;
        # autocommit é necessário para DDL (DROP/CREATE DATABASE).
        conn = pymssql.connect(
            server=SERVER, port=str(PORT), user=USER, password=PASSWORD,
            database="master", autocommit=True,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERRO ao conectar: {exc}")
        return 1

    cur = conn.cursor()

    if dropar:
        print(f"== Dropando banco '{DB_NAME}' se existir ==")
        try:
            # SET SINGLE_USER com ROLLBACK IMMEDIATE derruba conexões abertas,
            # evitando o erro "banco em uso" ao dropar.
            cur.execute(
                f"""
                IF DB_ID('{DB_NAME}') IS NOT NULL
                BEGIN
                    ALTER DATABASE [{DB_NAME}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
                    DROP DATABASE [{DB_NAME}];
                END
                """
            )
            print("  OK (banco removido ou inexistente)")
        except Exception as exc:  # noqa: BLE001
            print(f"  ERRO ao dropar: {exc}")
            conn.close()
            return 1

    for arq in ARQUIVOS:
        caminho = Path(arq)
        if not caminho.exists():
            print(f"ERRO: arquivo não encontrado: {arq}")
            return 1
        print(f"\n== Executando {arq} ==")
        sql = caminho.read_text(encoding="utf-8")
        for i, batch in enumerate(dividir_em_batches(sql), 1):
            try:
                cur.execute(batch)
                # Consome eventuais result sets para liberar a conexão.
                while cur.nextset():
                    pass
            except Exception as exc:  # noqa: BLE001
                print(f"  ERRO no batch {i} de {arq}:\n  {exc}")
                conn.close()
                return 1
        print(f"  OK ({arq})")

    conn.close()
    print("\nConcluído: banco 'agencia_viagens' criado e populado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
