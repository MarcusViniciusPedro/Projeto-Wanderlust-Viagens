# Projeto Wanderlust Viagens

Back-end da agencia de viagens **Wanderlust Viagens**. O sistema e construido
com **Python (FastAPI)** para a API e **SQL Server (T-SQL)** para o banco de
dados, preparado para integracao posterior com o front-end (HTML/CSS/JS).

## Arquitetura

Monolito modular que espelha os microsservicos planejados, pronto para ser
dividido no futuro:

- `app/usuarios/` — perfis e autenticacao (Turista, Agente de Viagens, Administrador).
- `app/catalogo/` — catalogo de pacotes e destinos.
- `app/vendas/` — carrinho, vendas e maquina de estados de pagamento.
- `app/recomendacao/` — recomendacao de viagens (AIV), heuristica deterministica.
- `app/integracoes/` — stubs de SMS, e-mail, gateway de pagamento e Street View.
- `app/core/` — configuracao da aplicacao (via `.env`).
- `app/db/` — fabrica de conexao preguicosa com o SQL Server (pymssql).

> As regras de dominio e os scripts T-SQL serao adicionados em features
> seguintes. Esta baseline entrega apenas o esqueleto que sobe sem banco vivo.

## Requisitos

- Python 3.11+
- SQL Server (opcional nesta fase; a API sobe e os testes rodam sem banco).

## Como rodar (desenvolvimento)

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e '.[dev]'

# Validar que a app importa sem conectar ao banco
.venv/bin/python -c "import app.main; print('import ok')"

# Rodar a API
.venv/bin/uvicorn app.main:app --reload
```

Acesse a documentacao interativa em `http://localhost:8000/docs`.

## Configuracao

Copie `.env.example` para `.env` e preencha as variaveis. Nenhum segredo e
commitado; `.env` e `.venv/` estao no `.gitignore`.

## Testes

```bash
.venv/bin/pytest -q
```

Testes de integracao que exigem um SQL Server vivo sao marcados com
`@pytest.mark.integration` e **pulados por padrao**. Para roda-los com um banco
disponivel:

```bash
.venv/bin/pytest -m integration
```
