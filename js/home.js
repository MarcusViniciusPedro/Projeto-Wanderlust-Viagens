// Barra de busca e recomendação da home. Consome o banco via apiFetch:
//   GET /catalogo/pacotes   -> para o select de tipo e a recomendação (RF7)
//   GET /catalogo/destinos  -> para o select de destino (estados reais)
// O formulário de busca usa GET para pages/pacotes.html (filtros na URL).

document.addEventListener("DOMContentLoaded", async () => {
  const moeda = (v) =>
    Number(v).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

  // Slider de valor máximo.
  const valor = document.getElementById("busca-valor");
  const saida = document.getElementById("busca-valor-saida");
  if (valor && saida) {
    const atualizar = () => { saida.textContent = moeda(Number(valor.value)); };
    valor.addEventListener("input", atualizar);
    atualizar();
  }

  // Carrega pacotes e destinos do banco (tolerante a falha de rede).
  let pacotes = [];
  let destinos = [];
  try {
    const res = await apiFetch("/catalogo/pacotes");
    pacotes = res.pacotes || [];
  } catch (_) { /* segue com lista vazia */ }
  try {
    destinos = await apiFetch("/catalogo/destinos");
  } catch (_) { /* segue com lista vazia */ }

  // Select de destino (estados reais dos destinos cadastrados).
  const selectEstado = document.getElementById("busca-estado");
  if (selectEstado) {
    const estados = [...new Set(destinos.map((d) => d.estado))].sort();
    for (const uf of estados) {
      const opt = document.createElement("option");
      opt.value = uf;
      opt.textContent = uf;
      selectEstado.appendChild(opt);
    }
  }

  // Select de tipo de viagem (tipos reais presentes nos pacotes).
  // Select de tipo do formulário de recomendação: tipos reais dos pacotes.
  const selectTipo = document.getElementById("rec-tipo");
  if (selectTipo) {
    const tipos = [...new Set(pacotes.map((p) => p.tipo_viagem).filter(Boolean))].sort();
    for (const t of tipos) {
      const opt = document.createElement("option");
      opt.value = t;
      opt.textContent = t.charAt(0).toUpperCase() + t.slice(1);
      selectTipo.appendChild(opt);
    }
  }

  // --- Recomendação (RF7): POST /recomendacao/ranking -------------------
  // Recomendação: ao enviar, redireciona para pacotes.html com as preferências
  // na URL (?recomendar=1&...). O ranking e os selos são exibidos lá.
  const formRec = document.getElementById("form-recomendacao");
  if (formRec) {
    formRec.addEventListener("submit", (evento) => {
      evento.preventDefault();
      const params = new URLSearchParams({ recomendar: "1" });
      const tipo = formRec.elements["tipo_viagem"].value;
      const nivel = formRec.elements["nivel"].value;
      const orcamento = formRec.elements["orcamento_max"].value.trim();
      if (tipo) params.set("tipo_viagem", tipo);
      if (nivel) params.set("nivel", nivel);
      if (orcamento) params.set("orcamento_max", orcamento);
      window.location.href = `pages/pacotes.html?${params.toString()}`;
    });
  }
});
