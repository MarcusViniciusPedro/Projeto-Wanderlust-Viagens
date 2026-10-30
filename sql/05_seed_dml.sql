/* =====================================================================
   Wanderlust Viagens - Camada de banco de dados (SQL Server / T-SQL)
   Script 05 - Seed (dados de exemplo) + consultas CRUD representativas
   ---------------------------------------------------------------------
   Popula todas as entidades com dados de exemplo e demonstra consultas
   CRUD (secao 5.4). Observacoes:
     - As senhas sao apenas placeholders de HASH (nunca texto puro).
     - IDs de IDENTITY sao recuperados via SCOPE_IDENTITY para manter o
       script robusto independentemente dos valores gerados.
   Pre-requisito: executar 01 a 04 antes deste script.
   ===================================================================== */

USE agencia_viagens;
GO

/* ---------------------------------------------------------------------
   1) Destinos
   --------------------------------------------------------------------- */
INSERT INTO dbo.Destino (cidade, estado, pais, categoria, descricao) VALUES
    (N'Rio de Janeiro', N'RJ', N'Brasil',    N'Praia',    N'Praias famosas e Pao de Acucar.'),
    (N'Gramado',        N'RS', N'Brasil',    N'Serra',    N'Clima europeu na serra gaucha.'),
    (N'Paris',          N'IDF',N'Franca',    N'Cultural', N'Museus, gastronomia e arquitetura.');
GO

/* ---------------------------------------------------------------------
   2) Usuarios (um turista e um colaborador) + Credenciais
   --------------------------------------------------------------------- */
DECLARE @id_turista_user INT;
DECLARE @id_colab_user   INT;

INSERT INTO dbo.Usuario (nome, nome_social, pronome, data_nascimento, cpf, cep, email, telefone, papel)
VALUES (N'Ana Beatriz Souza', NULL, N'ela/dela', '1995-04-12', N'111.222.333-44', N'22000-000',
        N'ana.souza@example.com', N'+5521999990000', N'Turista');
SET @id_turista_user = CAST(SCOPE_IDENTITY() AS INT);

INSERT INTO dbo.Usuario (nome, nome_social, pronome, data_nascimento, cpf, cep, email, telefone, papel)
VALUES (N'Carlos Mendes', N'Carla Mendes', N'ela/dela', '1988-09-30', N'555.666.777-88', N'01000-000',
        N'carla.mendes@example.com', N'+5511988887777', N'Agente');
SET @id_colab_user = CAST(SCOPE_IDENTITY() AS INT);

-- Especializacoes:
INSERT INTO dbo.Conta_turista (id_turista) VALUES (@id_turista_user);
INSERT INTO dbo.Conta_colaborador (id_colaborador, cargo, comissao)
VALUES (@id_colab_user, N'Agente de Viagens', 5.50);

-- Credenciais (hashes de exemplo; valores ficticios):
INSERT INTO dbo.Credencial (id_usuario, senha_hash, totp_secret, two_factor)
VALUES
    (@id_turista_user, N'$2b$12$exemplodehashficticioparaanabsouza......', NULL, 0),
    (@id_colab_user,   N'$2b$12$exemplodehashficticioparacarlamendes....', N'JBSWY3DPEHPK3PXP', 1);
GO

/* ---------------------------------------------------------------------
   3) Pacotes (com extensoes tipo_viagem/nivel)
   --------------------------------------------------------------------- */
INSERT INTO dbo.Pacote (preco_base, data_inicio, data_fim, estoque, tipo_viagem, nivel) VALUES
    (2500.00, '2025-12-20', '2025-12-27', 10, N'Praia',    N'Conforto'),
    (1800.00, '2025-07-10', '2025-07-15', 5,  N'Serra',    N'Economico'),
    (9800.00, '2026-05-01', '2026-05-12', 8,  N'Cultural', N'Luxo');
GO

/* ---------------------------------------------------------------------
   4) Viagens (vinculadas a destinos) e Hospedagens (vinculadas a pacotes)
   --------------------------------------------------------------------- */
INSERT INTO dbo.Viagem (data_partida, data_chegada, meio_transporte, duracao, fk_Destino_id_destino) VALUES
    ('2025-12-20T08:00:00', '2025-12-20T10:00:00', N'Aviao', N'2h',  1),
    ('2025-07-10T07:00:00', '2025-07-10T13:00:00', N'Onibus',N'6h',  2),
    ('2026-05-01T22:00:00', '2026-05-02T13:00:00', N'Aviao', N'11h', 3);
GO

INSERT INTO dbo.Hospedagem (cep, rua, numero, nome, tipo_quarto, regime_alimentacao, fk_Pacote_id_pacote) VALUES
    (N'22010-000', N'Av. Atlantica',   1500, N'Hotel Copa Mar',   N'Duplo',       N'Meia pensao',   1),
    (N'95670-000', N'Rua das Hortensias', 200, N'Pousada Serrana', N'Standard',    N'Cafe da manha', 2),
    (N'75001',     N'Rue de Rivoli',     10, N'Hotel Louvre',     N'Suite',       N'Pensao completa', 3);
