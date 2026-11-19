-- =====================================================================
-- Wanderlust Viagens - Banco de dados (SQL Server / T-SQL)
-- Script 02 - Tabelas de apoio ao AIV (Assistente Inteligente de Viagens)
-- ---------------------------------------------------------------------
-- Preferencia, Questionario_Resposta, Avaliacao e IA_Feedback alimentam
-- a recomendacao e o feedback do AIV. FKs sem ON DELETE (NO ACTION).
-- Pre-requisito: executar 01_schema.sql antes.
-- =====================================================================

USE agencia_viagens;
GO

-- Preferencia - perfil de preferencias do turista (uma por turista).
CREATE TABLE Preferencia (
    id_preferencia    INT IDENTITY(1,1) NOT NULL,
    fk_turista        INT NOT NULL,
    tipo_viagem       NVARCHAR(50) NULL,
    nivel             NVARCHAR(50) NULL,
    orcamento_max     DECIMAL(10,2) NULL,
    estacao_preferida NVARCHAR(30) NULL,
    observacoes       NVARCHAR(MAX) NULL,
    atualizado_em     DATETIME2 NOT NULL DEFAULT (SYSUTCDATETIME()),
    PRIMARY KEY (id_preferencia),
    UNIQUE (fk_turista),
    FOREIGN KEY (fk_turista) REFERENCES Conta_turista (id_turista)
)

-- Questionario_Resposta - respostas brutas do questionario inicial.
CREATE TABLE Questionario_Resposta (
    id_resposta   INT IDENTITY(1,1) NOT NULL,
    fk_turista    INT NOT NULL,
    pergunta      NVARCHAR(200) NOT NULL,
    resposta      NVARCHAR(MAX) NOT NULL,
    respondido_em DATETIME2 NOT NULL DEFAULT (SYSUTCDATETIME()),
    PRIMARY KEY (id_resposta),
    FOREIGN KEY (fk_turista) REFERENCES Conta_turista (id_turista)
)

-- Avaliacao - avaliacoes de pacotes pelos turistas (nota 1..5).
-- UNIQUE (fk_turista, fk_pacote): um turista avalia um pacote uma vez.
CREATE TABLE Avaliacao (
    id_avaliacao INT IDENTITY(1,1) NOT NULL,
    fk_turista   INT NOT NULL,
    fk_pacote    INT NOT NULL,
    nota         INT NOT NULL,
    comentario   NVARCHAR(MAX) NULL,
    data         DATETIME2 NOT NULL DEFAULT (SYSUTCDATETIME()),
    PRIMARY KEY (id_avaliacao),
    FOREIGN KEY (fk_turista) REFERENCES Conta_turista (id_turista),
    FOREIGN KEY (fk_pacote) REFERENCES Pacote (id_pacote),
    CHECK (nota BETWEEN 1 AND 5),
    UNIQUE (fk_turista, fk_pacote)
)

-- IA_Feedback - feedback agregado pelo AIV por pacote (um por pacote).
-- Atualizado pela trigger tr_avaliacao_atualiza_ia_feedback (script 04).
CREATE TABLE IA_Feedback (
    id_feedback      INT IDENTITY(1,1) NOT NULL,
    fk_pacote        INT NOT NULL,
    score_agregado   DECIMAL(4,2) NULL,
    total_avaliacoes INT NOT NULL DEFAULT (0),
    resumo           NVARCHAR(MAX) NULL,
    data_atualizacao DATETIME2 NOT NULL DEFAULT (SYSUTCDATETIME()),
    PRIMARY KEY (id_feedback),
    UNIQUE (fk_pacote),
    FOREIGN KEY (fk_pacote) REFERENCES Pacote (id_pacote),
    CHECK (score_agregado IS NULL OR score_agregado BETWEEN 0 AND 5)
)
GO
