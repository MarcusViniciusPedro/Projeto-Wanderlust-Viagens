-- =====================================================================
-- Wanderlust Viagens - Banco de dados (SQL Server / T-SQL)
-- Script 05 - Dados de exemplo + consultas CRUD representativas
-- ---------------------------------------------------------------------
-- Popula as entidades e demonstra consultas. As senhas sao apenas
-- placeholders de HASH (nunca texto puro).
-- Os INSERT sem lista de colunas comecam na PRIMEIRA coluna que nao e
-- IDENTITY (a PK auto-incremento e gerada pelo banco e nao recebe valor).
-- Como as insercoes rodam de cima para baixo, os ids gerados sao
-- deterministicos (1, 2, 3...), entao as FKs usam esses valores literais.
-- Pre-requisito: executar 01 a 04 antes deste script.
-- =====================================================================

USE agencia_viagens;
GO

-- 1) Destinos  -> ids 1, 2, 3
INSERT INTO Destino (cidade, estado, pais, descricao) VALUES
    (N'Rio de Janeiro', N'RJ', N'Brasil',  N'Praias famosas e Pao de Acucar.'),
    (N'Gramado',        N'RS', N'Brasil',  N'Clima europeu na serra gaucha.'),
    (N'Paris',          N'IDF',N'Franca',  N'Museus, gastronomia e arquitetura.');

-- 2) Usuarios  -> id 1 (turista), id 2 (colaborador)
-- Lista de colunas explicita: a coluna status (extensao, secao 4.1) fica no
-- DEFAULT ('Ativo'), sem precisar informar valor aqui.
INSERT INTO Usuario (nome, nome_social, pronome, data_nascimento, cpf, cep, email, telefone, papel) VALUES
    (N'Ana Beatriz Souza', NULL, N'ela/dela', '1995-04-12', N'111.222.333-44', N'22000-000', N'ana.souza@example.com', N'+5521999990000', N'Turista'),
    (N'Carlos Mendes', N'Carla Mendes', N'ela/dela', '1988-09-30', N'555.666.777-88', N'01000-000', N'carla.mendes@example.com', N'+5511988887777', N'Agente');

-- Especializacoes: usam os ids de Usuario gerados acima (1 turista, 2 colaborador).
INSERT INTO Conta_turista VALUES (1);
INSERT INTO Conta_colaborador VALUES (2, N'Agente de Viagens', 5.50);

-- Credenciais (lista de colunas explicita para deixar atualizado_em no DEFAULT).
INSERT INTO Credencial (id_usuario, senha_hash, totp_secret, two_factor) VALUES
    (1, N'$2b$12$exemplodehashficticioparaanabsouza......', NULL, 0),
    (2, N'$2b$12$exemplodehashficticioparacarlamendes....', N'JBSWY3DPEHPK3PXP', 1);

-- 3) Pacotes  -> ids 1, 2, 3
INSERT INTO Pacote VALUES
    (2500.00, '2025-12-20', '2025-12-27', 10, N'Praia',    N'Conforto',  1),
    (1800.00, '2025-07-10', '2025-07-15', 5,  N'Serra',    N'Economico', 2),
    (9800.00, '2026-05-01', '2026-05-12', 8,  N'Cultural', N'Luxo',      3);

-- 4) Viagens (destinos 1,2,3)  -> ids 1, 2, 3
INSERT INTO Viagem VALUES
    ('2025-12-20T08:00:00', '2025-12-20T10:00:00', N'Aviao',  N'2h',  1),
    ('2025-07-10T07:00:00', '2025-07-10T13:00:00', N'Onibus', N'6h',  2),
    ('2026-05-01T22:00:00', '2026-05-02T13:00:00', N'Aviao',  N'11h', 3);

-- 5) Hospedagens (pacotes 1,2,3)  -> ids 1, 2, 3
INSERT INTO Hospedagem VALUES
    (N'22010-000', N'Av. Atlantica',       1500, N'Hotel Copa Mar',  N'Duplo',    N'Meia pensao',     1),
    (N'95670-000', N'Rua das Hortensias',   200, N'Pousada Serrana', N'Standard', N'Cafe da manha',   2),
    (N'75001',     N'Rue de Rivoli',         10, N'Hotel Louvre',    N'Suite',    N'Pensao completa', 3);

-- 6) Preferencia e respostas do questionario do turista 1.
-- Preferencia usa lista de colunas explicita (atualizado_em fica no DEFAULT).
INSERT INTO Preferencia (fk_turista, tipo_viagem, nivel, orcamento_max, estacao_preferida, observacoes)
VALUES (1, N'Praia', N'Conforto', 3000.00, N'Verao', N'Prefere destinos com praia e vida noturna.');

INSERT INTO Questionario_Resposta (fk_turista, pergunta, resposta) VALUES
    (1, N'Qual o seu tipo de viagem preferido?', N'Praia'),
    (1, N'Qual o seu nivel de conforto desejado?', N'Conforto'),
    (1, N'Qual o seu orcamento maximo?', N'3000');
GO

-- 7) Uma venda completa via procedure (Venda + Obtem + baixa de estoque).
-- turista 1, colaborador 2, pacote 1 -> gera a Venda de id 1.
DECLARE @nova_venda INT;
EXEC sp_registrar_venda
    @fk_conta_turista     = 1,
    @fk_pacote            = 1,
    @forma_pagamento      = N'credito',
    @fk_conta_colaborador = 2,
    @status_pagamento     = N'Pago',
    @id_venda_out         = @nova_venda OUTPUT;

-- Emissao de uma passagem para a venda recem-criada (viagem 1).
INSERT INTO Passagem VALUES (N'12A', N'Economica', 1, @nova_venda);
GO

-- 8) Avaliacao do turista 1 para o pacote 2 (dispara a trigger do IA_Feedback).
-- Lista de colunas explicita (data fica no DEFAULT).
INSERT INTO Avaliacao (fk_turista, fk_pacote, nota, comentario)
VALUES (1, 2, 5, N'Experiencia excelente, recomendo!');
GO

-- =====================================================================
-- CONSULTAS CRUD REPRESENTATIVAS
-- =====================================================================

-- READ (RF3): busca de pacotes por tipo, nivel e orcamento, com estoque.
SELECT p.id_pacote, p.tipo_viagem, p.nivel, p.preco_base, p.data_inicio, p.estoque
FROM Pacote p
WHERE p.tipo_viagem = N'Praia'
  AND p.nivel = N'Conforto'
  AND p.preco_base <= 3000.00
  AND p.estoque > 0
ORDER BY p.data_inicio;

-- READ: vendas detalhadas (view consolidada).
SELECT * FROM vw_vendas_detalhadas ORDER BY data_venda DESC;

-- READ (RF10): incidencia de turistas por destino e ano.
SELECT * FROM vw_turistas_por_destino_ano ORDER BY ano DESC, qtd_turistas DESC;

-- READ: score agregado do AIV por pacote.
SELECT f.fk_pacote, f.score_agregado, f.total_avaliacoes, f.data_atualizacao
FROM IA_Feedback f
ORDER BY f.score_agregado DESC;

-- READ: idade do turista 1 usando a function.
SELECT u.nome, dbo.fn_calcular_idade(u.data_nascimento) AS idade
FROM Usuario u
WHERE u.id_passageiro = 1;

-- UPDATE: atualizar o status de pagamento da venda 1.
UPDATE Venda
SET status_pagamento = N'Pago'
WHERE id_venda = 1;

-- DELETE: remover uma resposta de questionario especifica.
DELETE FROM Questionario_Resposta
WHERE pergunta = N'Qual o seu orcamento maximo?';
GO
