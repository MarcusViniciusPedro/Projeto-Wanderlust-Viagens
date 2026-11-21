// Carrinho: lê o pacote reservado (sessionStorage "pacote_reservado" — dura só
// a sessão do navegador, some ao fechar),
// mostra a prévia, calcula o orçamento (RF4) e registra a compra (RF5) se o
// cliente estiver logado. Busca o pacote no banco (GET /catalogo/pacotes/{id}).

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

// Normaliza um valor de nível/regime para a chave das tabelas de fatores:
// minúsculas, sem acento e com espaços/hífens vira underscore.
// Ex.: "Meia pensao" -> "meia_pensao", "Econômico" -> "economico".
function normalizarChave(v) {
  if (!v) return null;
  return v
    .normalize("NFD").replace(/[\u0300-\u036f]/g, "") // remove acentos
    .trim().toLowerCase()
    .replace(/[\s-]+/g, "_");
}

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

function cancelarVenda(idVenda) {
  return apiFetch(`/vendas/${idVenda}/cancelar`, { method: "POST" });
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
    [`Regime: ${ROTULO_REGIME[p.regime] || "não informado"}`, `× ${fatorRegime.toFixed(2)}`],
    [`Nível: ${ROTULO_NIVEL[p.nivel] || "não informado"}`, `× ${fatorNivel.toFixed(2)}`],
    [`Alta temporada ${p.alta ? "(dez/jan/jul)" : "(não se aplica)"}`, `× ${fatorTemp.toFixed(2)}`],
    [`Pessoas`, `× ${p.pessoas}`],
  ];

  dl.innerHTML = linhas
    .map(([t, v]) => `<div class="resumo-linha"><dt>${t}</dt><dd>${v}</dd></div>`)
    .join("");
}

