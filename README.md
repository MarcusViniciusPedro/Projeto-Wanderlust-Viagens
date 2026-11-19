# Projeto Wanderlust Viagens

Back-end da agencia de viagens **Wanderlust Viagens**. O sistema e construido
com **Python 3.11 (FastAPI)** para a API e **Microsoft SQL Server (T-SQL)**
para o banco de dados, preparado para integracao posterior com o front-end
(HTML/CSS/JS, fora do escopo deste MVP de back-end).

## Visao geral

A Wanderlust Viagens e uma agencia que vende pacotes de viagem a tres perfis de
usuario (Turista, Agente de Viagens e Administrador). O back-end entrega:

- Cadastro e autenticacao de usuarios com **2FA (TOTP + SMS)** e autorizacao por
  papel (matriz de permissoes da secao 4.1 do documento de requisitos).
- Catalogo de pacotes com busca por filtros e visualizacao de destinos via
  Street View.
- Carrinho/venda com uma **maquina de estados de pagamento** (Pendente -> Pago /
  Cancelado / Estornado) e integracao com um gateway de pagamento.
- Estatisticas de incidencia de turistas por destino (relatorio anual).
- **AIV - Assistente Inteligente de Viagens**: uma IA *heuristica e
  deterministica* (sem modelo de ML externo) que estima orcamentos, recomenda
  pacotes por aderencia as preferencias do turista e agrega avaliacoes em um
  feedback consolidado.

### O que e o AIV

