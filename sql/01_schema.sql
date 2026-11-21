-- =====================================================================
-- Wanderlust Viagens - Banco de dados (SQL Server / T-SQL)
-- Script 01 - Criacao do banco e tabelas base
-- ---------------------------------------------------------------------
-- Estilo direto para rodar no VS Code (extensao mssql), Azure Data
-- Studio ou SSMS: CREATE DATABASE, USE e CREATE TABLE em sequencia.
-- Tipos: NVARCHAR para texto (acentos/PT e nome social), DECIMAL para
-- dinheiro, DATETIME2 para data/hora, DATE para datas.
-- As FKs sao declaradas sem ON DELETE (NO ACTION por padrao), o que
-- tambem evita o erro 1785 de multiplos caminhos de cascade.
-- Execute os scripts em ordem: 01 -> 02 -> 03 -> 04 -> 05.
-- =====================================================================

CREATE DATABASE agencia_viagens;
GO

USE agencia_viagens;
GO

-- 1) Destino
CREATE TABLE Destino (
    id_destino INT IDENTITY(1,1) NOT NULL,
    cidade     NVARCHAR(100) NOT NULL,
    estado     NVARCHAR(50) NOT NULL,
    pais       NVARCHAR(50) NOT NULL,
    descricao  NVARCHAR(MAX) NULL,
    PRIMARY KEY (id_destino)
)

-- 2) Usuario (base para turista e colaborador)
-- nome_social/pronome: design inclusivo. email: login/contato.
-- telefone: canal de SMS para 2FA.
CREATE TABLE Usuario (
    id_passageiro   INT IDENTITY(1,1) NOT NULL,
    nome            NVARCHAR(150) NOT NULL,
    nome_social     NVARCHAR(150) NULL,
    pronome         NVARCHAR(30) NULL,
    data_nascimento DATE NOT NULL,
    cpf             NVARCHAR(14) NOT NULL,
    cep             NVARCHAR(9) NULL,
    email           NVARCHAR(254) NULL,
    telefone        NVARCHAR(20) NULL,
    papel           NVARCHAR(20) NOT NULL DEFAULT ('Turista'),
    status          NVARCHAR(20) NOT NULL DEFAULT ('Ativo'),
    PRIMARY KEY (id_passageiro),
    UNIQUE (cpf),
    UNIQUE (email),
    CHECK (papel IN ('Turista', 'Agente', 'Administrador')),
    CHECK (status IN ('Ativo', 'Banido', 'Denunciado'))
)

-- Credencial (1:1 com Usuario) - dados de autenticacao isolados do perfil.
-- Nunca armazena senha em texto puro, apenas o hash.
CREATE TABLE Credencial (
    id_usuario    INT NOT NULL,
    senha_hash    NVARCHAR(255) NOT NULL,
    totp_secret   NVARCHAR(64) NULL,
    two_factor    BIT NOT NULL DEFAULT (0),
    atualizado_em DATETIME2 NOT NULL DEFAULT (SYSUTCDATETIME()),
    PRIMARY KEY (id_usuario),
    FOREIGN KEY (id_usuario) REFERENCES Usuario (id_passageiro)
)

-- 3) Pacote (tipo_viagem/nivel apoiam a busca e a recomendacao do AIV)
CREATE TABLE Pacote (
    id_pacote   INT IDENTITY(1,1) NOT NULL,
    preco_base  DECIMAL(10,2) NOT NULL,
    data_inicio DATE NOT NULL,
    data_fim    DATE NOT NULL,
    estoque     INT NOT NULL,
    tipo_viagem NVARCHAR(50) NULL,
    nivel       NVARCHAR(50) NULL,
    fk_destino  INT NOT NULL,
    PRIMARY KEY (id_pacote),
    FOREIGN KEY (fk_destino) REFERENCES Destino (id_destino),
    CHECK (estoque >= 0),
    CHECK (data_fim >= data_inicio)
)

-- 4) Conta_colaborador (especializacao de Usuario)
CREATE TABLE Conta_colaborador (
    id_colaborador INT NOT NULL,
    cargo          NVARCHAR(50) NOT NULL,
    comissao       DECIMAL(5,2) NULL,
    PRIMARY KEY (id_colaborador),
    FOREIGN KEY (id_colaborador) REFERENCES Usuario (id_passageiro)
)

