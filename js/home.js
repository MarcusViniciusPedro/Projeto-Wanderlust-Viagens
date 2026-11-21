// Barra de busca e recomendação da home. Consome o banco via apiFetch:
//   GET /catalogo/pacotes   -> para o select de tipo e a recomendação (RF7)
// O formulário de recomendação redireciona para pages/pacotes.html (filtros na URL).

document.addEventListener("DOMContentLoaded", async () => {
  // Carrega os pacotes do banco (tolerante a falha de rede) para o select de
  // tipo e para a recomendação (RF7).
  let pacotes = [];
  try {
    const res = await apiFetch("/catalogo/pacotes");
    pacotes = res.pacotes || [];
  } catch (_) { /* segue com lista vazia */ }

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
