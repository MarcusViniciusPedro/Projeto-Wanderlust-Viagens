# Camada de banco de dados — Wanderlust Viagens (SQL Server / T-SQL)

Scripts T-SQL da base de dados `agencia_viagens`. Foram traduzidos do DDL
MySQL do documento de requisitos e ampliados com as tabelas de apoio ao
AIV (Assistente Inteligente de Viagens).

> Não há instância de SQL Server no ambiente de desenvolvimento do agente.
> Os scripts foram validados por inspeção de sintaxe e devem ser executados
> pelo usuário em um SQL Server próprio.

## Requisitos

- Microsoft SQL Server 2017 ou superior (recomenda-se 2019+).
- Um cliente de execução de T-SQL: `sqlcmd`, Azure Data Studio ou SSMS.

## Ordem de execução

Execute os scripts na ordem numérica. Cada um depende do anterior:

| Ordem | Arquivo                 | Conteúdo                                                        |
|-------|-------------------------|----------------------------------------------------------------|
| 1     | `01_schema.sql`         | Criação do banco e das 10 tabelas do documento + `Credencial`. |
| 2     | `02_aiv_tables.sql`     | Tabelas de apoio ao AIV (Preferencia, Questionario_Resposta, Avaliacao, IA_Feedback). |
| 3     | `03_indexes.sql`        | Índices estratégicos para busca/recomendação.                  |
| 4     | `04_programmability.sql`| Views, functions, stored procedures e triggers.                |
| 5     | `05_seed_dml.sql`       | Dados de exemplo + consultas CRUD representativas.              |

### Via `sqlcmd`

```bash
sqlcmd -S localhost -U sa -P 'SuaSenha' -i sql/01_schema.sql
sqlcmd -S localhost -U sa -P 'SuaSenha' -i sql/02_aiv_tables.sql
sqlcmd -S localhost -U sa -P 'SuaSenha' -i sql/03_indexes.sql
sqlcmd -S localhost -U sa -P 'SuaSenha' -i sql/04_programmability.sql
sqlcmd -S localhost -U sa -P 'SuaSenha' -i sql/05_seed_dml.sql
```

No Azure Data Studio ou SSMS, abra e execute cada arquivo na mesma ordem.
Os scripts usam `GO` como separador de lotes e são, em sua maioria,
idempotentes (podem ser reexecutados sem erro).

## Notas de tradução MySQL → T-SQL

- `INT AUTO_INCREMENT` → `INT IDENTITY(1,1)`
- `VARCHAR` → `NVARCHAR` (acentos/português e nome social, RNF1)
- `TEXT` → `NVARCHAR(MAX)`
- `DATETIME` → `DATETIME2`
- `DATE` e `DECIMAL` permanecem.
- `CREATE DATABASE IF NOT EXISTS` → verificação via `sys.databases`.

## Múltiplos caminhos de cascade (importante)

O SQL Server rejeita esquemas com múltiplos caminhos de cascade até a mesma
tabela (erro 1785). Como `Venda` referencia **tanto** `Conta_turista` quanto
`Conta_colaborador` (ambas especializações de `Usuario`), suas FKs usam
`ON DELETE NO ACTION`. As FKs a jusante (`Passagem`, `Obtem`) seguem a mesma
regra. Apenas `Conta_turista`, `Conta_colaborador`, `Credencial`,
`Preferencia`, `Questionario_Resposta` e `IA_Feedback` usam `ON DELETE CASCADE`,
pois cada uma tem um único caminho.

## Dicionário de dados

A descrição completa de todas as tabelas e colunas está em
[`docs/dicionario_de_dados.md`](../docs/dicionario_de_dados.md).
