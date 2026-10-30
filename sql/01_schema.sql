/* =====================================================================
   Wanderlust Viagens - Camada de banco de dados (SQL Server / T-SQL)
   Script 01 - Schema base (DDL)
   ---------------------------------------------------------------------
   Traducao para T-SQL do DDL MySQL do documento de requisitos.
   Regras de traducao aplicadas:
     - INT AUTO_INCREMENT  -> INT IDENTITY(1,1)
     - VARCHAR             -> NVARCHAR (suporte a acentos/PT e nome social, RNF1)
     - TEXT                -> NVARCHAR(MAX)
     - DATE                -> DATE (inalterado)
     - DATETIME            -> DATETIME2
     - DECIMAL             -> DECIMAL (inalterado)
   ---------------------------------------------------------------------
   IMPORTANTE (multiplos caminhos de cascade no SQL Server):
     As tabelas Conta_turista e Conta_colaborador usam ON DELETE CASCADE
     para Usuario (um unico caminho cada -> permitido).
     A tabela Venda referencia AO MESMO TEMPO Conta_turista e
     Conta_colaborador; se ambas cascateassem, haveria multiplos caminhos
     de cascade para Usuario e o SQL Server rejeitaria o schema
     (erro 1785). Por isso as FKs de Venda (e as FKs a jusante em
     Passagem e Obtem) usam ON DELETE NO ACTION.
   Ordem de execucao: ver sql/README.md (01 -> 05).
   ===================================================================== */

/* ---------------------------------------------------------------------
   Criacao do banco (equivalente a CREATE DATABASE IF NOT EXISTS)
   --------------------------------------------------------------------- */
IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = 'agencia_viagens')
    CREATE DATABASE agencia_viagens;
GO

USE agencia_viagens;
GO

/* =====================================================================
   1) Destino
   ===================================================================== */
IF OBJECT_ID('dbo.Destino', 'U') IS NULL
CREATE TABLE dbo.Destino (
    id_destino  INT IDENTITY(1,1) NOT NULL,
    cidade      NVARCHAR(100)     NOT NULL,
    estado      NVARCHAR(50)      NOT NULL,
    pais        NVARCHAR(50)      NOT NULL,
    categoria   NVARCHAR(50)      NULL,
    descricao   NVARCHAR(MAX)     NULL,   -- TEXT no MySQL
    CONSTRAINT PK_Destino PRIMARY KEY (id_destino)
);
GO

/* =====================================================================
   2) Usuario
   ---------------------------------------------------------------------
   Extensoes coerentes ao modelo (documentadas):
     - nome_social, pronome : design inclusivo (RNF1).
     - email UNIQUE         : login e contato (RF1/RF2).
     - telefone             : canal de SMS para 2FA (RNF3).
   As credenciais sensiveis (hash de senha, segredo TOTP) ficam
   isoladas na tabela Credencial (1:1), separando dados de autenticacao
   dos dados de perfil (boa pratica de LGPD/RNF3).
   ===================================================================== */
IF OBJECT_ID('dbo.Usuario', 'U') IS NULL
CREATE TABLE dbo.Usuario (
    id_passageiro   INT IDENTITY(1,1) NOT NULL,
    nome            NVARCHAR(150)     NOT NULL,
    nome_social     NVARCHAR(150)     NULL,     -- extensao: design inclusivo (RNF1)
    pronome         NVARCHAR(30)      NULL,     -- extensao: design inclusivo (RNF1)
    data_nascimento DATE              NOT NULL,
    cpf             NVARCHAR(14)      NOT NULL,
    cep             NVARCHAR(9)       NULL,
    email           NVARCHAR(254)     NULL,     -- extensao: login/contato (RF1/RF2)
    telefone        NVARCHAR(20)      NULL,     -- extensao: SMS 2FA (RNF3)
    papel           NVARCHAR(20)      NOT NULL  -- extensao: role (Turista/Agente/Administrador)
                    CONSTRAINT DF_Usuario_papel DEFAULT ('Turista'),
    CONSTRAINT PK_Usuario PRIMARY KEY (id_passageiro),
    CONSTRAINT UQ_Usuario_cpf   UNIQUE (cpf),
    CONSTRAINT UQ_Usuario_email UNIQUE (email),
    CONSTRAINT CK_Usuario_papel CHECK (papel IN ('Turista', 'Agente', 'Administrador'))
);
GO

/* =====================================================================
   Credencial (extensao 1:1 com Usuario) - dados de autenticacao
   ---------------------------------------------------------------------
   Separa segredos (hash, TOTP) do perfil. Nunca armazena senha em texto.
   Caminho unico de cascade (apenas Usuario), portanto ON DELETE CASCADE
   e permitido aqui.
   ===================================================================== */
