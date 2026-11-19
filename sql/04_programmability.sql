/* =====================================================================
   Wanderlust Viagens - Camada de banco de dados (SQL Server / T-SQL)
   Script 04 - Programabilidade (views, functions, procedures, triggers)
   ---------------------------------------------------------------------
   Objetos de logica no banco conforme a secao 5.3. Cada objeto e
   comentado com a sua finalidade. Os objetos sao recriados de forma
   idempotente (DROP IF EXISTS + CREATE) para facilitar re-execucao.
   Pre-requisito: executar 01_schema.sql e 02_aiv_tables.sql antes.
   ===================================================================== */

USE agencia_viagens;
GO

/* =====================================================================
   FUNCTION fn_calcular_idade
   ---------------------------------------------------------------------
   Calcula a idade (anos completos) a partir de uma data de nascimento.
   Usada em regras de elegibilidade e relatorios de perfil.
   ===================================================================== */
IF OBJECT_ID('dbo.fn_calcular_idade', 'FN') IS NOT NULL
    DROP FUNCTION dbo.fn_calcular_idade;
GO
CREATE FUNCTION dbo.fn_calcular_idade (@data_nascimento DATE)
RETURNS INT
AS
BEGIN
    DECLARE @idade INT;
    SET @idade = DATEDIFF(YEAR, @data_nascimento, GETDATE())
        -- ajusta se o aniversario ainda nao ocorreu no ano corrente:
        - CASE
            WHEN (MONTH(@data_nascimento) > MONTH(GETDATE()))
              OR (MONTH(@data_nascimento) = MONTH(GETDATE())
                  AND DAY(@data_nascimento) > DAY(GETDATE()))
            THEN 1 ELSE 0
          END;
    RETURN @idade;
END;
GO

/* =====================================================================
   VIEW vw_vendas_detalhadas
   ---------------------------------------------------------------------
   Consolida Venda + turista (Usuario) + pacotes adquiridos (via Obtem).
   Uma linha por par Venda x Pacote. Base para relatorios de vendas.
   ===================================================================== */
IF OBJECT_ID('dbo.vw_vendas_detalhadas', 'V') IS NOT NULL
    DROP VIEW dbo.vw_vendas_detalhadas;
GO
CREATE VIEW dbo.vw_vendas_detalhadas
AS
SELECT
    v.id_venda,
    v.data_venda,
    v.valor_total,
    v.status_pagamento,
    v.forma_pagamento,
    ct.id_turista,
    u.nome              AS nome_turista,
    u.nome_social       AS nome_social_turista,
    u.email             AS email_turista,
    p.id_pacote,
    p.tipo_viagem,
    p.nivel,
    p.preco_base
FROM dbo.Venda AS v
INNER JOIN dbo.Conta_turista AS ct ON ct.id_turista = v.fk_conta_turista
INNER JOIN dbo.Usuario       AS u  ON u.id_passageiro = ct.id_turista
INNER JOIN dbo.Obtem         AS o  ON o.fk_Venda_id_venda = v.id_venda
INNER JOIN dbo.Pacote        AS p  ON p.id_pacote = o.fk_Pacote_id_pacote;
GO

/* =====================================================================
   VIEW vw_turistas_por_destino_ano  (suporte a RF10)
   ---------------------------------------------------------------------
   Estatistica de incidencia de turistas por destino ao longo do ano:
   conta turistas distintos e total de vendas por (destino, ano),
   derivando o ano a partir de data_venda e o destino via
   Pacote -> Hospedagem? Nao: o vinculo destino-venda se da pela Viagem
   associada as Passagens da venda. Aqui ligamos Venda -> Passagem ->
   Viagem -> Destino.
   ===================================================================== */
IF OBJECT_ID('dbo.vw_turistas_por_destino_ano', 'V') IS NOT NULL
    DROP VIEW dbo.vw_turistas_por_destino_ano;
GO
CREATE VIEW dbo.vw_turistas_por_destino_ano
AS
SELECT
    d.id_destino,
    d.cidade,
    d.estado,
    d.pais,
    YEAR(v.data_venda)                   AS ano,
    COUNT(DISTINCT v.fk_conta_turista)   AS qtd_turistas,
    COUNT(DISTINCT v.id_venda)           AS qtd_vendas
FROM dbo.Venda    AS v
INNER JOIN dbo.Passagem AS pg ON pg.fk_id_venda = v.id_venda
INNER JOIN dbo.Viagem   AS vi ON vi.id_viagem = pg.fk_id_viagem
INNER JOIN dbo.Destino  AS d  ON d.id_destino = vi.fk_Destino_id_destino
GROUP BY d.id_destino, d.cidade, d.estado, d.pais, YEAR(v.data_venda);
GO

