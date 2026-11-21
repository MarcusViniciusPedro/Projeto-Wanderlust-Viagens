# Projeto-Wanderlust-Viagens

Agencia de viagens com backend FastAPI (monolito modular por dominio) e
frontend estatico (HTML/CSS/JS), apoiado por um banco SQL Server (T-SQL) com
stored procedures. Consulte [COMO_TESTAR.md](COMO_TESTAR.md) para subir o
ambiente local e [docs/dicionario_de_dados.md](docs/dicionario_de_dados.md)
para o modelo de dados.

## Mapeamento de requisitos (RF/RNF)

A tabela abaixo reflete o backend atual depois da poda de recursos nao usados
pelo frontend.

| Requisito | Situacao       | Endpoints / observacao                                                        |
|-----------|----------------|-------------------------------------------------------------------------------|
| RF1/RF2   | Implementado   | Cadastro e login com 2FA: `POST /auth/cadastro`, `POST /auth/login`, `POST /auth/2fa/verificar`. |
| RF3       | Implementado   | Busca de pacotes no catalogo: `GET /catalogo/pacotes`, `GET /catalogo/pacotes/{id}`. Filtragem em Python. |
| RF4       | Implementado   | Orcamento de viagem: `POST /recomendacao/orcamento`.                          |
| RF5       | Implementado   | Compra/venda de pacote: `POST /vendas`, `POST /vendas/{id}/pagar`, `POST /vendas/{id}/cancelar`. |
| RF6       | Removido       | Nao cadastramos e-mails de envio, entao a integracao de e-mail foi descartada. |
| RF7       | Implementado   | Recomendacao/ranking de pacotes: `POST /recomendacao/ranking`.                |
| RF8       | Implementado   | Avaliacoes e feedback do AIV: `POST /recomendacao/avaliacoes`, `POST /recomendacao/feedback`, `GET /recomendacao/pacotes/{id}/feedback`. |
| RF9       | Removido       | Visualizacao Street View descartada (integracao removida do backend).         |
| RF10      | Implementado   | Estatisticas de turistas por destino: `GET /estatisticas/turistas-por-destino`. |
| RNF1      | Implementado   | Nome social e pronome no cadastro (design inclusivo).                         |
| RNF3      | Implementado   | Credenciais isoladas, 2FA e moderacao de contas pelo admin.                   |

## Gestao de catalogo e contas (admin)

- Catalogo (gated por GERENCIAR_CATALOGO): CRUD de pacotes, destinos e
  hospedagens em `/catalogo/pacotes`, `/catalogo/destinos` e
  `/catalogo/hospedagens`. As leituras de catalogo (`GET`), incluindo as de
  hospedagem, sao publicas para o front (carrinho/catalogo).
- Contas (gated por GERENCIAR_CONTAS): `GET /auth/admin/contas`,
  `PATCH /auth/admin/contas/{id}/status` (banir/denunciar/reativar) e
  `DELETE /auth/admin/contas/{id}`. A exclusao de conta e um **hard delete**:
  a linha e removida junto com seus dependentes (decisao de produto).

## Endpoints removidos

- Os endpoints administrativos de **Agendar Viagem** foram removidos porque o
  frontend nao tem tela de viagens. A tabela `Viagem` permanece no banco por ser
  necessaria as estatisticas de RF10 (Venda -> Passagem -> Viagem -> Destino).
- As integracoes de e-mail (RF6) e Street View (RF9) foram removidas.