IF OBJECT_ID('dbo.Credencial', 'U') IS NULL
CREATE TABLE dbo.Credencial (
    id_usuario   INT             NOT NULL,
    senha_hash   NVARCHAR(255)   NOT NULL,            -- hash (ex.: bcrypt/argon2), nunca texto puro
    totp_secret  NVARCHAR(64)    NULL,                -- segredo TOTP para 2FA (RNF3)
    two_factor   BIT             NOT NULL
                 CONSTRAINT DF_Credencial_2fa DEFAULT (0),
    atualizado_em DATETIME2      NOT NULL
                 CONSTRAINT DF_Credencial_atualizado DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT PK_Credencial PRIMARY KEY (id_usuario),
    CONSTRAINT FK_Credencial_Usuario FOREIGN KEY (id_usuario)
        REFERENCES dbo.Usuario (id_passageiro)
        ON DELETE CASCADE   -- caminho unico: OK
);
GO

/* =====================================================================
   3) Pacote
   ---------------------------------------------------------------------
   Extensoes coerentes (RF3/RF7 - busca e recomendacao do AIV):
     - tipo_viagem : ex. 'Praia', 'Aventura', 'Cultural', 'Urbano'.
     - nivel       : ex. 'Economico', 'Conforto', 'Luxo'.
   ===================================================================== */
IF OBJECT_ID('dbo.Pacote', 'U') IS NULL
CREATE TABLE dbo.Pacote (
    id_pacote   INT IDENTITY(1,1) NOT NULL,
    preco_base  DECIMAL(10,2)     NOT NULL,
    data_inicio DATE              NOT NULL,
    data_fim    DATE              NOT NULL,
    estoque     INT               NOT NULL,
    tipo_viagem NVARCHAR(50)      NULL,   -- extensao: filtro de busca/recomendacao (RF3/RF7)
    nivel       NVARCHAR(50)      NULL,   -- extensao: filtro de busca/recomendacao (RF3/RF7)
    CONSTRAINT PK_Pacote PRIMARY KEY (id_pacote),
    CONSTRAINT CK_Pacote_estoque CHECK (estoque >= 0),
    CONSTRAINT CK_Pacote_datas   CHECK (data_fim >= data_inicio)
);
GO

/* =====================================================================
   4) Conta_colaborador (especializacao de Usuario)
   ---------------------------------------------------------------------
   ON DELETE CASCADE para Usuario: caminho unico -> permitido.
   ===================================================================== */
IF OBJECT_ID('dbo.Conta_colaborador', 'U') IS NULL
CREATE TABLE dbo.Conta_colaborador (
    id_colaborador INT           NOT NULL,
    cargo          NVARCHAR(50)  NOT NULL,
    comissao       DECIMAL(5,2)  NULL,
    CONSTRAINT PK_Conta_colaborador PRIMARY KEY (id_colaborador),
    CONSTRAINT FK_Conta_colaborador_Usuario FOREIGN KEY (id_colaborador)
        REFERENCES dbo.Usuario (id_passageiro)
        ON DELETE CASCADE   -- caminho unico: OK
);
GO

/* =====================================================================
   5) Conta_turista (especializacao de Usuario)
   ---------------------------------------------------------------------
   ON DELETE CASCADE para Usuario: caminho unico -> permitido.
   ===================================================================== */
IF OBJECT_ID('dbo.Conta_turista', 'U') IS NULL
CREATE TABLE dbo.Conta_turista (
    id_turista INT NOT NULL,
    CONSTRAINT PK_Conta_turista PRIMARY KEY (id_turista),
    CONSTRAINT FK_Conta_turista_Usuario FOREIGN KEY (id_turista)
        REFERENCES dbo.Usuario (id_passageiro)
        ON DELETE CASCADE   -- caminho unico: OK
);
GO

/* =====================================================================
   6) Viagem
   ---------------------------------------------------------------------
   data_partida / data_chegada: DATETIME (MySQL) -> DATETIME2.
   ===================================================================== */
IF OBJECT_ID('dbo.Viagem', 'U') IS NULL
CREATE TABLE dbo.Viagem (
    id_viagem            INT IDENTITY(1,1) NOT NULL,
    data_partida         DATETIME2         NOT NULL,   -- era DATETIME no MySQL
    data_chegada         DATETIME2         NOT NULL,   -- era DATETIME no MySQL
    meio_transporte      NVARCHAR(50)      NOT NULL,
    duracao              NVARCHAR(30)      NULL,
    fk_Destino_id_destino INT              NOT NULL,
    CONSTRAINT PK_Viagem PRIMARY KEY (id_viagem),
    CONSTRAINT FK_Viagem_Destino FOREIGN KEY (fk_Destino_id_destino)
        REFERENCES dbo.Destino (id_destino)
        ON DELETE NO ACTION,
    CONSTRAINT CK_Viagem_datas CHECK (data_chegada >= data_partida)
);
GO

/* =====================================================================
   7) Hospedagem
   ===================================================================== */
