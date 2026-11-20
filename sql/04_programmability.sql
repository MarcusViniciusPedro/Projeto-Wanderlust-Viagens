-- =====================================================================
-- Wanderlust Viagens - Banco de dados (SQL Server / T-SQL)
-- Script 04 - Programabilidade (function, views, procedure, triggers)
-- ---------------------------------------------------------------------
-- Cada objeto e criado no seu proprio lote (GO antes de cada CREATE,
-- pois precisam ser a primeira instrucao do lote).
-- Pre-requisito: executar 01_schema.sql e 02_aiv_tables.sql antes.
-- =====================================================================

USE agencia_viagens;
GO

-- fn_calcular_idade: idade em anos completos a partir da data de nascimento.
CREATE FUNCTION fn_calcular_idade (@data_nascimento DATE)
RETURNS INT
AS
BEGIN
    DECLARE @idade INT;
    SET @idade = DATEDIFF(YEAR, @data_nascimento, GETDATE())
        - CASE
            WHEN (MONTH(@data_nascimento) > MONTH(GETDATE()))
              OR (MONTH(@data_nascimento) = MONTH(GETDATE())
                  AND DAY(@data_nascimento) > DAY(GETDATE()))
            THEN 1 ELSE 0
          END;
    RETURN @idade;
END;
GO

-- vw_vendas_detalhadas: Venda + turista (Usuario) + pacotes (via Obtem).
CREATE VIEW vw_vendas_detalhadas
AS
SELECT
    v.id_venda,
    v.data_venda,
    v.valor_total,
    v.status_pagamento,
    v.forma_pagamento,
    ct.id_turista,
    u.nome        AS nome_turista,
    u.nome_social AS nome_social_turista,
    u.email       AS email_turista,
    p.id_pacote,
    p.tipo_viagem,
    p.nivel,
    p.preco_base
FROM Venda v
JOIN Conta_turista ct ON ct.id_turista = v.fk_conta_turista
JOIN Usuario u ON u.id_passageiro = ct.id_turista
JOIN Obtem o ON o.fk_Venda_id_venda = v.id_venda
JOIN Pacote p ON p.id_pacote = o.fk_Pacote_id_pacote;
GO

-- vw_turistas_por_destino_ano: incidencia de turistas por destino e ano
-- (RF10). O destino liga-se a venda via Passagem -> Viagem -> Destino.
CREATE VIEW vw_turistas_por_destino_ano
AS
SELECT
    d.id_destino,
    d.cidade,
    d.estado,
    d.pais,
    YEAR(v.data_venda)                 AS ano,
    COUNT(DISTINCT v.fk_conta_turista) AS qtd_turistas,
    COUNT(DISTINCT v.id_venda)         AS qtd_vendas
FROM Venda v
JOIN Passagem pg ON pg.fk_id_venda = v.id_venda
JOIN Viagem vi ON vi.id_viagem = pg.fk_id_viagem
JOIN Destino d ON d.id_destino = vi.fk_Destino_id_destino
GROUP BY d.id_destino, d.cidade, d.estado, d.pais, YEAR(v.data_venda);
GO

-- sp_registrar_venda: registra uma venda de forma atomica -
--   1) valida estoque; 2) insere a Venda; 3) insere o vinculo em Obtem;
--   4) baixa 1 unidade do estoque. Retorna o id_venda em @id_venda_out.
CREATE PROCEDURE sp_registrar_venda
    @fk_conta_turista     INT,
    @fk_pacote            INT,
    @forma_pagamento      NVARCHAR(50),
    @fk_conta_colaborador INT = NULL,
    @status_pagamento     NVARCHAR(30) = N'Pendente',
    @id_venda_out         INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    BEGIN TRY
        BEGIN TRANSACTION;

        DECLARE @preco DECIMAL(10,2);
        DECLARE @estoque INT;

        -- Bloqueia a linha do pacote para evitar corrida de estoque:
        SELECT @preco = preco_base, @estoque = estoque
        FROM Pacote WITH (UPDLOCK, ROWLOCK)
        WHERE id_pacote = @fk_pacote;

        IF @preco IS NULL
            THROW 50001, 'Pacote inexistente.', 1;

        IF @estoque <= 0
            THROW 50002, 'Estoque esgotado para o pacote informado.', 1;

        INSERT INTO Venda (valor_total, status_pagamento, forma_pagamento, fk_conta_turista, fk_conta_colaborador)
        VALUES (@preco, @status_pagamento, @forma_pagamento, @fk_conta_turista, @fk_conta_colaborador);

        SET @id_venda_out = CAST(SCOPE_IDENTITY() AS INT);

        INSERT INTO Obtem (fk_Pacote_id_pacote, fk_Venda_id_venda)
        VALUES (@fk_pacote, @id_venda_out);

        UPDATE Pacote
        SET estoque = estoque - 1
        WHERE id_pacote = @fk_pacote;

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;  -- repropaga o erro para o chamador
    END CATCH
END;
GO

