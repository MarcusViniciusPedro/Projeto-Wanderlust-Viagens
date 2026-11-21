"""Cria o banco e roda os scripts sql/01..05 automaticamente via pymssql.

Uso:
    .venv/bin/python criar_banco.py

Conecta usando as variáveis WANDERLUST_DB_* do .env (server/port/user/password).
NÃO usa WANDERLUST_DB_NAME para conectar: o 01_schema.sql cria o banco e dá USE.
Executa cada arquivo em batches separados por linhas 'GO', em autocommit
(necessário para CREATE DATABASE). Para e reporta no primeiro erro.
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
    print(f"Conectando em {SERVER}:{PORT} como {USER} (sem banco padrão)...")
    try:
        # Sem 'database=' para poder criar o banco; autocommit para DDL.
        conn = pymssql.connect(
            server=SERVER, port=str(PORT), user=USER, password=PASSWORD,
            autocommit=True,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERRO ao conectar: {exc}")
        return 1

    cur = conn.cursor()
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
