// Carrinho: lê o pacote reservado (localStorage "pacote_reservado"),
// mostra a prévia, calcula o orçamento (RF4) e registra a compra (RF5) se o
// cliente estiver logado. Usa PACOTES de js/pacotes-dados.js e apiFetch de api.js.

// Fatores do AIV (espelham app/recomendacao/service.py) — usados apenas para
// MOSTRAR ao cliente como o cálculo é feito. O valor oficial vem do back-end.
const FATOR_POR_DIA_EXTRA = 0.03;
const FATORES_REGIME = {
  sem_refeicao: 1.0, cafe_da_manha: 1.08, meia_pensao: 1.18,
  pensao_completa: 1.28, all_inclusive: 1.4,
};
const FATORES_NIVEL = { economico: 1.0, conforto: 1.25, luxo: 1.6 };
const FATOR_ALTA_TEMPORADA = 1.15;
const MESES_ALTA_TEMPORADA = [12, 1, 7]; // dezembro, janeiro, julho

const ROTULO_REGIME = {
  sem_refeicao: "Sem refeição", cafe_da_manha: "Café da manhã",
  meia_pensao: "Meia pensão", pensao_completa: "Pensão completa",
  all_inclusive: "All inclusive",
};
const ROTULO_NIVEL = { economico: "Econômico", conforto: "Conforto", luxo: "Luxo" };

