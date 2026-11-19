# Camada de banco de dados — Wanderlust Viagens (SQL Server / T-SQL)

Scripts T-SQL da base de dados `agencia_viagens`, escritos em estilo direto
para rodar no Visual Studio Code (extensão **mssql**), no Azure Data Studio
ou no SSMS. Os scripts usam `CREATE DATABASE`, `USE` e `CREATE TABLE` em
sequência, com `GO` para separar os lotes.

> Não há instância de SQL Server no ambiente de desenvolvimento do agente.
> Os scripts foram validados por inspeção e devem ser executados pelo
> usuário em um SQL Server próprio.

## Requisitos

- Microsoft SQL Server 2017 ou superior (recomenda-se 2019+).
- Um cliente de execução de T-SQL: a extensão **mssql** do VS Code,
  `sqlcmd`, Azure Data Studio ou SSMS.

## Ordem de execução

Execute os scripts na ordem numérica. Cada um depende do anterior:

| Ordem | Arquivo                 | Conteúdo                                                        |
|-------|-------------------------|----------------------------------------------------------------|
| 1     | `01_schema.sql`         | Criação do banco e das 10 tabelas do documento + `Credencial`. |
| 2     | `02_aiv_tables.sql`     | Tabelas de apoio ao AIV (Preferencia, Questionario_Resposta, Avaliacao, IA_Feedback). |
| 3     | `03_indexes.sql`        | Índices estratégicos para busca/recomendação.                  |
| 4     | `04_programmability.sql`| Views, function, stored procedure e triggers.                  |
| 5     | `05_seed_dml.sql`       | Dados de exemplo + consultas CRUD representativas.              |

Como os scripts fazem `CREATE` direto (sem guardas de "se não existir"),
rode-os em um banco limpo. Para reexecutar do zero, apague o banco antes
(`DROP DATABASE agencia_viagens;` em um contexto fora dele, ex.: `USE master;`).

### No VS Code (extensão mssql) / Azure Data Studio / SSMS

Abra cada arquivo na ordem acima e execute o script inteiro
(`01` cria e seleciona o banco com `USE agencia_viagens;`).

### Via `sqlcmd`

```bash
sqlcmd -S localhost -U sa -P 'SuaSenha' -i sql/01_schema.sql
sqlcmd -S localhost -U sa -P 'SuaSenha' -i sql/02_aiv_tables.sql
sqlcmd -S localhost -U sa -P 'SuaSenha' -i sql/03_indexes.sql
sqlcmd -S localhost -U sa -P 'SuaSenha' -i sql/04_programmability.sql
sqlcmd -S localhost -U sa -P 'SuaSenha' -i sql/05_seed_dml.sql
```

## Tipos adotados

Os nomes de tabelas, colunas e objetos seguem o modelo do projeto. Os tipos
preservam o domínio:

- Texto em `NVARCHAR` (acentos/português e nome social).
- Dinheiro em `DECIMAL`.
- Data/hora em `DATETIME2`; datas simples em `DATE`.

## INSERT sem lista de colunas e colunas IDENTITY

O seed (`05_seed_dml.sql`) usa `INSERT INTO Tabela VALUES (...)` sem lista de
colunas. Como a PK é `INT IDENTITY(1,1)`, ela é gerada pelo banco e **não**
recebe valor: o primeiro valor de cada tupla corresponde à primeira coluna
**não-IDENTITY**. As inserções são determinísticas (de cima para baixo),
então os ids gerados são 1, 2, 3... e as FKs referenciam esses valores
literais (ex.: `Conta_turista VALUES (1)` aponta para o `Usuario` de id 1).

Quando uma coluna `NOT NULL` tem `DEFAULT` e queremos deixá-la no valor
padrão (ex.: `Credencial.atualizado_em`, `Preferencia.atualizado_em`,
`Avaliacao.data`), usamos uma lista de colunas explícita naquele `INSERT`,
pois sem lista seria obrigatório fornecer um valor para todas as colunas.

## Chaves estrangeiras e exclusão

As FKs são declaradas sem cláusula `ON DELETE` (comportamento padrão
`NO ACTION`). Isso mantém o estilo simples do exemplo e evita o erro 1785
do SQL Server (múltiplos caminhos de cascade até `Usuario`, já que `Venda`
referencia tanto `Conta_turista` quanto `Conta_colaborador`). Para apagar
dados relacionados, remova primeiro as linhas dependentes.

## Dicionário de dados

A descrição completa de todas as tabelas e colunas está em
[`docs/dicionario_de_dados.md`](../docs/dicionario_de_dados.md).
