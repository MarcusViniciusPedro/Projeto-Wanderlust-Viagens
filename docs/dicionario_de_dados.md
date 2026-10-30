# Dicionário de dados — Wanderlust Viagens

Banco de dados: **`agencia_viagens`** (SQL Server / T-SQL).

Este documento descreve todas as tabelas e colunas do modelo, incluindo as
tabelas de apoio ao AIV. Convenções:

- **Tipo**: tipo T-SQL da coluna.
- **Nulo**: se a coluna aceita `NULL`.
- **Chave**: PK (chave primária), FK (chave estrangeira), UQ (única).
- Colunas marcadas como **extensão** não constam do DDL original do
  documento; foram adicionadas de forma coerente para atender aos
  requisitos (RF/RNF indicados).

---

## Tabela `Destino`

Destinos turísticos oferecidos.

| Coluna      | Tipo           | Nulo | Chave | Descrição                                   |
|-------------|----------------|------|-------|---------------------------------------------|
| id_destino  | INT IDENTITY   | Não  | PK    | Identificador do destino (auto-incremento). |
| cidade      | NVARCHAR(100)  | Não  |       | Cidade do destino.                          |
| estado      | NVARCHAR(50)   | Não  |       | Estado/província.                           |
| pais        | NVARCHAR(50)   | Não  |       | País.                                       |
| categoria   | NVARCHAR(50)   | Sim  |       | Categoria (ex.: Praia, Serra, Cultural).    |
| descricao   | NVARCHAR(MAX)  | Sim  |       | Descrição livre (era `TEXT` no MySQL).      |

---

## Tabela `Usuario`

Pessoa cadastrada (base para turista e colaborador).

| Coluna          | Tipo          | Nulo | Chave | Descrição                                               |
|-----------------|---------------|------|-------|---------------------------------------------------------|
| id_passageiro   | INT IDENTITY  | Não  | PK    | Identificador do usuário (auto-incremento).             |
| nome            | NVARCHAR(150) | Não  |       | Nome civil.                                             |
| nome_social     | NVARCHAR(150) | Sim  |       | **Extensão (RNF1)**: nome social (design inclusivo).    |
| pronome         | NVARCHAR(30)  | Sim  |       | **Extensão (RNF1)**: pronome de tratamento.             |
| data_nascimento | DATE          | Não  |       | Data de nascimento.                                     |
| cpf             | NVARCHAR(14)  | Não  | UQ    | CPF (único).                                            |
| cep             | NVARCHAR(9)   | Sim  |       | CEP de residência.                                      |
| email           | NVARCHAR(254) | Sim  | UQ    | **Extensão (RF1/RF2)**: e-mail de login/contato (único).|
| telefone        | NVARCHAR(20)  | Sim  |       | **Extensão (RNF3)**: telefone para SMS 2FA.             |
| papel           | NVARCHAR(20)  | Não  |       | **Extensão**: papel (`Turista`/`Agente`/`Administrador`). |

---

## Tabela `Credencial` (extensão, 1:1 com `Usuario`)

Dados sensíveis de autenticação, isolados do perfil (boa prática LGPD/RNF3).

| Coluna        | Tipo          | Nulo | Chave   | Descrição                                            |
|---------------|---------------|------|---------|------------------------------------------------------|
| id_usuario    | INT           | Não  | PK, FK  | FK para `Usuario(id_passageiro)` (ON DELETE CASCADE).|
| senha_hash    | NVARCHAR(255) | Não  |         | Hash da senha (ex.: bcrypt/argon2). Nunca texto puro.|
| totp_secret   | NVARCHAR(64)  | Sim  |         | Segredo TOTP para 2FA.                               |
| two_factor    | BIT           | Não  |         | Indica se 2FA está habilitado (padrão 0).            |
| atualizado_em | DATETIME2     | Não  |         | Última atualização das credenciais.                  |

---

