// Barra de busca da home. Usa PACOTES de js/pacotes-dados.js.
// O formulário usa GET para pages/pacotes.html, então os filtros vão na URL
// nativamente; aqui só preenchemos o select de estado e o texto do slider.

document.addEventListener("DOMContentLoaded", () => {
  const selectEstado = document.getElementById("busca-estado");
  if (selectEstado && typeof PACOTES !== "undefined") {
    const estados = [...new Set(PACOTES.map((p) => p.estado))].sort();
    for (const uf of estados) {
      const opt = document.createElement("option");
      opt.value = uf;
      opt.textContent = uf;
      selectEstado.appendChild(opt);
    }
  }

  const valor = document.getElementById("busca-valor");
  const saida = document.getElementById("busca-valor-saida");
  if (valor && saida) {
    const atualizar = () => {
      saida.textContent = Number(valor.value).toLocaleString("pt-BR", {
        style: "currency",
        currency: "BRL",
      });
    };
    valor.addEventListener("input", atualizar);
    atualizar();
  }

  // --- Recomendação (RF7): POST /recomendacao/ranking -------------------
  const formRec = document.getElementById("form-recomendacao");
  if (formRec && typeof PACOTES !== "undefined") {
    const feedbackRec = document.getElementById("recomendacao-feedback");
    const listaRec = document.getElementById("recomendacao-lista");
    const btnRec = document.getElementById("btn-recomendar");

    const moeda = (v) =>
      Number(v).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

    formRec.addEventListener("submit", async (evento) => {
      evento.preventDefault();

      // Candidatos: os pacotes estáticos. Sem avaliações, o componente de
      // reputação do back cai no neutro (0.5) para todos.
      const pacotes = PACOTES.map((p) => ({
        id_pacote: p.id,
        preco_base: p.preco_base,
        tipo_viagem: p.tipo,
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
          body: JSON.stringify({ preferencia, pacotes }),
        });

        listaRec.innerHTML = ranking
          .map((item) => {
            const pac = PACOTES.find((p) => p.id === item.id_pacote);
            const nome = pac ? `${pac.cidade} - ${pac.estado}` : `Pacote ${item.id_pacote}`;
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
