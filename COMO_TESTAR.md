# Como executar e testar o sistema localmente

Você precisa de três coisas no ar: **SQL Server**, **back-end** (FastAPI) e
**front-end** (estático). Os scripts SQL e o back-end estão no branch
`feat/backend-wanderlust`; o front, no branch `main`. Use um *checkout* ou
*worktree* do branch de back para os passos 1–3.

> O banco é **descartável**: os testes escrevem de verdade (criam/apagam
> pacotes, vendas, contas). Para zerar, basta recriar o banco (passo 2).

---

## 1. Subir o SQL Server

Qualquer instância SQL Server 2017+ serve. Com Docker (descartável):

```bash
docker run -d --name wanderlust-sql \
  -e "ACCEPT_EULA=Y" -e "MSSQL_SA_PASSWORD=SuaSenha!123" \
  -p 1433:1433 mcr.microsoft.com/mssql/server:2022-latest
```

A senha do `sa` deve ser forte (maiúscula, minúscula, número e símbolo).
Se já tiver um SQL Server instalado, use-o — só precisa de usuário, senha e a
porta 1433.

---

## 2. Configurar e criar o banco

No branch do back (`feat/backend-wanderlust`):

```bash
# ambiente Python (uma vez)
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e '.[dev]'

# configuração: copie o exemplo e ajuste o banco + JWT
cp .env.example .env
```

Edite o `.env` com os dados do seu SQL Server. O banco criado chama-se
**`agencia_viagens`**:

```
WANDERLUST_DB_SERVER=localhost
WANDERLUST_DB_PORT=1433
WANDERLUST_DB_NAME=agencia_viagens
WANDERLUST_DB_USER=sa
WANDERLUST_DB_PASSWORD=SuaSenha!123
WANDERLUST_JWT_SECRET=qualquer-coisa-aleatoria-para-dev
```

As demais variáveis (SMS, e-mail, pagamento, Street View) podem ficar vazias
(modo stub). Crie/recrie o banco do zero com **um comando** — ele dropa o banco
se existir, roda `sql/01`..`sql/06` e já cria o admin de teste:

```bash
.venv/bin/python criar_banco.py
```

---

## 3. Subir o back-end

```bash
.venv/bin/uvicorn app.main:app --reload
```

Deixe o terminal aberto. Confira:

- API: http://localhost:8000
- Swagger (testar endpoints à mão): http://localhost:8000/docs
- Saúde do banco: http://localhost:8000/health/db → deve dizer `conectado`.

---

## 4. Servir o front-end

No branch `main`, sirva pela porta **5500** (a liberada pelo CORS) — por
exemplo a extensão **Live Server** do VS Code, abrindo `index.html`.

A URL deve ficar `http://localhost:5500/...`. Abrir o HTML por duplo clique
(`file://`) **não funciona**: o navegador bloqueia as chamadas à API por CORS.

---

## 5. Acesso de administrador

O `criar_banco.py` já cria um admin de teste pronto, com 2FA desligado
(login só com e-mail e senha):

- **E-mail:** `admin@wanderlust.com`
- **Senha:** `Admin123`

Ao logar como admin, aparece um **cadeado** no menu, que abre o painel de
administração. Contas criadas pela tela de cadastro nascem como **Turista**,
sem 2FA e já aptas a comprar.

---

## 6. Roteiro de teste

1. **Cadastro** — crie uma conta de turista pela tela (`SELECT * FROM Usuario`
   para conferir).
2. **Login** — entre com o admin (2FA off → só clicar "Verificar e entrar") ou
   com o turista que cadastrou. Logado, o menu mostra "Meu perfil"/"Sair" e,
   para admin, o cadeado.
3. **Painel admin** (cadeado) — CRUD de destinos, pacotes e hospedagens; gestão
   de contas; estatísticas por destino. A ordem de cadastro é
   **destino → pacote → hospedagem**.
4. **Catálogo** (`pages/pacotes.html`) — vem do banco; filtra por destino/tipo/
   valor/data; cada pacote tem avaliações e botão "Reserve já".
5. **Carrinho** — reserve um pacote, escolha datas (dentro do período), calcule
   o orçamento (AIV) e finalize. A venda é registrada como `Pendente`
   (`SELECT * FROM Venda`).

---

## Dicas e solução de problemas

- **Recriar o banco:** `.venv/bin/python criar_banco.py` (dropa e refaz; o admin
  de teste volta). Use quando os dados de teste "sujarem".
- **NetworkError no navegador:** quase sempre o back não está no ar ou o front
  foi aberto por `file://`. Confira `http://localhost:8000/health` e use o Live
  Server na 5500.
- **HTTP 503 nas telas:** o back não achou o banco. Cheque o `.env` e
  `/health/db`.
- **401/403 no painel admin:** o token não tem papel de admin. Logue com o admin
  (o papel vai no token no momento do login).
- **Excluir pacote/destino falha com mensagem de "vinculado":** é esperado —
  há hospedagem/venda (ou pacote/viagem) dependente. Remova as dependências
  primeiro.
- **Recarregue com Ctrl+Shift+R** após mudar arquivos do front, para o navegador
  não usar JS em cache.