## Tabela `Pacote`

Pacotes de viagem comercializados.

| Coluna      | Tipo          | Nulo | Chave | Descrição                                               |
|-------------|---------------|------|-------|---------------------------------------------------------|
| id_pacote   | INT IDENTITY  | Não  | PK    | Identificador do pacote (auto-incremento).              |
| preco_base  | DECIMAL(10,2) | Não  |       | Preço base do pacote.                                   |
| data_inicio | DATE          | Não  |       | Início da vigência/período do pacote.                   |
| data_fim    | DATE          | Não  |       | Fim da vigência/período do pacote.                      |
| estoque     | INT           | Não  |       | Quantidade disponível (>= 0).                           |
| tipo_viagem | NVARCHAR(50)  | Sim  |       | **Extensão (RF3/RF7)**: tipo (Praia, Aventura, etc.).   |
| nivel       | NVARCHAR(50)  | Sim  |       | **Extensão (RF3/RF7)**: nível (Econômico, Luxo, etc.).  |

---

## Tabela `Conta_colaborador` (especialização de `Usuario`)

| Coluna         | Tipo         | Nulo | Chave   | Descrição                                                   |
|----------------|--------------|------|---------|-------------------------------------------------------------|
| id_colaborador | INT          | Não  | PK, FK  | FK para `Usuario(id_passageiro)` (ON DELETE CASCADE).       |
| cargo          | NVARCHAR(50) | Não  |         | Cargo do colaborador.                                       |
| comissao       | DECIMAL(5,2) | Sim  |         | Percentual de comissão.                                     |

---

## Tabela `Conta_turista` (especialização de `Usuario`)

| Coluna     | Tipo | Nulo | Chave  | Descrição                                               |
|------------|------|------|--------|---------------------------------------------------------|
| id_turista | INT  | Não  | PK, FK | FK para `Usuario(id_passageiro)` (ON DELETE CASCADE).   |

---

## Tabela `Viagem`

Trechos de viagem associados a um destino.

| Coluna                | Tipo         | Nulo | Chave | Descrição                                           |
|-----------------------|--------------|------|-------|-----------------------------------------------------|
| id_viagem             | INT IDENTITY | Não  | PK    | Identificador da viagem (auto-incremento).          |
| data_partida          | DATETIME2    | Não  |       | Data/hora de partida (era `DATETIME` no MySQL).     |
| data_chegada          | DATETIME2    | Não  |       | Data/hora de chegada (era `DATETIME` no MySQL).     |
| meio_transporte       | NVARCHAR(50) | Não  |       | Meio de transporte (Avião, Ônibus, etc.).           |
| duracao               | NVARCHAR(30) | Sim  |       | Duração textual (ex.: "6h").                        |
| fk_Destino_id_destino | INT          | Não  | FK    | FK para `Destino(id_destino)` (NO ACTION).          |

---

## Tabela `Hospedagem`

Hospedagem vinculada a um pacote.

| Coluna              | Tipo          | Nulo | Chave | Descrição                                      |
|---------------------|---------------|------|-------|------------------------------------------------|
| id_hospedagem       | INT IDENTITY  | Não  | PK    | Identificador da hospedagem (auto-incremento). |
| cep                 | NVARCHAR(9)   | Não  |       | CEP da hospedagem.                             |
| rua                 | NVARCHAR(150) | Não  |       | Logradouro.                                    |
| numero              | INT           | Não  |       | Número do endereço.                            |
| nome                | NVARCHAR(100) | Não  |       | Nome do estabelecimento.                       |
| tipo_quarto         | NVARCHAR(50)  | Sim  |       | Tipo de quarto.                                |
| regime_alimentacao  | NVARCHAR(50)  | Sim  |       | Regime de alimentação (ex.: Meia pensão).      |
| fk_Pacote_id_pacote | INT           | Não  | FK    | FK para `Pacote(id_pacote)` (ON DELETE CASCADE).|