/* =====================================================================
   PROCEDURE sp_registrar_venda  (secao 5.3)
   ---------------------------------------------------------------------
   Registra uma venda de um pacote de forma atomica:
     1) valida estoque do pacote;
     2) insere a Venda;
     3) insere o vinculo em Obtem;
     4) baixa 1 unidade do estoque do Pacote.
   Tudo dentro de uma transacao com tratamento de erro (TRY/CATCH).
   Retorna o id_venda gerado via parametro de saida.
   ===================================================================== */
IF OBJECT_ID('dbo.sp_registrar_venda', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_registrar_venda;
GO
CREATE PROCEDURE dbo.sp_registrar_venda
    @fk_conta_turista     INT,
    @fk_pacote            INT,
    @forma_pagamento      NVARCHAR(50),
    @fk_conta_colaborador INT          = NULL,
    @status_pagamento     NVARCHAR(30) = N'Pendente',
    @id_venda_out         INT          OUTPUT
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
        FROM dbo.Pacote WITH (UPDLOCK, ROWLOCK)
        WHERE id_pacote = @fk_pacote;

        IF @preco IS NULL
        BEGIN
            THROW 50001, 'Pacote inexistente.', 1;
        END

        IF @estoque <= 0
        BEGIN
            THROW 50002, 'Estoque esgotado para o pacote informado.', 1;
        END

        INSERT INTO dbo.Venda
            (valor_total, status_pagamento, forma_pagamento, fk_conta_turista, fk_conta_colaborador)
        VALUES
            (@preco, @status_pagamento, @forma_pagamento, @fk_conta_turista, @fk_conta_colaborador);

        SET @id_venda_out = CAST(SCOPE_IDENTITY() AS INT);

        INSERT INTO dbo.Obtem (fk_Pacote_id_pacote, fk_Venda_id_venda)
        VALUES (@fk_pacote, @id_venda_out);

        UPDATE dbo.Pacote
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

/* =====================================================================
   TRIGGER tr_passagem_anti_overbooking
   ---------------------------------------------------------------------
   Reforca a regra de overbooking em nivel de INSERT/UPDATE:
   impede que o mesmo assento seja atribuido duas vezes na mesma viagem.
   A constraint UQ_Passagem_assento_viagem ja protege no schema; esta
   trigger entrega uma mensagem de negocio clara (RNF de usabilidade).
   ===================================================================== */
IF OBJECT_ID('dbo.tr_passagem_anti_overbooking', 'TR') IS NOT NULL
    DROP TRIGGER dbo.tr_passagem_anti_overbooking;
GO
CREATE TRIGGER dbo.tr_passagem_anti_overbooking
ON dbo.Passagem
AFTER INSERT, UPDATE
AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS (
        SELECT 1
        FROM dbo.Passagem AS p
        INNER JOIN inserted AS i
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

/* =====================================================================
   TRIGGER tr_avaliacao_atualiza_ia_feedback
   ---------------------------------------------------------------------
   Apos INSERT/UPDATE/DELETE em Avaliacao, recalcula o score agregado e
   o total de avaliacoes do pacote em IA_Feedback (upsert por pacote).
   Mantem o insumo do AIV sempre consistente (RF8).
   ===================================================================== */
IF OBJECT_ID('dbo.tr_avaliacao_atualiza_ia_feedback', 'TR') IS NOT NULL
    DROP TRIGGER dbo.tr_avaliacao_atualiza_ia_feedback;
GO
CREATE TRIGGER dbo.tr_avaliacao_atualiza_ia_feedback
ON dbo.Avaliacao
AFTER INSERT, UPDATE, DELETE
AS
BEGIN
    SET NOCOUNT ON;

    -- Conjunto de pacotes afetados (linhas inseridas e/ou removidas):
    DECLARE @pacotes TABLE (fk_pacote INT PRIMARY KEY);

    INSERT INTO @pacotes (fk_pacote)
    SELECT fk_pacote FROM inserted
    UNION
    SELECT fk_pacote FROM deleted;

    -- Upsert em IA_Feedback para cada pacote afetado:
    MERGE dbo.IA_Feedback AS alvo
    USING (
        SELECT
            pa.fk_pacote,
            AVG(CAST(a.nota AS DECIMAL(4,2))) AS score,
            COUNT(a.id_avaliacao)             AS total
        FROM @pacotes AS pa
        LEFT JOIN dbo.Avaliacao AS a ON a.fk_pacote = pa.fk_pacote
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