function formatarMoeda(valor) {
  return Number(valor).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
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

// Dias entre duas datas ISO (inclusivo): 20 a 30 de janeiro = 11 dias.
function calcularDias(inicioIso, fimIso) {
  const ms = new Date(fimIso) - new Date(inicioIso);
  return Math.floor(ms / 86400000) + 1;
}

// Alta temporada se a data inicial OU a final cair em dez/jan/jul.
function ehAltaTemporada(inicioIso, fimIso) {
  const mesInicio = new Date(inicioIso).getUTCMonth() + 1;
  const mesFim = new Date(fimIso).getUTCMonth() + 1;
  return MESES_ALTA_TEMPORADA.includes(mesInicio) || MESES_ALTA_TEMPORADA.includes(mesFim);
}

function estaLogado() {
  return !!localStorage.getItem("access_token");
}

function estimarOrcamento(dados) {
  return apiFetch("/recomendacao/orcamento", {
    method: "POST",
    body: JSON.stringify(dados),
  });
}

function registrarVenda(dados) {
  return apiFetch("/vendas", { method: "POST", body: JSON.stringify(dados) });
}

// Monta o detalhamento (linha a linha) de como o total foi obtido.
function montarDetalhe(dl, p) {
  const fatorDuracao = p.dias > 1 ? 1 + (p.dias - 1) * FATOR_POR_DIA_EXTRA : 1.0;
  const fatorRegime = FATORES_REGIME[p.regime] ?? 1.0;
  const fatorNivel = FATORES_NIVEL[p.nivel] ?? 1.0;
  const fatorTemp = p.alta ? FATOR_ALTA_TEMPORADA : 1.0;

  const linhas = [
    ["Preço base", formatarMoeda(p.preco_base)],
    [`Duração (${p.dias} dia(s), +3% por dia extra)`, `× ${fatorDuracao.toFixed(2)}`],
    [`Regime: ${ROTULO_REGIME[p.regime]}`, `× ${fatorRegime.toFixed(2)}`],
    [`Nível: ${ROTULO_NIVEL[p.nivel]}`, `× ${fatorNivel.toFixed(2)}`],
    [`Alta temporada ${p.alta ? "(dez/jan/jul)" : "(não se aplica)"}`, `× ${fatorTemp.toFixed(2)}`],
    [`Pessoas`, `× ${p.pessoas}`],
  ];

  dl.innerHTML = linhas
    .map(([t, v]) => `<div class="resumo-linha"><dt>${t}</dt><dd>${v}</dd></div>`)
    .join("");
}

document.addEventListener("DOMContentLoaded", () => {
  const vazio = document.getElementById("carrinho-vazio");
  const conteudo = document.getElementById("carrinho-conteudo");

  const idReservado = Number(localStorage.getItem("pacote_reservado"));
  const pacote =
    typeof PACOTES !== "undefined" ? PACOTES.find((p) => p.id === idReservado) : null;

  if (!pacote) {
    vazio.hidden = false;
    conteudo.hidden = true;
    return;
  }

  // Prévia do pacote.
  document.getElementById("previa-destino").textContent = `${pacote.cidade} - ${pacote.estado}`;
  document.getElementById("previa-tipo").textContent = capitalizar(pacote.tipo);
  document.getElementById("previa-periodo").textContent = `${pacote.data_inicio} a ${pacote.data_fim}`;
  document.getElementById("previa-preco").textContent = formatarMoeda(pacote.preco_base);
  document.getElementById("previa-vagas").textContent = pacote.vagas;

  // Limita as datas ao período de oferta do pacote.
  const campoInicio = document.getElementById("data_inicio");
  const campoFim = document.getElementById("data_fim");
  for (const campo of [campoInicio, campoFim]) {
    campo.min = pacote.inicio_iso;
    campo.max = pacote.fim_iso;
  }
  campoInicio.value = pacote.inicio_iso;
  campoFim.value = pacote.fim_iso;
  document.getElementById("ajuda-datas").textContent =
    `Entre ${pacote.data_inicio} e ${pacote.data_fim}.`;

  // Limita pessoas às vagas.
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
  const detalheEl = document.getElementById("orcamento-detalhe");
  const valorEl = document.getElementById("orcamento-valor");

  const formConfirmar = document.getElementById("form-confirmar");
  const confirmarFeedback = document.getElementById("confirmar-feedback");
  const btnConfirmar = document.getElementById("btn-confirmar");

  let totalCalculado = null; // valor oficial vindo do back

  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    if (!form.checkValidity()) {
      form.reportValidity();
      return;
    }

    const inicioIso = campoInicio.value;
    const fimIso = campoFim.value;

    // Validações de data contra o período de oferta.
    if (inicioIso < pacote.inicio_iso || fimIso > pacote.fim_iso) {
      mostrarFeedback(feedback, `As datas devem ficar entre ${pacote.data_inicio} e ${pacote.data_fim}.`, "erro");
      return;
    }
    if (fimIso < inicioIso) {
      mostrarFeedback(feedback, "A data final não pode ser anterior à inicial.", "erro");
      return;
    }

    const pessoas = Number(campoPessoas.value);
    if (pessoas > pacote.vagas) {
      mostrarFeedback(feedback, `Há apenas ${pacote.vagas} vaga(s) neste pacote.`, "erro");
      return;
    }

    const dias = calcularDias(inicioIso, fimIso);
    const alta = ehAltaTemporada(inicioIso, fimIso);
    const regime = form.elements["regime"].value;
    const nivel = form.elements["nivel"].value;

    const dados = {
      preco_base: pacote.preco_base,
      dias,
      regime_alimentacao: regime,
      nivel,
      numero_pessoas: pessoas,
      alta_temporada: alta,
    };

    botao.disabled = true;
    feedback.hidden = true;

    try {
      const resposta = await estimarOrcamento(dados);
      totalCalculado = resposta.total_estimado;
      montarDetalhe(detalheEl, { preco_base: pacote.preco_base, dias, regime, nivel, alta, pessoas });
      valorEl.textContent = formatarMoeda(totalCalculado);
      resultado.hidden = false;
      confirmarFeedback.hidden = true;
    } catch (erro) {
      mostrarFeedback(feedback, erro.message || "Não foi possível calcular o orçamento.", "erro");
    } finally {
      botao.disabled = false;
    }
  });

  formConfirmar.addEventListener("submit", async (evento) => {
    evento.preventDefault();

    // Precisa ter um orçamento calculado antes.
    if (totalCalculado == null) {
      mostrarFeedback(confirmarFeedback, "Calcule o orçamento antes de confirmar.", "erro");
      return;
    }

    // Exige login.
    if (!estaLogado()) {
      mostrarFeedback(
        confirmarFeedback,
        "Você precisa entrar na sua conta para concluir a compra.",
        "erro"
      );
      setTimeout(() => {
        window.location.href = "login.html";
      }, 1500);
      return;
    }

    if (!formConfirmar.checkValidity()) {
      formConfirmar.reportValidity();
      return;
    }

    const fkTurista = Number(localStorage.getItem("id_turista"));
    if (!fkTurista) {
      mostrarFeedback(
        confirmarFeedback,
        "Não foi possível identificar sua conta. Entre novamente para concluir.",
        "erro"
      );
      return;
    }

    const dados = {
      fk_conta_turista: fkTurista,
      fk_pacote: pacote.id,
      valor_total: totalCalculado,
      forma_pagamento: formConfirmar.elements["forma_pagamento"].value,
    };

    btnConfirmar.disabled = true;
    confirmarFeedback.hidden = true;

    try {
      const venda = await registrarVenda(dados);
      mostrarFeedback(
        confirmarFeedback,
        `Compra registrada! Venda nº ${venda.id_venda}, status: ${venda.status_pagamento}.`,
        "ok"
      );
      localStorage.removeItem("pacote_reservado");
    } catch (erro) {
      mostrarFeedback(confirmarFeedback, erro.message || "Não foi possível registrar a compra.", "erro");
      btnConfirmar.disabled = false;
    }
  });
});