-- tr_passagem_anti_overbooking: alem do UNIQUE no schema, entrega uma
-- mensagem de negocio clara quando o assento ja esta ocupado na viagem.
CREATE TRIGGER tr_passagem_anti_overbooking
ON Passagem
AFTER INSERT, UPDATE
AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS (
        SELECT 1
        FROM Passagem p
        JOIN inserted i
            ON i.fk_id_viagem = p.fk_id_viagem
           AND i.numero_assento = p.numero_assento
           AND i.id_passagem <> p.id_passagem
    )
    BEGIN
        ROLLBACK TRANSACTION;
        THROW 50010, 'Overbooking: assento ja ocupado nesta viagem.', 1;
    END
END;
GO

-- sp_atualizar_usuario: atualiza os campos editaveis do PROPRIO perfil
-- (self-service, RF "Alterar os dados de cadastro"). A atualizacao e PARCIAL e
-- ATOMICA: todas as seis colunas editaveis (nome, nome_social, pronome, cep,
-- email, telefone) sao parametros OPCIONAIS que default para NULL, onde NULL
-- significa "nao alterar". Cada coluna usa COALESCE(@param, coluna), entao um
-- unico UPDATE altera somente os campos efetivamente enviados, sem precisar de
-- uma leitura previa do perfil (elimina o read-modify-write em conexoes
-- separadas que abria janela de lost-update em atualizacoes concorrentes).
--
-- Semantica NULL = "nao alterar": o repositorio Python envia apenas campos
-- presentes E nao-None (model_dump(exclude_unset=True, exclude_none=True)),
-- passando NULL para as colunas nao enviadas. Como limpar um campo (set NULL)
-- nunca foi suportado por este caminho, COALESCE(@param, coluna) e exatamente
-- correto e nao muda o comportamento observavel.
--
-- A defesa em profundidade (RNF3: papel/status/cpf/data_nascimento NAO sao
-- editaveis) continua no Python (lista branca de colunas) e no schema
-- UsuarioAtualizar. A procedure devolve @@ROWCOUNT (linhas afetadas) como unico
-- resultado, lido via fetchone()[0] no Python (0 -> id inexistente -> None),
-- pois sob SET NOCOUNT ON o rowcount do driver pymssql nao e confiavel.
CREATE PROCEDURE sp_atualizar_usuario
    @id_passageiro INT,
    @nome          NVARCHAR(150) = NULL,
    @nome_social   NVARCHAR(150) = NULL,
    @pronome       NVARCHAR(30)  = NULL,
    @cep           NVARCHAR(9)   = NULL,
    @email         NVARCHAR(254) = NULL,
    @telefone      NVARCHAR(20)  = NULL
AS
BEGIN
    SET NOCOUNT ON;

    -- UPDATE unico e atomico: COALESCE preserva a coluna quando o parametro
    -- chega NULL ("nao alterar"), dispensando qualquer leitura previa.
    UPDATE dbo.Usuario
    SET nome        = COALESCE(@nome, nome),
        nome_social = COALESCE(@nome_social, nome_social),
        pronome     = COALESCE(@pronome, pronome),
        cep         = COALESCE(@cep, cep),
        email       = COALESCE(@email, email),
        telefone    = COALESCE(@telefone, telefone)
    WHERE id_passageiro = @id_passageiro;

    SELECT @@ROWCOUNT;  -- linhas afetadas, lidas via fetchone()[0] no Python
END;
GO

-- sp_excluir_usuario: SOFT DELETE / anonimizacao de uma conta (LGPD/RNF3).
-- Compartilhada pelo self-service (DELETE /auth/me) e pela exclusao
-- administrativa (DELETE /auth/admin/contas/{id}), que tem a MESMA semantica.
-- NAO e um hard delete: as FKs de dbo.Venda para Conta_turista usam
-- ON DELETE NO ACTION, entao apagar um Usuario com vendas violaria as FKs e
-- destruiria o historico financeiro. Em vez disso a conta vira 'Banido'
-- (estado terminal) e os campos pessoais sao anonimizados. Devolve @@ROWCOUNT
-- (linhas afetadas) como unico resultado.
CREATE PROCEDURE sp_excluir_usuario
    @id_passageiro INT
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.Usuario
    SET status      = N'Banido',
        nome        = N'Conta removida',
        nome_social = NULL,
        pronome     = NULL,
        email       = NULL,
        telefone    = NULL,
        cep         = NULL,
        cpf         = CONCAT('removido-', @id_passageiro)
    WHERE id_passageiro = @id_passageiro;

    SELECT @@ROWCOUNT;  -- linhas afetadas, lidas via fetchone()[0] no Python
END;
GO