-- 5) Conta_turista (especializacao de Usuario)
CREATE TABLE Conta_turista (
    id_turista INT NOT NULL,
    PRIMARY KEY (id_turista),
    FOREIGN KEY (id_turista) REFERENCES Usuario (id_passageiro)
)

-- 6) Viagem (vinculada a um destino)
CREATE TABLE Viagem (
    id_viagem             INT IDENTITY(1,1) NOT NULL,
    data_partida          DATETIME2 NOT NULL,
    data_chegada          DATETIME2 NOT NULL,
    meio_transporte       NVARCHAR(50) NOT NULL,
    duracao               NVARCHAR(30) NULL,
    fk_Destino_id_destino INT NOT NULL,
    PRIMARY KEY (id_viagem),
    FOREIGN KEY (fk_Destino_id_destino) REFERENCES Destino (id_destino),
    CHECK (data_chegada >= data_partida)
)

-- 7) Hospedagem (vinculada a um pacote)
CREATE TABLE Hospedagem (
    id_hospedagem       INT IDENTITY(1,1) NOT NULL,
    cep                 NVARCHAR(9) NOT NULL,
    rua                 NVARCHAR(150) NOT NULL,
    numero              INT NOT NULL,
    nome                NVARCHAR(100) NOT NULL,
    tipo_quarto         NVARCHAR(50) NULL,
    regime_alimentacao  NVARCHAR(50) NULL,
    fk_Pacote_id_pacote INT NOT NULL,
    PRIMARY KEY (id_hospedagem),
    FOREIGN KEY (fk_Pacote_id_pacote) REFERENCES Pacote (id_pacote)
)

-- 8) Venda
-- data_venda tem DEFAULT (agora UTC). status_pagamento e forma_pagamento
-- com CHECK; forma_pagamento usa os mesmos valores do enum FormaPagamento
-- do Python (app/vendas/schemas.py).
CREATE TABLE Venda (
    id_venda             INT IDENTITY(1,1) NOT NULL,
    valor_total          DECIMAL(10,2) NOT NULL,
    status_pagamento     NVARCHAR(30) NOT NULL,
    forma_pagamento      NVARCHAR(50) NOT NULL,
    data_venda           DATETIME2 NOT NULL DEFAULT (SYSUTCDATETIME()),
    fk_conta_turista     INT NOT NULL,
    fk_conta_colaborador INT NULL,
    PRIMARY KEY (id_venda),
    FOREIGN KEY (fk_conta_turista) REFERENCES Conta_turista (id_turista),
    FOREIGN KEY (fk_conta_colaborador) REFERENCES Conta_colaborador (id_colaborador),
    CHECK (status_pagamento IN ('Pendente', 'Pago', 'Cancelado', 'Estornado')),
    CHECK (forma_pagamento IN ('debito', 'credito', 'pix', 'boleto'))
)

-- 9) Passagem
-- UNIQUE (fk_id_viagem, numero_assento) impede overbooking (mesmo assento
-- vendido duas vezes na mesma viagem).
CREATE TABLE Passagem (
    id_passagem    INT IDENTITY(1,1) NOT NULL,
    numero_assento NVARCHAR(10) NOT NULL,
    classe         NVARCHAR(30) NOT NULL,
    fk_id_viagem   INT NOT NULL,
    fk_id_venda    INT NOT NULL,
    PRIMARY KEY (id_passagem),
    FOREIGN KEY (fk_id_viagem) REFERENCES Viagem (id_viagem),
    FOREIGN KEY (fk_id_venda) REFERENCES Venda (id_venda),
    UNIQUE (fk_id_viagem, numero_assento)
)

-- 10) Obtem (associativa Pacote x Venda, PK composta)
CREATE TABLE Obtem (
    fk_Pacote_id_pacote INT NOT NULL,
    fk_Venda_id_venda   INT NOT NULL,
    PRIMARY KEY (fk_Pacote_id_pacote, fk_Venda_id_venda),
    FOREIGN KEY (fk_Pacote_id_pacote) REFERENCES Pacote (id_pacote),
    FOREIGN KEY (fk_Venda_id_venda) REFERENCES Venda (id_venda)
)
GO
