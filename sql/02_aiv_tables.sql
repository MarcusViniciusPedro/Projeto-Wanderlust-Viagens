/* =====================================================================
   Wanderlust Viagens - Camada de banco de dados (SQL Server / T-SQL)
   Script 02 - Tabelas de apoio ao AIV (Assistente Inteligente de Viagens)
   ---------------------------------------------------------------------
   Estas tabelas sao extensoes coerentes ao modelo original: o documento
   referencia o questionario inicial, as preferencias do turista, as
   avaliacoes de pacotes e o IA_Feedback (secoes 1.2.2 e RF4/RF7/RF8),
   mas o DDL fornecido as omitiu. Aqui elas sao modeladas de forma
   consistente com o schema base (sql/01_schema.sql).
   Todas as colunas de texto usam NVARCHAR (acentos/PT). Datas DATETIME2.
   FKs com ON DELETE conforme a necessidade (CASCADE quando caminho unico).
   Pre-requisito: executar 01_schema.sql antes deste script.
   ===================================================================== */

USE agencia_viagens;
GO

/* =====================================================================
   Preferencia - perfil de preferencias do turista
   ---------------------------------------------------------------------
   Resultado consolidado do questionario inicial (RF4). Usado pelo AIV
   para recomendacao (RF7/RF8). 1 preferencia por turista (UNIQUE).
   Caminho unico de cascade (apenas Conta_turista) -> CASCADE permitido.
   ===================================================================== */
IF OBJECT_ID('dbo.Preferencia', 'U') IS NULL
CREATE TABLE dbo.Preferencia (
    id_preferencia   INT IDENTITY(1,1) NOT NULL,
    fk_turista       INT               NOT NULL,
    tipo_viagem      NVARCHAR(50)      NULL,   -- casa com Pacote.tipo_viagem (RF7)
    nivel            NVARCHAR(50)      NULL,   -- casa com Pacote.nivel (RF7)
    orcamento_max    DECIMAL(10,2)     NULL,   -- teto de orcamento desejado
    estacao_preferida NVARCHAR(30)     NULL,   -- ex. 'Verao', 'Inverno'
    observacoes      NVARCHAR(MAX)     NULL,
    atualizado_em    DATETIME2         NOT NULL
                     CONSTRAINT DF_Preferencia_atualizado DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT PK_Preferencia PRIMARY KEY (id_preferencia),
    CONSTRAINT UQ_Preferencia_turista UNIQUE (fk_turista),
    CONSTRAINT FK_Preferencia_ContaTurista FOREIGN KEY (fk_turista)
        REFERENCES dbo.Conta_turista (id_turista)
        ON DELETE CASCADE   -- caminho unico: OK
);
GO

/* =====================================================================
   Questionario_Resposta - respostas brutas do questionario inicial
   ---------------------------------------------------------------------
   Armazena cada resposta (pergunta -> valor) que alimenta o perfil de
   Preferencia. Mantido separado para rastreabilidade (auditoria do AIV).
   Caminho unico de cascade (apenas Conta_turista) -> CASCADE permitido.
   ===================================================================== */
IF OBJECT_ID('dbo.Questionario_Resposta', 'U') IS NULL
CREATE TABLE dbo.Questionario_Resposta (
    id_resposta  INT IDENTITY(1,1) NOT NULL,
    fk_turista   INT               NOT NULL,
    pergunta     NVARCHAR(200)     NOT NULL,
    resposta     NVARCHAR(MAX)     NOT NULL,
    respondido_em DATETIME2        NOT NULL
                 CONSTRAINT DF_Questionario_data DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT PK_Questionario_Resposta PRIMARY KEY (id_resposta),
    CONSTRAINT FK_Questionario_ContaTurista FOREIGN KEY (fk_turista)
        REFERENCES dbo.Conta_turista (id_turista)
        ON DELETE CASCADE   -- caminho unico: OK
);
GO

/* =====================================================================
   Avaliacao - avaliacoes de pacotes pelos turistas (RF8)
   ---------------------------------------------------------------------
   nota 1..5; comentario em texto livre. Alimenta o IA_Feedback.
   FK para Pacote usa NO ACTION (o turista ja cascateia; evita conflito
   de multiplos caminhos). FK para Conta_turista com NO ACTION tambem,
   para nao criar segundo caminho de cascade ate Pacote/Usuario.
   ===================================================================== */
IF OBJECT_ID('dbo.Avaliacao', 'U') IS NULL
CREATE TABLE dbo.Avaliacao (
    id_avaliacao INT IDENTITY(1,1) NOT NULL,
    fk_turista   INT               NOT NULL,
    fk_pacote    INT               NOT NULL,
    nota         INT               NOT NULL,
    comentario   NVARCHAR(MAX)     NULL,
    data         DATETIME2         NOT NULL
                 CONSTRAINT DF_Avaliacao_data DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT PK_Avaliacao PRIMARY KEY (id_avaliacao),
    CONSTRAINT FK_Avaliacao_ContaTurista FOREIGN KEY (fk_turista)
        REFERENCES dbo.Conta_turista (id_turista)
        ON DELETE NO ACTION,
    CONSTRAINT FK_Avaliacao_Pacote FOREIGN KEY (fk_pacote)
        REFERENCES dbo.Pacote (id_pacote)
        ON DELETE NO ACTION,
    CONSTRAINT CK_Avaliacao_nota CHECK (nota BETWEEN 1 AND 5),
    -- Um turista avalia um pacote no maximo uma vez:
    CONSTRAINT UQ_Avaliacao_turista_pacote UNIQUE (fk_turista, fk_pacote)
);
GO

/* =====================================================================
   IA_Feedback - feedback agregado pelo AIV por pacote (RF8)
   ---------------------------------------------------------------------
   score_agregado : media/ponderacao das avaliacoes (0..5).
   resumo         : sintese textual gerada pelo AIV.
   1 registro por pacote (UNIQUE). Atualizado por trigger (ver 04).
   Caminho unico de cascade (apenas Pacote) -> CASCADE permitido.
   ===================================================================== */
IF OBJECT_ID('dbo.IA_Feedback', 'U') IS NULL
CREATE TABLE dbo.IA_Feedback (
    id_feedback       INT IDENTITY(1,1) NOT NULL,
    fk_pacote         INT               NOT NULL,
    score_agregado    DECIMAL(4,2)      NULL,     -- 0.00 .. 5.00
    total_avaliacoes  INT               NOT NULL
                      CONSTRAINT DF_IAFeedback_total DEFAULT (0),
    resumo            NVARCHAR(MAX)     NULL,
    data_atualizacao  DATETIME2         NOT NULL
                      CONSTRAINT DF_IAFeedback_data DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT PK_IA_Feedback PRIMARY KEY (id_feedback),
    CONSTRAINT UQ_IA_Feedback_pacote UNIQUE (fk_pacote),
    CONSTRAINT FK_IA_Feedback_Pacote FOREIGN KEY (fk_pacote)
        REFERENCES dbo.Pacote (id_pacote)
        ON DELETE CASCADE,  -- caminho unico: OK
    CONSTRAINT CK_IA_Feedback_score CHECK (score_agregado IS NULL OR score_agregado BETWEEN 0 AND 5)
);
GO