O AIV nao usa nenhum modelo de machine learning externo nem rede. Ele e uma
heuristica **transparente, deterministica e testavel** implementada em
`app/recomendacao/service.py`. As mesmas entradas sempre produzem a mesma
saida, e todos os pesos ficam explicitos em constantes. Detalhes na secao
[Decisao do AIV](#decisao-do-aiv-ia-deterministica).

## Arquitetura

O sistema e um **monolito modular** que espelha os microsservicos planejados na
secao 2.1 do documento, de modo que cada modulo possa, no futuro, ser extraido
para um servico independente sem reescrever a logica de dominio.

Escolhas tecnologicas:

- **Python 3.11 + FastAPI**: framework async, API-first, com documentacao
  OpenAPI/Swagger automatica (`/docs`) e validacao de dados via Pydantic. A
  logica de dominio fica em funcoes puras (sem HTTP nem banco), o que torna o
  nucleo facil de testar isoladamente.
- **SQL Server (T-SQL)** como banco de dados, conforme requisito do projeto. O
  driver escolhido e o **pymssql**, que instala via *wheel* sem exigir um driver
  ODBC do sistema, simplificando o ambiente. A conexao e **preguicosa e
  opcional**: a aplicacao sobe e os testes rodam sem um banco vivo; a conexao so
  e aberta quando um recurso que precisa dela e efetivamente usado.

### Estrutura de diretorios

```text
.
├── app/                      # API FastAPI (monolito modular por microsservico)
│   ├── main.py               # ponto de entrada; registra routers e /health
│   ├── core/
│   │   ├── config.py         # Settings (prefixo WANDERLUST_, le .env)
│   │   ├── security.py       # hash bcrypt, JWT (python-jose), TOTP (pyotp)
│   │   └── authz.py          # papeis e matriz de permissoes (secao 4.1)
│   ├── db/
│   │   └── session.py        # fabrica de conexao pymssql preguicosa/opcional
│   ├── usuarios/             # perfis e autenticacao 2FA (RF1/RF2)
│   ├── catalogo/             # busca de pacotes (RF3) + Street View (RF9)
│   ├── vendas/               # carrinho/venda e maquina de pagamento (RF5)
│   ├── recomendacao/         # AIV: orcamento (RF4) e recomendacao (RF7)
│   ├── estatisticas/         # turistas por destino (RF10)
│   └── integracoes/          # stubs: sms.py, email.py, pagamento.py, streetview.py
├── sql/                      # camada de banco (SQL Server / T-SQL)
│   ├── 01_schema.sql         # banco + tabelas do documento + Credencial
│   ├── 02_aiv_tables.sql     # tabelas de apoio ao AIV
│   ├── 03_indexes.sql        # indices estrategicos
│   ├── 04_programmability.sql# views, functions, procedures e triggers
│   ├── 05_seed_dml.sql       # dados de exemplo + consultas CRUD
│   └── README.md             # guia de execucao dos scripts
├── docs/
│   └── dicionario_de_dados.md# dicionario de dados completo
├── tests/                    # testes pytest (sem DB vivo por padrao)
├── pyproject.toml            # metadados, dependencias e config do pytest
└── .env.example              # modelo de variaveis de ambiente
```

Cada modulo de `app/` que acessa o banco segue o padrao
`router.py` (rotas HTTP) + `service.py` (logica de dominio pura) +
`repository.py` (acesso a dados) + `schemas.py` (modelos Pydantic).

## Banco de dados (SQL Server / T-SQL)

O banco se chama **`agencia_viagens`** e e descrito por scripts T-SQL numerados
em `sql/`. **Nao ha instancia de SQL Server neste ambiente**: os scripts foram
validados por inspecao de sintaxe e devem ser executados pelo usuario no seu
proprio SQL Server (2017+ recomendado; cliente `sqlcmd`, Azure Data Studio ou
SSMS).

Execute os scripts na ordem numerica (cada um depende do anterior):

| Ordem | Arquivo                  | Conteudo                                                      |
|-------|--------------------------|---------------------------------------------------------------|
| 1     | `sql/01_schema.sql`      | Criacao do banco e das tabelas do documento + `Credencial`.   |
| 2     | `sql/02_aiv_tables.sql`  | Tabelas de apoio ao AIV (Preferencia, Questionario_Resposta, Avaliacao, IA_Feedback). |
| 3     | `sql/03_indexes.sql`     | Indices estrategicos para busca/recomendacao.                 |
| 4     | `sql/04_programmability.sql` | Views, functions, stored procedures e triggers.           |
| 5     | `sql/05_seed_dml.sql`    | Dados de exemplo + consultas CRUD representativas.            |

Exemplo com `sqlcmd`:

```bash
sqlcmd -S localhost -U sa -P 'SuaSenha' -i sql/01_schema.sql
sqlcmd -S localhost -U sa -P 'SuaSenha' -i sql/02_aiv_tables.sql
sqlcmd -S localhost -U sa -P 'SuaSenha' -i sql/03_indexes.sql
sqlcmd -S localhost -U sa -P 'SuaSenha' -i sql/04_programmability.sql
sqlcmd -S localhost -U sa -P 'SuaSenha' -i sql/05_seed_dml.sql
```

A descricao completa de todas as tabelas e colunas esta no
[dicionario de dados](docs/dicionario_de_dados.md). Notas de execucao
adicionais (traducao MySQL -> T-SQL, regra de multiplos caminhos de cascade)
estao em [`sql/README.md`](sql/README.md).

## Configurar e rodar o back-end

Requisitos: Python 3.11+. O SQL Server e **opcional** nesta fase (a API sobe e
os testes rodam sem banco).

```bash
# 1) criar e usar um virtualenv do projeto
python3 -m venv .venv
.venv/bin/pip install --upgrade pip

# 2) instalar o projeto com as dependencias de desenvolvimento/testes
.venv/bin/pip install -e '.[dev]'

# 3) validar que a app importa sem conectar ao banco
.venv/bin/python -c "import app.main; print('import ok')"

# 4) subir a API
.venv/bin/uvicorn app.main:app --reload
```

- Documentacao interativa (Swagger): `http://localhost:8000/docs`
- Health check (nao depende do banco): `http://localhost:8000/health`

### Variaveis de ambiente

A configuracao e lida por `app/core/config.py` (classe `Settings`), que usa o
prefixo **`WANDERLUST_`** e carrega um arquivo **`.env`** (modelo em
`.env.example`). Nenhum segredo e commitado; `.env` e `.venv/` estao no
`.gitignore`. A conexao de banco so e aberta quando um recurso que precisa dela
e usado; sem as variaveis `WANDERLUST_DB_*` a app continua subindo e os
endpoints que exigem banco respondem **HTTP 503** com mensagem clara.

| Variavel de ambiente           | Campo em `Settings`     | Padrao / observacao                                      |
|--------------------------------|-------------------------|-----------------------------------------------------------|
| `WANDERLUST_DB_SERVER`         | `db_server`             | `None` (banco opcional)                                   |
| `WANDERLUST_DB_PORT`           | `db_port`               | `1433`                                                    |
| `WANDERLUST_DB_NAME`           | `db_name`               | `None`                                                    |
| `WANDERLUST_DB_USER`           | `db_user`               | `None`                                                    |
| `WANDERLUST_DB_PASSWORD`       | `db_password`           | `None`                                                    |
| `WANDERLUST_JWT_SECRET`        | `jwt_secret`            | `None`; obrigatorio para emitir/validar JWT               |
| `WANDERLUST_JWT_ALGORITHM`     | `jwt_algorithm`         | `HS256`                                                   |
| `WANDERLUST_JWT_EXPIRE_MINUTES`| `jwt_expire_minutes`    | `60`                                                      |
| `WANDERLUST_TOTP_ISSUER`       | `totp_issuer`           | `Wanderlust Viagens` (emissor exibido no app 2FA)         |
| `WANDERLUST_SMS_API_KEY`       | `sms_api_key`           | vazio = stub/desativado                                   |
| `WANDERLUST_SMS_SENDER`        | `sms_sender`            | vazio = stub/desativado                                   |
| `WANDERLUST_EMAIL_API_KEY`     | `email_api_key`         | vazio = stub/desativado                                   |
| `WANDERLUST_EMAIL_FROM`        | `email_from`            | remetente de e-mails                                      |
| `WANDERLUST_PAYMENT_API_KEY`   | `payment_api_key`       | vazio = stub/desativado                                   |
| `WANDERLUST_PAYMENT_BASE_URL`  | `payment_base_url`      | vazio = stub/desativado                                   |
| `WANDERLUST_STREETVIEW_API_KEY`| `streetview_api_key`    | vazio = URL montada sem chave                             |

Alem destas, `Settings` define `app_name`, `app_version` e
`streetview_base_url` (URL base do embed de Street View, com padrao
configuravel para nao depender de um provedor real). O campo `db_configured`
indica se ha dados suficientes (`server`, `name`, `user`, `password`) para
conectar.

## Testes

```bash
.venv/bin/pytest -q
```

A suite tem **64 testes** cobrindo a logica de negocio (orcamento,
recomendacao, agregacao de feedback, autenticacao/2FA, autorizacao por papel,
maquina de estados de pagamento, busca, e-mail, estatisticas, configuracao).
Os testes unitarios **nao exigem um SQL Server vivo**.

Os testes de integracao que precisam de um banco real sao marcados com
`@pytest.mark.integration` e ficam **pulados por padrao** (via
`addopts = "-m 'not integration'"` no `pyproject.toml`). Para roda-los com um
banco disponivel:

```bash
.venv/bin/pytest -m integration
```

## Decisao do AIV (IA deterministica)

O AIV e uma heuristica deterministica em `app/recomendacao/service.py`, sem
nenhum modelo de ML externo. Isso garante transparencia, reprodutibilidade e
testabilidade.

**RF4 - Estimativa de orcamento (`estimar_orcamento`).** Parte do `preco_base`
e aplica fatores multiplicativos deterministicos, todos neutros (1.0) quando o
insumo nao e informado:

- Duracao: `+3%` por dia extra alem do primeiro (`FATOR_POR_DIA_EXTRA = 0.03`).
- Regime de alimentacao (`FATORES_REGIME`): `sem_refeicao` 1.00, `cafe_da_manha`
  1.08, `meia_pensao` 1.18, `pensao_completa` 1.28, `all_inclusive` 1.40.
- Nivel de conforto (`FATORES_NIVEL`): `economico` 1.00, `conforto` 1.25,
  `luxo` 1.60.
- Alta temporada: `x1.15` (`FATOR_ALTA_TEMPORADA`).
- Multiplicacao final pelo numero de pessoas.

**RF7 - Recomendacao (`recomendar` / `pontuar_pacote`).** Soma ponderada de
quatro componentes cujos pesos somam 1.0:

- `PESO_TIPO = 0.35` (aderencia do tipo de viagem a preferencia).
- `PESO_NIVEL = 0.20` (aderencia do nivel a preferencia).
- `PESO_ORCAMENTO = 0.25` (pacote dentro do orcamento maximo do turista).
- `PESO_AVALIACOES = 0.20` (reputacao normalizada 0..5 -> 0..1, ponderada pela
  confianca da amostra, que satura em `AVALIACOES_PARA_CONFIANCA_PLENA = 10`).

Pacotes fora do orcamento nao sao descartados, apenas penalizados. O ranking e
estavel: empates sao desempatados pelo `id_pacote` crescente.

**RF8 - Feedback agregado (`agregar_feedback`).** Agrega as `Avaliacao` de um
pacote em um score medio (0..5) e um resumo textual deterministico (faixas
fixas em `FAIXAS_RESUMO`), alimentando a tabela `IA_Feedback`. Exposto por HTTP
em `POST /recomendacao/feedback` (paridade de API com os demais RFs), alem de
materializado no banco pela trigger `tr_avaliacao_atualiza_ia_feedback`.

**Ciclo de feedback.** As preferencias do turista (`Preferencia`,
`Questionario_Resposta`) alimentam a recomendacao; as `Avaliacao` pos-viagem
sao agregadas em `IA_Feedback` (no app por `agregar_feedback` e, no banco, pela
trigger `tr_avaliacao_atualiza_ia_feedback`), que por sua vez realimenta o
componente de reputacao da recomendacao.

## Mapeamento de requisitos

### Requisitos funcionais (RF1..RF10)

| RF   | Descricao                         | Onde/como foi implementado |
|------|-----------------------------------|----------------------------|
| RF1  | Cadastro de usuario               | `app/usuarios/router.py:cadastrar` + `repository.criar_usuario`; tabelas `Usuario`/`Credencial` (`sql/01_schema.sql`). |
| RF2  | Autenticacao com 2FA              | `app/usuarios/router.py` (`login`, `verificar_2fa`), `app/usuarios/service.py` (`iniciar_login`/`concluir_login`), `app/core/security.py` (TOTP/JWT + token de desafio), SMS via `app/integracoes/sms.py`. A etapa 1 valida a senha e emite um **token de desafio** curto; a etapa 2 exige esse token + o codigo TOTP (reamarra as duas chamadas: nao autentica so com e-mail + codigo). Honra a flag `two_factor`. |
| RF3  | Busca de pacotes                  | `app/catalogo/router.py:buscar_pacotes` + `app/catalogo/service.py:filtrar_pacotes`. |
| RF4  | Orcamento por IA                  | `app/recomendacao/service.py:estimar_orcamento`; endpoint `POST /recomendacao/orcamento`. |
| RF5  | Pagamento (maquina de estados)    | `app/vendas/service.py` (transicoes) + `app/vendas/router.py`; gateway `app/integracoes/pagamento.py`; `sql/04_programmability.sql:sp_registrar_venda`. |
| RF6  | E-mail de confirmacao + propaganda| `app/integracoes/email.py` (`montar_email_confirmacao`, `enviar_confirmacao`). |
| RF7  | Recomendacao de viagens           | `app/recomendacao/service.py:recomendar`/`pontuar_pacote`; endpoint `POST /recomendacao/ranking`. |
| RF8  | Feedback agregado por IA          | `app/recomendacao/service.py:agregar_feedback`; endpoint `POST /recomendacao/feedback`; trigger `tr_avaliacao_atualiza_ia_feedback` + tabela `IA_Feedback`. |
| RF9  | Visualizacao 3D / Street View     | `app/integracoes/streetview.py` + `app/catalogo/router.py:streetview_destino`. |
| RF10 | Estatistica de turistas por destino | `app/estatisticas/service.py:agregar_turistas_por_mes` + `router.py`; view `vw_turistas_por_destino_ano` (`sql/04_programmability.sql`). |

### Requisitos nao funcionais (RNF1..RNF6)

| RNF  | Descricao               | Situacao |
|------|-------------------------|----------|
| RNF1 | Usabilidade / i18n PT-BR + nome social | **Parcial no back-end**: colunas `NVARCHAR` e `nome_social` (`sql/01_schema.sql`), docs/mensagens em Portugues. A parte de UI/usabilidade visual fica no front-end (fora de escopo do MVP). |
| RNF2 | Responsividade          | **Fora de escopo do back-end** (requisito de front-end HTML/CSS/JS). |
| RNF3 | Seguranca / LGPD        | **Implementado**: senhas com hash bcrypt (`app/core/security.py`), 2FA/TOTP, JWT, segredos e integracoes externas via variaveis de ambiente (nenhum segredo hardcoded), autorizacao por papel em `app/core/authz.py`. |
| RNF4 | Integridade / consistencia de dados | **Implementado no banco**: constraints, indices (`sql/03_indexes.sql`), transacao com TRY/CATCH em `sp_registrar_venda`, triggers anti-overbooking e de consistencia do AIV (`sql/04_programmability.sql`). |
| RNF5 | Portabilidade entre navegadores | **Fora de escopo do back-end** (requisito de front-end). |
| RNF6 | Disponibilidade / infraestrutura | **Fora de escopo do MVP**: depende de deploy/operacao. O back-end expoe `/health` para suporte a health checks. |

## Stubs e o que exige o SQL Server do usuario

Integracoes externas ficam atras de interfaces configuraveis por variavel de
ambiente; por padrao operam em **modo stub** (sem rede), o que permite
exercitar e testar todos os fluxos localmente:

- `app/integracoes/sms.py` (`StubSMSSender`): captura o codigo 2FA em memoria.
- `app/integracoes/email.py` (`StubEmailSender`): captura os e-mails em memoria.
- `app/integracoes/pagamento.py` (`StubGatewayPagamento`): aprova
  deterministicamente e registra operacoes.
- `app/integracoes/streetview.py`: monta a URL/embed sem chamada externa (chave
  de API anexada apenas quando configurada).

O que **exige o SQL Server do proprio usuario** para ser exercitado de ponta a
ponta (os endpoints respondem HTTP 503 enquanto o banco nao estiver
configurado):

- Persistencia de usuarios/credenciais (RF1/RF2), busca de pacotes (RF3),
  registro de vendas (RF5) e estatisticas (RF10).
- Os objetos de banco (views, `sp_registrar_venda`, triggers) so sao exercitados
  rodando os scripts `sql/01..05` em um SQL Server real.

A logica de IA do AIV (RF4/RF7/RF8) e as maquinas/heuristicas puras rodam sem
banco e estao totalmente cobertas pelos testes unitarios.