GO

/* ---------------------------------------------------------------------
   5) Preferencias e respostas do questionario (AIV)
   --------------------------------------------------------------------- */
DECLARE @turista INT = (SELECT TOP 1 id_turista FROM dbo.Conta_turista ORDER BY id_turista);

INSERT INTO dbo.Preferencia (fk_turista, tipo_viagem, nivel, orcamento_max, estacao_preferida, observacoes)
VALUES (@turista, N'Praia', N'Conforto', 3000.00, N'Verao', N'Prefere destinos com praia e vida noturna.');

INSERT INTO dbo.Questionario_Resposta (fk_turista, pergunta, resposta) VALUES
    (@turista, N'Qual o seu tipo de viagem preferido?', N'Praia'),
    (@turista, N'Qual o seu nivel de conforto desejado?', N'Conforto'),
    (@turista, N'Qual o seu orcamento maximo?', N'3000');
GO

/* ---------------------------------------------------------------------
   6) Uma venda completa usando a procedure (Venda + Obtem + baixa estoque)
   --------------------------------------------------------------------- */
DECLARE @turista2   INT = (SELECT TOP 1 id_turista FROM dbo.Conta_turista ORDER BY id_turista);
DECLARE @colab      INT = (SELECT TOP 1 id_colaborador FROM dbo.Conta_colaborador ORDER BY id_colaborador);
DECLARE @pacote1    INT = (SELECT TOP 1 id_pacote FROM dbo.Pacote ORDER BY id_pacote);
DECLARE @nova_venda INT;

EXEC dbo.sp_registrar_venda
    @fk_conta_turista     = @turista2,
    @fk_pacote            = @pacote1,
    @forma_pagamento      = N'Cartao de credito',
    @fk_conta_colaborador = @colab,
    @status_pagamento     = N'Pago',
    @id_venda_out         = @nova_venda OUTPUT;

-- Emissao de uma passagem para a venda recem-criada:
DECLARE @viagem1 INT = (SELECT TOP 1 id_viagem FROM dbo.Viagem ORDER BY id_viagem);
INSERT INTO dbo.Passagem (numero_assento, classe, fk_id_viagem, fk_id_venda)
VALUES (N'12A', N'Economica', @viagem1, @nova_venda);
GO

/* ---------------------------------------------------------------------
   7) Avaliacao (dispara a trigger que atualiza IA_Feedback)
   --------------------------------------------------------------------- */
DECLARE @turista3 INT = (SELECT TOP 1 id_turista FROM dbo.Conta_turista ORDER BY id_turista);
DECLARE @pacote2  INT = (SELECT TOP 1 id_pacote FROM dbo.Pacote ORDER BY id_pacote);

INSERT INTO dbo.Avaliacao (fk_turista, fk_pacote, nota, comentario)
VALUES (@turista3, @pacote2, 5, N'Experiencia excelente, recomendo!');
GO

/* =====================================================================
   CONSULTAS CRUD REPRESENTATIVAS (secao 5.4)
   ---------------------------------------------------------------------
   Exemplos executaveis de leitura, atualizacao e remocao.
   ===================================================================== */

-- READ (RF3): busca de pacotes por tipo de viagem, nivel e orcamento,
-- apenas com estoque disponivel.
SELECT p.id_pacote, p.tipo_viagem, p.nivel, p.preco_base, p.data_inicio, p.estoque
FROM dbo.Pacote AS p
WHERE p.tipo_viagem = N'Praia'
  AND p.nivel = N'Conforto'
  AND p.preco_base <= 3000.00
  AND p.estoque > 0
ORDER BY p.data_inicio;
GO

-- READ: vendas detalhadas (view consolidada).
SELECT * FROM dbo.vw_vendas_detalhadas ORDER BY data_venda DESC;
GO

-- READ (RF10): incidencia de turistas por destino e ano.
SELECT * FROM dbo.vw_turistas_por_destino_ano ORDER BY ano DESC, qtd_turistas DESC;
GO

-- READ: score agregado do AIV por pacote.
SELECT f.fk_pacote, f.score_agregado, f.total_avaliacoes, f.data_atualizacao
FROM dbo.IA_Feedback AS f
ORDER BY f.score_agregado DESC;
GO

-- UPDATE: atualizar o status de pagamento de uma venda.
UPDATE dbo.Venda
SET status_pagamento = N'Pago'
WHERE id_venda = (SELECT TOP 1 id_venda FROM dbo.Venda ORDER BY id_venda);
GO

-- DELETE (exemplo): remover uma resposta de questionario especifica.
DELETE FROM dbo.Questionario_Resposta
WHERE pergunta = N'Qual o seu orcamento maximo?';
GO
