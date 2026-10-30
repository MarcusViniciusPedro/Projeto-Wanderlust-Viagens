/* =====================================================================
   Wanderlust Viagens - Camada de banco de dados (SQL Server / T-SQL)
   Script 03 - Indices estrategicos
   ---------------------------------------------------------------------
   Indices para as consultas de alta frequencia do catalogo e do AIV
   (secao 1.2.1). Cada indice e comentado com a sua justificativa.
   Pre-requisito: executar 01_schema.sql e 02_aiv_tables.sql antes.
   Todos criados de forma idempotente (IF NOT EXISTS via sys.indexes).
   ===================================================================== */

USE agencia_viagens;
GO

/* IX_Pacote_busca
   Busca/filtro de pacotes por tipo de viagem + nivel + janela de datas
   (RF3 busca no catalogo e RF7 recomendacao do AIV). Inclui preco_base
   e estoque como colunas cobertas para evitar lookups na consulta. */
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Pacote_busca' AND object_id = OBJECT_ID('dbo.Pacote'))
    CREATE INDEX IX_Pacote_busca
        ON dbo.Pacote (tipo_viagem, nivel, data_inicio)
        INCLUDE (preco_base, estoque);
GO

/* IX_Avaliacao_pacote
   Agregacao de avaliacoes por pacote (calculo de score do IA_Feedback e
   exibicao de notas). Inclui nota para cobrir o AVG sem lookup. */
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Avaliacao_pacote' AND object_id = OBJECT_ID('dbo.Avaliacao'))
    CREATE INDEX IX_Avaliacao_pacote
        ON dbo.Avaliacao (fk_pacote)
        INCLUDE (nota);
GO

/* IX_Preferencia_turista
   Recuperacao do perfil de preferencias por turista (entrada do AIV, RF7).
   fk_turista ja e UNIQUE, mas o indice nomeado documenta o acesso. */
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Preferencia_turista' AND object_id = OBJECT_ID('dbo.Preferencia'))
    CREATE INDEX IX_Preferencia_turista
        ON dbo.Preferencia (fk_turista);
GO

/* IX_Venda_conta_turista
   Historico de compras por turista (perfil, relatorios e insumo do AIV).
   Inclui data_venda e valor_total para relatorios temporais. */
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Venda_conta_turista' AND object_id = OBJECT_ID('dbo.Venda'))
    CREATE INDEX IX_Venda_conta_turista
        ON dbo.Venda (fk_conta_turista)
        INCLUDE (data_venda, valor_total);
GO

/* IX_Usuario_email
   Autenticacao/login por e-mail (RF1/RF2). A coluna email ja possui
   UNIQUE (UQ_Usuario_email), que cria um indice unico; este indice
   nomeado existe apenas para documentar o padrao de acesso de login.
   Criado de forma condicional para nao duplicar caso ja haja o indice
   do UNIQUE constraint. */
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Usuario_email' AND object_id = OBJECT_ID('dbo.Usuario'))
   AND NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UQ_Usuario_email' AND object_id = OBJECT_ID('dbo.Usuario'))
    CREATE INDEX IX_Usuario_email
        ON dbo.Usuario (email);
GO
