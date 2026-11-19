-- =====================================================================
-- Wanderlust Viagens - Banco de dados (SQL Server / T-SQL)
-- Script 03 - Indices estrategicos
-- ---------------------------------------------------------------------
-- Indices para as consultas de alta frequencia do catalogo e do AIV.
-- Pre-requisito: executar 01_schema.sql e 02_aiv_tables.sql antes.
-- =====================================================================

USE agencia_viagens;
GO

-- Busca de pacotes por tipo de viagem + nivel + data (catalogo e AIV).
-- Inclui preco_base e estoque para cobrir a consulta sem lookups.
CREATE INDEX IX_Pacote_busca
    ON Pacote (tipo_viagem, nivel, data_inicio)
    INCLUDE (preco_base, estoque)

-- Agregacao de avaliacoes por pacote (score do IA_Feedback).
CREATE INDEX IX_Avaliacao_pacote
    ON Avaliacao (fk_pacote)
    INCLUDE (nota)

-- Recuperacao do perfil de preferencias por turista (entrada do AIV).
CREATE INDEX IX_Preferencia_turista
    ON Preferencia (fk_turista)

-- Historico de compras por turista (perfil, relatorios e insumo do AIV).
CREATE INDEX IX_Venda_conta_turista
    ON Venda (fk_conta_turista)
    INCLUDE (data_venda, valor_total)
GO

-- Observacao: a coluna Usuario.email ja possui UNIQUE (ver 01_schema.sql),
-- que o SQL Server materializa como indice unico. Ele ja atende o login
-- por e-mail, entao um indice dedicado seria redundante.
