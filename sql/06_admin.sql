-- 06_admin.sql — Administrador pré-definido para desenvolvimento/testes.
--
-- Cria (se ainda não existir) um usuário Administrador com 2FA desligado,
-- pronto para logar pela interface sem código SMS.
--
--   E-mail: admin@wanderlust.com
--   Senha:  Admin123   (hash bcrypt abaixo; gerado por app.core.security.hash_senha)
--
-- Idempotente: pode rodar várias vezes; só insere se o e-mail não existir.
-- NÃO use estas credenciais em produção — são apenas para o trabalho acadêmico.

USE agencia_viagens;
GO

IF NOT EXISTS (SELECT 1 FROM dbo.Usuario WHERE email = N'admin@wanderlust.com')
BEGIN
    INSERT INTO dbo.Usuario (nome, data_nascimento, cpf, email, papel)
    VALUES (N'Administrador', '1990-01-01', N'000.000.000-00',
            N'admin@wanderlust.com', N'Administrador');

    DECLARE @id INT = SCOPE_IDENTITY();

    INSERT INTO dbo.Credencial (id_usuario, senha_hash, totp_secret, two_factor)
    VALUES (@id,
            N'$2b$12$ojQ4SpM1Oo6A6bHmfXxeLuKAzVfoTHHgN4id/nOo0D2UOTf/ywLfu',
            NULL, 0);

    PRINT 'Admin criado: admin@wanderlust.com / Admin123';
END
ELSE
BEGIN
    PRINT 'Admin ja existe: admin@wanderlust.com (nada a fazer).';
END
GO