IF OBJECT_ID('dbo.Hospedagem', 'U') IS NULL
CREATE TABLE dbo.Hospedagem (
    id_hospedagem        INT IDENTITY(1,1) NOT NULL,
    cep                  NVARCHAR(9)       NOT NULL,
    rua                  NVARCHAR(150)     NOT NULL,
    numero               INT               NOT NULL,
    nome                 NVARCHAR(100)     NOT NULL,
    tipo_quarto          NVARCHAR(50)      NULL,
    regime_alimentacao   NVARCHAR(50)      NULL,
    fk_Pacote_id_pacote  INT               NOT NULL,
    CONSTRAINT PK_Hospedagem PRIMARY KEY (id_hospedagem),
    CONSTRAINT FK_Hospedagem_Pacote FOREIGN KEY (fk_Pacote_id_pacote)
        REFERENCES dbo.Pacote (id_pacote)
        ON DELETE CASCADE   -- caminho unico (apenas Pacote): OK
);
GO

/* =====================================================================
   8) Venda
   ---------------------------------------------------------------------
   data_venda DATETIME2: adicionada conforme nota da secao 5.3.
   ATENCAO: FKs para Conta_turista e Conta_colaborador usam
   ON DELETE NO ACTION. Se ambas fossem CASCADE, formariam multiplos
   caminhos de cascade ate Usuario e o SQL Server rejeitaria o schema.
   ===================================================================== */
IF OBJECT_ID('dbo.Venda', 'U') IS NULL
CREATE TABLE dbo.Venda (
    id_venda             INT IDENTITY(1,1) NOT NULL,
    valor_total          DECIMAL(10,2)     NOT NULL,
    status_pagamento     NVARCHAR(30)      NOT NULL,
    forma_pagamento      NVARCHAR(50)      NOT NULL,
    data_venda           DATETIME2         NOT NULL   -- nota da secao 5.3
                         CONSTRAINT DF_Venda_data DEFAULT (SYSUTCDATETIME()),
    fk_conta_turista     INT               NOT NULL,
    fk_conta_colaborador INT               NULL,
    CONSTRAINT PK_Venda PRIMARY KEY (id_venda),
    -- NO ACTION evita multiplos caminhos de cascade (erro 1785 do SQL Server):
    CONSTRAINT FK_Venda_ContaTurista FOREIGN KEY (fk_conta_turista)
        REFERENCES dbo.Conta_turista (id_turista)
        ON DELETE NO ACTION,
    CONSTRAINT FK_Venda_ContaColaborador FOREIGN KEY (fk_conta_colaborador)
        REFERENCES dbo.Conta_colaborador (id_colaborador)
        ON DELETE NO ACTION,
    CONSTRAINT CK_Venda_status CHECK
        (status_pagamento IN ('Pendente', 'Pago', 'Cancelado', 'Estornado'))
);
GO

/* =====================================================================
   9) Passagem
   ---------------------------------------------------------------------
   FKs com NO ACTION (evita caminhos de cascade conflitantes via Venda).
   Unicidade de assento por viagem garantida por constraint (anti-overbooking).
   ===================================================================== */
IF OBJECT_ID('dbo.Passagem', 'U') IS NULL
CREATE TABLE dbo.Passagem (
    id_passagem    INT IDENTITY(1,1) NOT NULL,
    numero_assento NVARCHAR(10)      NOT NULL,
    classe         NVARCHAR(30)      NOT NULL,
    fk_id_viagem   INT               NOT NULL,
    fk_id_venda    INT               NOT NULL,
    CONSTRAINT PK_Passagem PRIMARY KEY (id_passagem),
    CONSTRAINT FK_Passagem_Viagem FOREIGN KEY (fk_id_viagem)
        REFERENCES dbo.Viagem (id_viagem)
        ON DELETE NO ACTION,
    CONSTRAINT FK_Passagem_Venda FOREIGN KEY (fk_id_venda)
        REFERENCES dbo.Venda (id_venda)
        ON DELETE NO ACTION,
    -- Impede overbooking: mesmo assento nao pode ser vendido 2x na mesma viagem
    CONSTRAINT UQ_Passagem_assento_viagem UNIQUE (fk_id_viagem, numero_assento)
);
GO

/* =====================================================================
   10) Obtem (associativa Pacote x Venda)
   ---------------------------------------------------------------------
   PK composta. FKs com NO ACTION (Venda ja e NO ACTION a jusante).
   ===================================================================== */
IF OBJECT_ID('dbo.Obtem', 'U') IS NULL
CREATE TABLE dbo.Obtem (
    fk_Pacote_id_pacote INT NOT NULL,
    fk_Venda_id_venda   INT NOT NULL,
    CONSTRAINT PK_Obtem PRIMARY KEY (fk_Pacote_id_pacote, fk_Venda_id_venda),
    CONSTRAINT FK_Obtem_Pacote FOREIGN KEY (fk_Pacote_id_pacote)
        REFERENCES dbo.Pacote (id_pacote)
        ON DELETE NO ACTION,
    CONSTRAINT FK_Obtem_Venda FOREIGN KEY (fk_Venda_id_venda)
        REFERENCES dbo.Venda (id_venda)
        ON DELETE NO ACTION
);
GO
