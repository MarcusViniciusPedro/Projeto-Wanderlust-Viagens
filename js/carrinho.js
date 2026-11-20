// Carrinho: lê o pacote reservado (localStorage "pacote_reservado"),
// mostra a prévia e calcula o orçamento via POST /recomendacao/orcamento (RF4).
// Usa PACOTES de js/pacotes-dados.js e apiFetch de js/api.js.

function formatarMoeda(valor) {
  return Number(valor).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
}

function mostrarFeedback(caixa, mensagem, tipo) {
  caixa.textContent = mensagem;
  caixa.classList.remove("feedback-erro", "feedback-ok");
  caixa.classList.add(tipo === "ok" ? "feedback-ok" : "feedback-erro");
  caixa.hidden = false;
}

function capitalizar(texto) {
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

function estimarOrcamento(dados) {
  return apiFetch("/recomendacao/orcamento", {
    method: "POST",
    body: JSON.stringify(dados),
  });
}

document.addEventListener("DOMContentLoaded", () => {
  const vazio = document.getElementById("carrinho-vazio");
  const conteudo = document.getElementById("carrinho-conteudo");

  const idReservado = Number(localStorage.getItem("pacote_reservado"));
  const pacote =
    typeof PACOTES !== "undefined"
      ? PACOTES.find((p) => p.id === idReservado)
      : null;

  // Carrinho vazio: mostra aviso com link para pacotes.
  if (!pacote) {
    vazio.hidden = false;
    conteudo.hidden = true;
    return;
  }

  // Preenche a prévia do pacote selecionado.
  document.getElementById("previa-destino").textContent = `${pacote.cidade} - ${pacote.estado}`;
  document.getElementById("previa-tipo").textContent = capitalizar(pacote.tipo);
  document.getElementById("previa-periodo").textContent = `${pacote.data_inicio} a ${pacote.data_fim}`;
  document.getElementById("previa-preco").textContent = formatarMoeda(pacote.preco_base);
  document.getElementById("previa-vagas").textContent = pacote.vagas;

  // Limita a quantidade de pessoas ao número de vagas do pacote.
  const campoPessoas = document.getElementById("numero_pessoas");
  campoPessoas.max = pacote.vagas;
  document.getElementById("ajuda-pessoas").textContent =
    `Máximo de ${pacote.vagas} pessoa(s), conforme as vagas do pacote.`;

  vazio.hidden = true;
  conteudo.hidden = false;

  const form = document.getElementById("form-orcamento");
  const feedback = document.getElementById("carrinho-feedback");
  const botao = document.getElementById("btn-calcular");
  const resultado = document.getElementById("orcamento-resultado");
  const valorEl = document.getElementById("orcamento-valor");

  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();

    if (!form.checkValidity()) {
      form.reportValidity();
      return;
    }

    const pessoas = Number(campoPessoas.value);
    if (pessoas > pacote.vagas) {
      mostrarFeedback(feedback, `Há apenas ${pacote.vagas} vaga(s) neste pacote.`, "erro");
      return;
    }

    const dados = {
      preco_base: pacote.preco_base,
      dias: Number(form.elements["dias"].value),
      regime_alimentacao: form.elements["regime"].value,
      nivel: form.elements["nivel"].value,
      numero_pessoas: pessoas,
      alta_temporada: form.elements["alta_temporada"].checked,
    };

    botao.disabled = true;
    feedback.hidden = true;

    try {
      const resposta = await estimarOrcamento(dados);
      valorEl.textContent = formatarMoeda(resposta.total_estimado);
      resultado.hidden = false;
    } catch (erro) {
      mostrarFeedback(
        feedback,
        erro.message || "Não foi possível calcular o orçamento. Tente novamente.",
        "erro"
      );
    } finally {
      botao.disabled = false;
    }
  });
});