---

## Tabela `Venda`

Registro de uma venda realizada.

| Coluna               | Tipo          | Nulo | Chave | Descrição                                                        |
|----------------------|---------------|------|-------|------------------------------------------------------------------|
| id_venda             | INT IDENTITY  | Não  | PK    | Identificador da venda (auto-incremento).                        |
| valor_total          | DECIMAL(10,2) | Não  |       | Valor total da venda.                                            |
| status_pagamento     | NVARCHAR(30)  | Não  |       | Estado (`Pendente`/`Pago`/`Cancelado`/`Estornado`).              |
| forma_pagamento      | NVARCHAR(50)  | Não  |       | Forma de pagamento.                                              |
| data_venda           | DATETIME2     | Não  |       | **Nota (seção 5.3)**: data/hora da venda (padrão: agora UTC).    |
| fk_conta_turista     | INT           | Não  | FK    | FK para `Conta_turista(id_turista)` — **NO ACTION** (ver nota).  |
| fk_conta_colaborador | INT           | Sim  | FK    | FK para `Conta_colaborador(id_colaborador)` — **NO ACTION**.     |

> **Nota de cascade**: as duas FKs usam `ON DELETE NO ACTION` para evitar
> múltiplos caminhos de cascade até `Usuario` (erro 1785 do SQL Server).

---

## Tabela `Passagem`

Passagem emitida para uma viagem dentro de uma venda.

| Coluna         | Tipo         | Nulo | Chave | Descrição                                          |
|----------------|--------------|------|-------|----------------------------------------------------|
| id_passagem    | INT IDENTITY | Não  | PK    | Identificador da passagem (auto-incremento).       |
| numero_assento | NVARCHAR(10) | Não  |       | Assento (único por viagem — anti-overbooking).     |
| classe         | NVARCHAR(30) | Não  |       | Classe (Econômica, Executiva, etc.).               |
| fk_id_viagem   | INT          | Não  | FK    | FK para `Viagem(id_viagem)` (NO ACTION).           |
| fk_id_venda    | INT          | Não  | FK    | FK para `Venda(id_venda)` (NO ACTION).             |

> Restrição `UQ_Passagem_assento_viagem` (fk_id_viagem, numero_assento)
> impede overbooking.

---

## Tabela `Obtem` (associativa `Pacote` × `Venda`)

| Coluna              | Tipo | Nulo | Chave  | Descrição                                        |
|---------------------|------|------|--------|--------------------------------------------------|
| fk_Pacote_id_pacote | INT  | Não  | PK, FK | FK para `Pacote(id_pacote)` (NO ACTION).         |
| fk_Venda_id_venda   | INT  | Não  | PK, FK | FK para `Venda(id_venda)` (NO ACTION).           |

Chave primária composta (`fk_Pacote_id_pacote`, `fk_Venda_id_venda`).

---

# Tabelas de apoio ao AIV

## Tabela `Preferencia` (extensão)

Perfil de preferências do turista (consolidado do questionário inicial).

| Coluna            | Tipo          | Nulo | Chave   | Descrição                                               |
|-------------------|---------------|------|---------|---------------------------------------------------------|
| id_preferencia    | INT IDENTITY  | Não  | PK      | Identificador (auto-incremento).                        |
| fk_turista        | INT           | Não  | FK, UQ  | FK para `Conta_turista(id_turista)` (CASCADE). Única.   |
| tipo_viagem       | NVARCHAR(50)  | Sim  |         | Tipo preferido (casa com `Pacote.tipo_viagem`).         |
| nivel             | NVARCHAR(50)  | Sim  |         | Nível preferido (casa com `Pacote.nivel`).              |
| orcamento_max     | DECIMAL(10,2) | Sim  |         | Teto de orçamento desejado.                             |
| estacao_preferida | NVARCHAR(30)  | Sim  |         | Estação preferida (ex.: Verão).                         |
| observacoes       | NVARCHAR(MAX) | Sim  |         | Observações livres.                                     |
| atualizado_em     | DATETIME2     | Não  |         | Última atualização.                                     |

