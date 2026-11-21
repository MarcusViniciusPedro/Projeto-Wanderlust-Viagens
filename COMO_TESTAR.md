# Como testar o sistema localmente (banco + back + front + admin)

Guia de teste para desenvolvimento. **Use um banco descartável** — os testes
escrevem de verdade (criam/apagam pacotes, vendas, contas). Para zerar tudo,
basta dropar o banco e rodar os scripts de novo.

Os scripts SQL e o código do back-end estão no branch `feat/backend-wanderlust`.
Rode os comandos a partir de um checkout desse branch (ou de um worktree dele).

---

## 1. Subir o SQL Server

### Opção A — Docker (mais simples, descartável)

```bash
docker run -d --name wanderlust-sql \
  -e "ACCEPT_EULA=Y" \
  -e "MSSQL_SA_PASSWORD=SuaSenha!123" \
  -p 1433:1433 \
  mcr.microsoft.com/mssql/server:2022-latest
```

- Guarde a senha escolhida (`SuaSenha!123`). O SQL Server exige senha forte
  (maiúscula, minúscula, número e símbolo).
- Para **zerar tudo** depois: `docker rm -f wanderlust-sql` e rode o comando de
  novo. Banco limpo em segundos.

### Opção B — SQL Server já instalado

Use sua instância local; só precisa do usuário/senha e da porta 1433.

---

## 2. Criar o banco e as tabelas (rodar os scripts na ordem)

Com o cliente `sqlcmd` (ou Azure Data Studio / SSMS), execute `sql/01` a `sql/05`
**nesta ordem**:

```bash
for n in 01_schema 02_aiv_tables 03_indexes 04_programmability 05_seed_dml; do
  sqlcmd -S localhost -U sa -P 'SuaSenha!123' -i sql/${n}.sql
done
```

> O nome do banco criado pelos scripts deve bater com `WANDERLUST_DB_NAME` no
> `.env` (passo 3). Confira no topo de `sql/01_schema.sql` qual nome ele cria e
> ajuste o `.env` para o mesmo valor.

---

## 3. Configurar e subir o back-end (FastAPI)

```bash
# criar venv e instalar (uma vez)
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e '.[dev]'

# criar o .env a partir do exemplo e editar os valores do banco + JWT
cp .env.example .env
```

Edite o `.env` e ajuste pelo menos:

```
WANDERLUST_DB_SERVER=localhost
WANDERLUST_DB_PORT=1433
WANDERLUST_DB_NAME=<nome do banco criado em sql/01>
WANDERLUST_DB_USER=sa
WANDERLUST_DB_PASSWORD=SuaSenha!123
WANDERLUST_JWT_SECRET=qualquer-coisa-aleatoria-para-teste
```

As demais variáveis (SMS, e-mail, pagamento, Street View) podem ficar **vazias**
— rodam em modo stub. O CORS já vem liberado para o Live Server (porta 5500).

Subir a API:

```bash
.venv/bin/uvicorn app.main:app --reload
```

- API: http://localhost:8000
- Swagger (testar endpoints à mão): http://localhost:8000/docs
- Health do banco: http://localhost:8000/health/db  → confirma se o back achou o SQL Server.

---

## 4. Criar o usuário administrador de teste

O seed **não** traz admin logável (senhas fictícias). Crie o seu:

1. Suba o front (passo 5) e **cadastre-se** pela tela de cadastro com um e-mail e
   senha à sua escolha (ex.: `admin@wanderlust.com` / `admin123`).
2. No banco, **promova a admin e desligue o 2FA** (para logar sem código SMS):

```sql
UPDATE Usuario SET papel = 'Administrador'
  WHERE email = 'admin@wanderlust.com';

UPDATE Credencial SET two_factor = 0
  WHERE id_usuario = (SELECT id_passageiro FROM Usuario
                      WHERE email = 'admin@wanderlust.com');
```

> Por que desligar o 2FA: em dev o código SMS é um stub (fica só na memória do
> back, não chega a lugar nenhum pela interface). Com `two_factor = 0` o login
> conclui sem precisar do código.

---

## 5. Servir o front-end

O front está no branch `main`. Sirva pela porta **5500** (a que o CORS libera):

- No VS Code, use a extensão **Live Server** → "Open with Live Server" no
  `index.html`.
- A URL deve ficar `http://localhost:5500/...` ou `http://127.0.0.1:5500/...`.

Abrir com duplo clique (`file://`) **não funciona** para as chamadas à API
(o CORS bloqueia). Use o Live Server.

---

## 6. Roteiro de teste

1. **Cadastro** — crie uma conta pela tela. Confira no banco (`SELECT * FROM Usuario`).
2. **Login** — entre com o admin (2FA off → é só clicar "Verificar e entrar").
   Ao logar, o **ícone de cadeado** aparece no menu.
3. **Painel admin** (cadeado) — teste o CRUD de pacotes e o RUD de contas.
4. **Catálogo/carrinho** — reserve um pacote, calcule o orçamento, finalize e
   pague. Confira a venda no banco (`SELECT * FROM Venda`).

---

## Catálogo público x banco (limitação conhecida)

O catálogo público (`pages/pacotes.html`) agora vem **direto do banco** via
`GET /catalogo/pacotes` — os cards mostram cidade/estado/descrição do destino
associado (FK Pacote->Destino). No painel admin, o formulário de pacote traz um
seletor de **Destino** carregado de `GET /catalogo/destinos`; todo pacote exige
um destino.

A **home** (busca + recomendação) e o **carrinho** (orçamento + venda) **ainda
leem o array estático `js/pacotes-dados.js`**. Essas telas dependem de campos
que o back não expõe hoje (limites de data em ISO, vagas, tipo em slug e lookup
por id), então sua migração fica como trabalho futuro — exige o back expor esses
dados. `js/pacotes-dados.js` é mantido como fallback só para essas duas telas.

## Dicas

- **Zerar o banco:** `docker rm -f wanderlust-sql` + repetir passos 1 e 2.
- **Ver o que mudou:** `SELECT * FROM Usuario; SELECT * FROM Pacote; SELECT * FROM Venda;`
- **Erro 503 nas telas:** o back não achou o banco. Cheque o `.env` e o
  `/health/db`.
- **Erro 401/403 no painel admin:** o token não tem papel de admin. Refaça o
  login após os UPDATEs do passo 4 (o papel vai no token no momento do login).
- **Recarregue com Ctrl+Shift+R** após mudanças no front, para o navegador não
  usar JS em cache.
```