document.addEventListener("DOMContentLoaded", async () => {
  const vazio = document.getElementById("carrinho-vazio");
  const conteudo = document.getElementById("carrinho-conteudo");

  const idReservado = Number(sessionStorage.getItem("pacote_reservado"));

  // Carrinho vazio: sem pacote reservado.
  if (!idReservado) {
    vazio.hidden = false;
    conteudo.hidden = true;
    return;
  }

  // Busca o pacote real no banco (GET /catalogo/pacotes/{id}).
  let pacote;
  try {
    pacote = await apiFetch(`/catalogo/pacotes/${idReservado}`);
  } catch (erro) {
    // Pacote não existe mais (ex.: removido) ou falha de rede.
    sessionStorage.removeItem("pacote_reservado");
    vazio.hidden = false;
    conteudo.hidden = true;
    return;
  }

  const local =
    pacote.cidade ? `${pacote.cidade} - ${pacote.estado}` : `Pacote ${pacote.id_pacote}`;

  // Nível vem do próprio pacote; regime vem da hospedagem do pacote (a 1ª, se
  // houver). Ambos entram no cálculo do orçamento sem escolha do cliente.
  // Normaliza para casar com as chaves das tabelas de fatores (o banco grava
  // valores como "Economico"/"Meia pensao", as tabelas usam "economico"/"meia_pensao").
  const nivelPacote = normalizarChave(pacote.nivel);
  let regimePacote = null;
  try {
    const hospedagens = await apiFetch(`/catalogo/hospedagens?fk_pacote=${pacote.id_pacote}`);
    if (hospedagens && hospedagens.length) {
      regimePacote = normalizarChave(hospedagens[0].regime_alimentacao);
    }
  } catch (_) { /* sem hospedagem: regime fica neutro no cálculo */ }

  // Identidade visual por tipo na prévia (foto quando houver; senão emoji+cor).
  const IMAGEM_TIPO = {
    praia: "../imgs/praia.jpg", serra: "../imgs/serra.jpg", cultural: "../imgs/cultural.jpg",
  };
  const VISUAL_TIPO = {
    relax: { emoji: "🧘", cor: "#5b8c9e" }, radical: { emoji: "🪂", cor: "#e76f51" },
  };
  const chaveTipo = (pacote.tipo_viagem || "").toLowerCase();
  const previaImg = document.querySelector(".previa-imagem");
  if (previaImg) {
    if (IMAGEM_TIPO[chaveTipo]) {
      previaImg.classList.add("pacote-imagem-foto");
      previaImg.style.backgroundImage = `url('${IMAGEM_TIPO[chaveTipo]}')`;
    } else {
      const vis = VISUAL_TIPO[chaveTipo] || { emoji: "✈️", cor: "#0d3b66" };
      previaImg.classList.add("pacote-imagem-tipo");
      previaImg.style.backgroundColor = vis.cor;
      previaImg.innerHTML = `<span>${vis.emoji}</span>`;
    }
  }

  // Prévia do pacote (campos do back: data_inicio/data_fim ISO, estoque, destino).
  document.getElementById("previa-destino").textContent = local;
  document.getElementById("previa-tipo").textContent =
    pacote.tipo_viagem ? capitalizar(pacote.tipo_viagem) : "—";
  document.getElementById("previa-periodo").textContent = `${pacote.data_inicio} a ${pacote.data_fim}`;
  document.getElementById("previa-preco").textContent = formatarMoeda(pacote.preco_base);
  document.getElementById("previa-vagas").textContent = pacote.estoque;

  // Limita as datas ao período de oferta do pacote (datas ISO do back).
  const campoInicio = document.getElementById("data_inicio");
  const campoFim = document.getElementById("data_fim");
  for (const campo of [campoInicio, campoFim]) {
    campo.min = pacote.data_inicio;
    campo.max = pacote.data_fim;
  }
  campoInicio.value = pacote.data_inicio;
  campoFim.value = pacote.data_fim;
  document.getElementById("ajuda-datas").textContent =
    `Entre ${pacote.data_inicio} e ${pacote.data_fim}.`;

  // Limite fixo de 2 pessoas por reserva.
  const MAX_PESSOAS = 2;
  const campoPessoas = document.getElementById("numero_pessoas");
  campoPessoas.max = MAX_PESSOAS;

  vazio.hidden = true;
  conteudo.hidden = false;

  // Limpar carrinho: remove o pacote reservado e volta ao estado vazio.
  const btnLimpar = document.getElementById("btn-limpar-carrinho");
  if (btnLimpar) {
    btnLimpar.addEventListener("click", () => {
      if (!confirm("Remover o pacote do carrinho?")) return;
      sessionStorage.removeItem("pacote_reservado");
      conteudo.hidden = true;
      vazio.hidden = false;
    });
  }

  const form = document.getElementById("form-orcamento");
  const feedback = document.getElementById("carrinho-feedback");
  const botao = document.getElementById("btn-calcular");
  const resultado = document.getElementById("orcamento-resultado");
  const detalheEl = document.getElementById("orcamento-detalhe");
  const valorEl = document.getElementById("orcamento-valor");

  const btnRevisar = document.getElementById("btn-revisar");
  const revisarFeedback = document.getElementById("revisar-feedback");
  const pagamentoSecao = document.getElementById("pagamento-secao");
  const resumoPedido = document.getElementById("resumo-pedido");

  const formConfirmar = document.getElementById("form-confirmar");
  const confirmarFeedback = document.getElementById("confirmar-feedback");
  const btnConfirmar = document.getElementById("btn-confirmar");
  const btnCancelarVenda = document.getElementById("btn-cancelar-venda");

  let totalCalculado = null; // valor oficial vindo do back
  let pedidoAtual = null; // dados do pedido (datas, pessoas, regime, nível)
  let vendaCriada = null; // id_venda após criar (para efetivar o pagamento)

  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    if (!form.checkValidity()) {
      form.reportValidity();
      return;
    }

    const inicioIso = campoInicio.value;
    const fimIso = campoFim.value;

    // Validações de data contra o período de oferta.
    if (inicioIso < pacote.data_inicio || fimIso > pacote.data_fim) {
      mostrarFeedback(feedback, `As datas devem ficar entre ${pacote.data_inicio} e ${pacote.data_fim}.`, "erro");
      return;
    }
    if (fimIso < inicioIso) {
      mostrarFeedback(feedback, "A data final não pode ser anterior à inicial.", "erro");
      return;
    }

    const pessoas = Number(campoPessoas.value);
    if (pessoas < 1 || pessoas > MAX_PESSOAS) {
      mostrarFeedback(feedback, `A reserva permite no máximo ${MAX_PESSOAS} pessoas.`, "erro");
      return;
    }

    const dias = calcularDias(inicioIso, fimIso);
    const alta = ehAltaTemporada(inicioIso, fimIso);
    // Nível e regime são características do pacote/hospedagem, não escolha do cliente.
    const regime = regimePacote;
    const nivel = nivelPacote;

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
      pedidoAtual = { inicioIso, fimIso, dias, regime, nivel, pessoas, alta };
      montarDetalhe(detalheEl, { preco_base: pacote.preco_base, dias, regime, nivel, alta, pessoas });
      valorEl.textContent = formatarMoeda(totalCalculado);
      resultado.hidden = false;
      // Recalcular esconde o passo de pagamento até revisar de novo.
      pagamentoSecao.hidden = true;
      revisarFeedback.hidden = true;
      confirmarFeedback.hidden = true;
    } catch (erro) {
      mostrarFeedback(feedback, erro.message || "Não foi possível calcular o orçamento.", "erro");
    } finally {
      botao.disabled = false;
    }
  });

  // Passo 1: revisar e confirmar — exige login antes de mostrar o pagamento.
  btnRevisar.addEventListener("click", () => {
    if (totalCalculado == null) {
      mostrarFeedback(revisarFeedback, "Calcule o orçamento antes de confirmar.", "erro");
      return;
    }
    if (!estaLogado()) {
      mostrarFeedback(
        revisarFeedback,
        "Você precisa entrar na sua conta para concluir a compra. Redirecionando...",
        "erro"
      );
      setTimeout(() => {
        window.location.href = "login.html";
      }, 1500);
      return;
    }

    // Logado: monta o resumo do pedido e revela as opções de pagamento.
    resumoPedido.innerHTML = [
      ["Destino", local],
      ["Período escolhido", `${pedidoAtual.inicioIso} a ${pedidoAtual.fimIso} (${pedidoAtual.dias} dia(s))`],
      ["Pessoas", pedidoAtual.pessoas],
      ["Regime", ROTULO_REGIME[pedidoAtual.regime] || "não informado"],
      ["Nível", ROTULO_NIVEL[pedidoAtual.nivel] || "não informado"],
      ["Total", formatarMoeda(totalCalculado)],
    ]
      .map(([t, v]) => `<div class="resumo-linha"><dt>${t}</dt><dd>${v}</dd></div>`)
      .join("");

    revisarFeedback.hidden = true;
    pagamentoSecao.hidden = false;
    pagamentoSecao.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });

  // Passo 2: finalizar — o login já foi exigido no passo "Revisar".
  formConfirmar.addEventListener("submit", async (evento) => {
    evento.preventDefault();

    if (totalCalculado == null) {
      mostrarFeedback(confirmarFeedback, "Calcule o orçamento antes de confirmar.", "erro");
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
      fk_pacote: pacote.id_pacote,
      valor_total: totalCalculado,
      forma_pagamento: formConfirmar.elements["forma_pagamento"].value,
    };

    btnConfirmar.disabled = true;
    confirmarFeedback.hidden = true;

    try {
      // Registra a venda de verdade (nasce "Pendente"); não há etapa de pagamento.
      const venda = await registrarVenda(dados);
      vendaCriada = venda.id_venda;
      mostrarFeedback(
        confirmarFeedback,
        `Reserva confirmada! Venda nº ${venda.id_venda} registrada (${venda.status_pagamento}). ` +
          "O pagamento será tratado pela agência.",
        "ok"
      );
      // Trava a forma de pagamento e permite apenas cancelar a reserva.
      for (const campo of formConfirmar.elements) campo.disabled = true;
      btnCancelarVenda.hidden = false;
    } catch (erro) {
      mostrarFeedback(confirmarFeedback, erro.message || "Não foi possível registrar a reserva.", "erro");
      btnConfirmar.disabled = false;
    }
  });

  // Cancela a venda pendente: POST /vendas/{id}/cancelar (Pendente -> Cancelado).
  btnCancelarVenda.addEventListener("click", async () => {
    if (!vendaCriada) return;
    if (!confirm("Cancelar esta compra? A venda ficará como Cancelada.")) return;
    btnCancelarVenda.disabled = true;
    confirmarFeedback.hidden = true;
    try {
      const venda = await cancelarVenda(vendaCriada);
      mostrarFeedback(
        confirmarFeedback,
        `Compra cancelada. Venda nº ${venda.id_venda}, status: ${venda.status_pagamento}.`,
        "ok"
      );
      btnCancelarVenda.hidden = true;
      vendaCriada = null;
      sessionStorage.removeItem("pacote_reservado");
    } catch (erro) {
      mostrarFeedback(confirmarFeedback, erro.message || "Não foi possível cancelar a compra.", "erro");
      btnCancelarVenda.disabled = false;
    }
  });
});