---

## Tabela `Questionario_Resposta` (extensão)

Respostas brutas do questionário inicial (rastreabilidade do AIV).

| Coluna        | Tipo          | Nulo | Chave | Descrição                                            |
|---------------|---------------|------|-------|------------------------------------------------------|
| id_resposta   | INT IDENTITY  | Não  | PK    | Identificador (auto-incremento).                     |
| fk_turista    | INT           | Não  | FK    | FK para `Conta_turista(id_turista)` (CASCADE).       |
| pergunta      | NVARCHAR(200) | Não  |       | Texto da pergunta.                                   |
| resposta      | NVARCHAR(MAX) | Não  |       | Resposta fornecida.                                  |
| respondido_em | DATETIME2     | Não  |       | Data/hora da resposta.                               |

---

## Tabela `Avaliacao` (extensão)

Avaliações de pacotes pelos turistas (RF8).

| Coluna       | Tipo          | Nulo | Chave  | Descrição                                           |
|--------------|---------------|------|--------|-----------------------------------------------------|
| id_avaliacao | INT IDENTITY  | Não  | PK     | Identificador (auto-incremento).                    |
| fk_turista   | INT           | Não  | FK     | FK para `Conta_turista(id_turista)` (NO ACTION).    |
| fk_pacote    | INT           | Não  | FK     | FK para `Pacote(id_pacote)` (NO ACTION).            |
| nota         | INT           | Não  |        | Nota de 1 a 5.                                      |
| comentario   | NVARCHAR(MAX) | Sim  |        | Comentário livre.                                   |
| data         | DATETIME2     | Não  |        | Data/hora da avaliação.                             |

> Restrição `UQ_Avaliacao_turista_pacote` garante uma avaliação por
> par (turista, pacote).

---

## Tabela `IA_Feedback` (extensão)

Feedback agregado pelo AIV por pacote (RF8). Atualizada por trigger.

| Coluna           | Tipo          | Nulo | Chave  | Descrição                                            |
|------------------|---------------|------|--------|------------------------------------------------------|
| id_feedback      | INT IDENTITY  | Não  | PK     | Identificador (auto-incremento).                     |
| fk_pacote        | INT           | Não  | FK, UQ | FK para `Pacote(id_pacote)` (CASCADE). Único.        |
| score_agregado   | DECIMAL(4,2)  | Sim  |        | Score agregado (0.00 a 5.00).                        |
| total_avaliacoes | INT           | Não  |        | Total de avaliações consideradas (padrão 0).         |
| resumo           | NVARCHAR(MAX) | Sim  |        | Síntese textual gerada pelo AIV.                     |
| data_atualizacao | DATETIME2     | Não  |        | Última atualização do feedback.                      |

---

# Objetos de programabilidade

| Objeto                                 | Tipo       | Descrição                                                                 |
|----------------------------------------|------------|---------------------------------------------------------------------------|
| `fn_calcular_idade`                    | Function   | Calcula a idade em anos a partir da data de nascimento.                   |
| `vw_vendas_detalhadas`                 | View       | Consolida Venda + turista + pacotes (via Obtem).                          |
| `vw_turistas_por_destino_ano`          | View       | Incidência de turistas por destino e ano (suporte a RF10).               |
| `sp_registrar_venda`                   | Procedure  | Registra Venda + Obtem e baixa estoque em transação atômica.             |
| `tr_passagem_anti_overbooking`         | Trigger    | Impede assento duplicado na mesma viagem (anti-overbooking).             |
| `tr_avaliacao_atualiza_ia_feedback`    | Trigger    | Recalcula `IA_Feedback.score_agregado` após mudanças em `Avaliacao`.     |
