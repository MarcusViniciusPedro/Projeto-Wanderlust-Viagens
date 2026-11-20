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
});
