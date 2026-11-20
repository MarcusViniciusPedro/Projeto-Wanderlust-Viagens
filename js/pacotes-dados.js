// Fonte única de dados dos pacotes (conteúdo estático do front).
// O back-end não expõe nome/descrição/imagem de pacote, então estes dados
// vivem aqui. Campos tipo/datas/preço/estoque espelham o que o back usaria.
// `id` corresponderia ao id_pacote do back (fk_pacote usado na venda/carrinho).
//
// Datas:
//   data_inicio / data_fim  -> texto para exibição ("20 de janeiro")
//   inicio_iso / fim_iso    -> período de oferta em ISO (AAAA-MM-DD), usado
//                              para limitar as datas que o cliente pode escolher.

const PACOTES = [
  {
    id: 1,
    cidade: "São Paulo",
    estado: "SP",
    tipo: "cultural",
    data_inicio: "20 de janeiro",
    data_fim: "30 de janeiro",
    inicio_iso: "2026-01-20",
    fim_iso: "2026-01-30",
    preco_base: 500,
    vagas: 15,
    descricao:
      "Estadia no centro de São Paulo com passeios pelo Teatro Municipal, " +
      "Edifício Copan e Farol Santander.",
  },
  {
    id: 2,
    cidade: "Boituva",
    estado: "SP",
    tipo: "radical",
    data_inicio: "10 de janeiro",
    data_fim: "20 de janeiro",
    inicio_iso: "2026-01-10",
    fim_iso: "2026-01-20",
    preco_base: 5000,
    vagas: 10,
    descricao:
      "Estadia na cidade referência em esportes radicais, passeios incluindo " +
      "paraquedismo e voos de balão.",
  },
  {
    id: 3,
    cidade: "Governador Celso Ramos",
    estado: "SC",
    tipo: "relax",
    data_inicio: "5 de janeiro",
    data_fim: "10 de janeiro",
    inicio_iso: "2026-01-05",
    fim_iso: "2026-01-10",
    preco_base: 6000,
    vagas: 5,
    descricao: "Estadia no Hotel 5 estrelas Awasi Santa Catarina.",
  },
];
