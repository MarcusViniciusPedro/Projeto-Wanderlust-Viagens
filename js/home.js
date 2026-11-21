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
  const selectTipo = document.getElementById("busca-tipo");
  if (selectTipo) {
    const tipos = [...new Set(pacotes.map((p) => p.tipo_viagem).filter(Boolean))].sort();
    // Mantém a opção "Todos" (primeira) e substitui as demais pelas reais.
    for (const t of tipos) {
      const opt = document.createElement("option");
      opt.value = t;
      opt.textContent = t.charAt(0).toUpperCase() + t.slice(1);
      selectTipo.appendChild(opt);
    }
  }

  // --- Recomendação (RF7): POST /recomendacao/ranking -------------------
  const formRec = document.getElementById("form-recomendacao");
  if (formRec) {
    const feedbackRec = document.getElementById("recomendacao-feedback");
    const listaRec = document.getElementById("recomendacao-lista");
    const btnRec = document.getElementById("btn-recomendar");

    formRec.addEventListener("submit", async (evento) => {
      evento.preventDefault();

      if (!pacotes.length) {
        feedbackRec.textContent = "Não há pacotes disponíveis para recomendar.";
        feedbackRec.classList.add("feedback-erro");
        feedbackRec.hidden = false;
        return;
      }

      // Candidatos: pacotes do banco. Sem avaliações, o componente de
      // reputação do back cai no neutro (0.5) para todos.
      const candidatos = pacotes.map((p) => ({
        id_pacote: p.id_pacote,
        preco_base: p.preco_base,
        tipo_viagem: p.tipo_viagem,
        nivel: p.nivel ?? null,
        total_avaliacoes: 0,
      }));

      const orcamento = formRec.elements["orcamento_max"].value.trim();
      const preferencia = {
        tipo_viagem: formRec.elements["tipo_viagem"].value || null,
        nivel: formRec.elements["nivel"].value || null,
        orcamento_max: orcamento ? Number(orcamento) : null,
      };

      btnRec.disabled = true;
      feedbackRec.hidden = true;
      listaRec.hidden = true;

      try {
        const ranking = await apiFetch("/recomendacao/ranking", {
          method: "POST",
          body: JSON.stringify({ preferencia, pacotes: candidatos }),
        });

        listaRec.innerHTML = ranking
          .map((item) => {
            const pac = pacotes.find((p) => p.id_pacote === item.id_pacote);
            const nome = pac && pac.cidade ? `${pac.cidade} - ${pac.estado}` : `Pacote ${item.id_pacote}`;
            const preco = pac ? ` — ${moeda(pac.preco_base)}` : "";
            const selo = item.dentro_do_orcamento
              ? '<span class="rec-selo rec-ok">dentro do orçamento</span>'
              : '<span class="rec-selo rec-fora">acima do orçamento</span>';
            return `<li><strong>${nome}</strong>${preco} ${selo}
              <span class="rec-score">aderência ${Math.round(item.score * 100)}%</span></li>`;
          })
          .join("");
        listaRec.hidden = false;
      } catch (erro) {
        feedbackRec.textContent =
          erro.message || "Não foi possível obter recomendações. Tente novamente.";
        feedbackRec.classList.add("feedback-erro");
        feedbackRec.hidden = false;
      } finally {
        btnRec.disabled = false;
      }
    });
  }
});