-- sp_listar_usuarios: lista contas para moderacao (RF "Consultar todos os
-- usuarios cadastrados"). Projeta SOMENTE campos nao sensiveis (RNF3/LGPD):
-- id_passageiro, nome, email, papel, status. cpf, senha, data de nascimento,
-- cep e telefone NUNCA sao retornados aqui.
CREATE PROCEDURE sp_listar_usuarios
AS
BEGIN
    SET NOCOUNT ON;

    SELECT id_passageiro, nome, email, papel, status
    FROM dbo.Usuario
    ORDER BY id_passageiro;
END;
GO

-- tr_avaliacao_atualiza_ia_feedback: apos mudancas em Avaliacao,
-- recalcula score_agregado e total_avaliacoes em IA_Feedback (upsert).
CREATE TRIGGER tr_avaliacao_atualiza_ia_feedback
ON Avaliacao
AFTER INSERT, UPDATE, DELETE
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @pacotes TABLE (fk_pacote INT PRIMARY KEY);

    INSERT INTO @pacotes (fk_pacote)
    SELECT fk_pacote FROM inserted
    UNION
    SELECT fk_pacote FROM deleted;

    MERGE IA_Feedback AS alvo
    USING (
        SELECT
            pa.fk_pacote,
            AVG(CAST(a.nota AS DECIMAL(4,2))) AS score,
            COUNT(a.id_avaliacao)             AS total
        FROM @pacotes pa
        LEFT JOIN Avaliacao a ON a.fk_pacote = pa.fk_pacote
        GROUP BY pa.fk_pacote
    ) AS origem
        ON alvo.fk_pacote = origem.fk_pacote
    WHEN MATCHED THEN
        UPDATE SET
            score_agregado   = origem.score,
            total_avaliacoes = origem.total,
            data_atualizacao = SYSUTCDATETIME()
    WHEN NOT MATCHED BY TARGET THEN
        INSERT (fk_pacote, score_agregado, total_avaliacoes, data_atualizacao)
        VALUES (origem.fk_pacote, origem.score, origem.total, SYSUTCDATETIME());
END;
GO

-- sp_criar_pacote: cadastra um pacote (RF "Cadastrar um pacote"). Insere as
-- seis colunas de dbo.Pacote e devolve o id gerado. A convencao de retorno do
-- id espelha sp_registrar_venda (SCOPE_IDENTITY): a ultima instrucao e
-- SELECT CAST(SCOPE_IDENTITY() AS INT), lida no Python via fetchone()[0].
CREATE PROCEDURE sp_criar_pacote
    @preco_base  DECIMAL(10,2),
    @data_inicio DATE,
    @data_fim    DATE,
    @estoque     INT,
    @tipo_viagem NVARCHAR(50),
    @nivel       NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO dbo.Pacote
        (preco_base, data_inicio, data_fim, estoque, tipo_viagem, nivel)
    VALUES
        (@preco_base, @data_inicio, @data_fim, @estoque, @tipo_viagem, @nivel);

    SELECT CAST(SCOPE_IDENTITY() AS INT) AS id_pacote;  -- id gerado, lido via fetchone()[0]
END;
GO

-- sp_atualizar_pacote: altera um pacote existente (RF "Alterar um pacote").
-- Faz um UPDATE completo das seis colunas e devolve @@ROWCOUNT (linhas
-- afetadas) como unico resultado, pois sob SET NOCOUNT ON o rowcount do driver
-- pymssql nao e confiavel. O Python le @@ROWCOUNT via fetchone()[0]: 0 -> None.
CREATE PROCEDURE sp_atualizar_pacote
    @id_pacote   INT,
    @preco_base  DECIMAL(10,2),
    @data_inicio DATE,
    @data_fim    DATE,
    @estoque     INT,
    @tipo_viagem NVARCHAR(50),
    @nivel       NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.Pacote
    SET preco_base  = @preco_base,
        data_inicio = @data_inicio,
        data_fim    = @data_fim,
        estoque     = @estoque,
        tipo_viagem = @tipo_viagem,
        nivel       = @nivel
    WHERE id_pacote = @id_pacote;

    SELECT @@ROWCOUNT;  -- linhas afetadas, lidas via fetchone()[0] no Python
END;
GO

-- sp_excluir_pacote: remove um pacote (RF "Deletar um pacote"). Diferente de
-- usuarios, pacotes NAO tem requisito de soft delete, entao e um hard DELETE.
-- Devolve @@ROWCOUNT (linhas afetadas) como unico resultado; o Python o le via
-- fetchone()[0] e retorna bool (True se removeu alguma linha).
CREATE PROCEDURE sp_excluir_pacote
    @id_pacote INT
AS
BEGIN
    SET NOCOUNT ON;

    DELETE FROM dbo.Pacote
    WHERE id_pacote = @id_pacote;

    SELECT @@ROWCOUNT;  -- linhas afetadas, lidas via fetchone()[0] no Python
END;
GO

-- sp_listar_pacotes: lista todos os pacotes do catalogo (RF "Consultar todos
-- os pacotes"). Devolve TODAS as linhas com as mesmas colunas/ordem que o
-- Python espera; a filtragem (RF3) permanece em Python
-- (app/catalogo/service.filtrar_pacotes), NAO aqui.
CREATE PROCEDURE sp_listar_pacotes
AS
BEGIN
    SET NOCOUNT ON;

    SELECT id_pacote, preco_base, data_inicio, data_fim, estoque, tipo_viagem, nivel
    FROM dbo.Pacote;
END;
GO
