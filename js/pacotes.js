// Renderização e filtragem dos pacotes (página pacotes.html).
// Consome GET /catalogo/pacotes do back (via apiFetch de js/api.js), exibindo
// cidade/estado/descrição do destino associado (FK Pacote->Destino).
//
// Filtros suportados (todos opcionais), lidos da query string da URL:
//   estado      -> UF exata (ex.: "SP")
//   tipo_viagem -> tipo exato (relax/cultural/radical)
//   valor_max   -> preço base <= valor
//   data_inicio -> ISO "AAAA-MM-DD"; mantém pacotes que iniciam em/depois dela
//
// As datas dos pacotes vêm em ISO ("AAAA-MM-DD") do back.

// "2025-01-15" -> MMDD (115). null se não reconhecer.
function isoParaMMDD(iso) {
  const m = (iso || "").match(/^\d{4}-(\d{2})-(\d{2})$/);
  if (!m) return null;
  return Number(m[1]) * 100 + Number(m[2]);
}

function formatarMoeda(valor) {
  return Number(valor).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function lerFiltros() {
  const p = new URLSearchParams(window.location.search);
  return {
    estado: p.get("estado") || "",
    tipo_viagem: p.get("tipo_viagem") || "",
    valor_max: p.get("valor_max") ? Number(p.get("valor_max")) : null,
    data_inicio: p.get("data_inicio") || "",
  };
}

function aplicarFiltros(pacotes, f) {
  return pacotes.filter((pac) => {
    if (f.estado && pac.estado !== f.estado) return false;
    if (f.tipo_viagem && pac.tipo_viagem !== f.tipo_viagem) return false;
    if (f.valor_max != null && pac.preco_base > f.valor_max) return false;
    if (f.data_inicio) {
      const pisoMMDD = isoParaMMDD(f.data_inicio);
      const pacMMDD = isoParaMMDD(pac.data_inicio);
      if (pisoMMDD != null && pacMMDD != null && pacMMDD < pisoMMDD) return false;
    }
    return true;
  });
}

function capitalizarTipo(tipo) {
  if (!tipo) return "—";
  return tipo.charAt(0).toUpperCase() + tipo.slice(1);
}

// Imagem de categoria por tipo de viagem. Tipos com foto usam o arquivo;
// os demais caem num emoji + cor de fundo. Chave normalizada (minúsculas).
const IMAGEM_TIPO = {
  praia: "../imgs/praia.jpg",
  serra: "../imgs/serra.jpg",
  cultural: "../imgs/cultural.jpg",
};
const VISUAL_TIPO = {
  relax: { emoji: "🧘", cor: "#5b8c9e" },
  radical: { emoji: "🪂", cor: "#e76f51" },
};

function visualTipo(tipo) {
  const chave = (tipo || "").toLowerCase();
  const img = IMAGEM_TIPO[chave];
  if (img) {
    return `<div class="pacote-imagem pacote-imagem-foto" aria-hidden="true"
      style="background-image:url('${img}')"></div>`;
  }
  const v = VISUAL_TIPO[chave] || { emoji: "✈️", cor: "#0d3b66" };
  return `<div class="pacote-imagem pacote-imagem-tipo" aria-hidden="true"
    style="background-color:${v.cor}"><span>${v.emoji}</span></div>`;
}

function criarCard(pac, extra = "") {
  const art = document.createElement("article");
  art.className = "pacote-card";
  art.innerHTML = `
    ${visualTipo(pac.tipo_viagem)}
    <div class="pacote-corpo">
      <h2 class="pacote-nome">${pac.cidade} - ${pac.estado}</h2>
      <p class="pacote-tipo">${capitalizarTipo(pac.tipo_viagem)}</p>
      <p class="pacote-preco">${formatarMoeda(pac.preco_base)}</p>
      ${extra}
      <button type="button" class="btn btn-primary w-100"
        data-bs-toggle="modal" data-bs-target="#modal-pacote-${pac.id_pacote}">
        Ver detalhes
      </button>
    </div>`;
  return art;
}

// Mostra os pacotes ordenados por aderência (ranking do AIV, RF7), com os
// selos de aderência e de orçamento. Recebe as preferências pela URL.
async function renderizarRecomendacao(pacotes, params, renderizarPadrao) {
  const grade = document.getElementById("pacotes-grade");
  const modais = document.getElementById("pacotes-modais");
  const vazio = document.getElementById("pacotes-vazio");

  if (!pacotes.length) {
    renderizarPadrao([]);
    return;
  }

  const preferencia = {
    tipo_viagem: params.get("tipo_viagem") || null,
    nivel: params.get("nivel") || null,
    orcamento_max: params.get("orcamento_max") ? Number(params.get("orcamento_max")) : null,
  };
  const candidatos = pacotes.map((p) => ({
    id_pacote: p.id_pacote,
    preco_base: p.preco_base,
    tipo_viagem: p.tipo_viagem,
    nivel: p.nivel ?? null,
    total_avaliacoes: 0,
  }));

  let ranking;
  try {
    ranking = await apiFetch("/recomendacao/ranking", {
      method: "POST",
      body: JSON.stringify({ preferencia, pacotes: candidatos }),
    });
  } catch (erro) {
    // Falha no ranking: cai para a listagem comum.
    renderizarPadrao(pacotes);
    return;
  }

  grade.innerHTML = "";
  modais.innerHTML = "";
  for (const item of ranking) {
    const pac = pacotes.find((p) => p.id_pacote === item.id_pacote);
    if (!pac) continue;
    const selo = item.dentro_do_orcamento
      ? '<span class="rec-selo rec-ok">dentro do orçamento</span>'
      : '<span class="rec-selo rec-fora">acima do orçamento</span>';
    const extra = `<p class="rec-aderencia">Aderência ${Math.round(item.score * 100)}% ${selo}</p>`;
    grade.appendChild(criarCard(pac, extra));
    modais.appendChild(criarModal(pac));
  }
  if (vazio) vazio.hidden = ranking.length > 0;
}

function criarModal(pac) {
  const div = document.createElement("div");
  div.className = "modal fade";
  div.id = `modal-pacote-${pac.id_pacote}`;
  div.tabIndex = -1;
  div.setAttribute("aria-labelledby", `titulo-pacote-${pac.id_pacote}`);
  div.setAttribute("aria-hidden", "true");
  const carrId = `carrossel-pacote-${pac.id_pacote}`;
  div.innerHTML = `
    <div class="modal-dialog modal-lg modal-dialog-centered">
      <div class="modal-content">
        <div class="modal-header">
          <h2 class="modal-title h5" id="titulo-pacote-${pac.id_pacote}">${pac.cidade} - ${pac.estado}</h2>
          <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Fechar"></button>
        </div>
        <div class="modal-body">
          ${visualTipo(pac.tipo_viagem)}
          <dl class="resumo-lista mt-3">
            <div class="resumo-linha"><dt>Tipo</dt><dd>${capitalizarTipo(pac.tipo_viagem)}</dd></div>
            <div class="resumo-linha"><dt>Data inicial</dt><dd>${pac.data_inicio}</dd></div>
            <div class="resumo-linha"><dt>Data final</dt><dd>${pac.data_fim}</dd></div>
            <div class="resumo-linha"><dt>Preço base</dt><dd>${formatarMoeda(pac.preco_base)}</dd></div>
            <div class="resumo-linha"><dt>Vagas</dt><dd>${pac.estoque}</dd></div>
          </dl>
          <p class="pacote-descricao">${pac.descricao || ""}</p>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-primary" data-reservar="${pac.id_pacote}">Reserve já</button>
        </div>
      </div>
    </div>`;

  return div;
}

// Preenche o select de destino com os estados reais existentes nos pacotes.
function preencherEstados(select, pacotes, filtros) {
  if (!select) return;
  const estados = [...new Set(pacotes.map((p) => p.estado))].sort();
  for (const uf of estados) {
    const opt = document.createElement("option");
    opt.value = uf;
    opt.textContent = uf;
    if (uf === filtros.estado) opt.selected = true;
    select.appendChild(opt);
  }
}

// Reflete nos controles o filtro recebido pela URL (para o usuário ver/ajustar).
function sincronizarControles(filtros) {
  const data = document.getElementById("filtro-data-inicio");
  const tipo = document.getElementById("filtro-tipo");
  const valor = document.getElementById("filtro-valor");
  const valorSaida = document.getElementById("filtro-valor-saida");
  if (data && filtros.data_inicio) data.value = filtros.data_inicio;
  if (tipo && filtros.tipo_viagem) tipo.value = filtros.tipo_viagem;
  if (valor) {
    if (filtros.valor_max != null) valor.value = filtros.valor_max;
    if (valorSaida) valorSaida.textContent = formatarMoeda(Number(valor.value));
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  const grade = document.getElementById("pacotes-grade");
  const modais = document.getElementById("pacotes-modais");
  const vazio = document.getElementById("pacotes-vazio");
  if (!grade) return;

  const filtros = lerFiltros();
  sincronizarControles(filtros);

  function renderizar(lista) {
    grade.innerHTML = "";
    modais.innerHTML = "";
    for (const pac of lista) {
      grade.appendChild(criarCard(pac));
      modais.appendChild(criarModal(pac));
    }
    if (vazio) vazio.hidden = lista.length > 0;
  }

  let pacotes = [];
  try {
    const resposta = await apiFetch("/catalogo/pacotes");
    pacotes = resposta.pacotes || [];
  } catch (erro) {
    if (vazio) {
      vazio.textContent = "Não foi possível carregar os pacotes. Tente novamente mais tarde.";
      vazio.hidden = false;
    }
    return;
  }

  preencherEstados(document.getElementById("filtro-estado"), pacotes, filtros);

  // Popula o select de tipo com os tipos reais dos pacotes (dinâmico).
  const selTipo = document.getElementById("filtro-tipo");
  if (selTipo) {
    const tipos = [...new Set(pacotes.map((p) => p.tipo_viagem).filter(Boolean))].sort();
    for (const t of tipos) {
      const opt = document.createElement("option");
      opt.value = t;
      opt.textContent = capitalizarTipo(t);
      if (t === filtros.tipo_viagem) opt.selected = true;
      selTipo.appendChild(opt);
    }
  }

  // Recomendação vinda da home (?recomendar=1): ranqueia por aderência e
  // mostra os selos de aderência/orçamento, em vez da filtragem comum.
  const params = new URLSearchParams(window.location.search);
  if (params.get("recomendar") === "1") {
    await renderizarRecomendacao(pacotes, params, renderizar);
  } else {
    renderizar(aplicarFiltros(pacotes, filtros));
  }

  // Permite refiltrar na própria página de pacotes.
  const form = document.getElementById("form-filtro");
  if (form) {
    const valor = document.getElementById("filtro-valor");
    const valorSaida = document.getElementById("filtro-valor-saida");
    if (valor && valorSaida) {
      valor.addEventListener("input", () => {
        valorSaida.textContent = formatarMoeda(Number(valor.value));
      });
    }
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const f = {
        estado: form.elements["estado"].value,
        tipo_viagem: form.elements["tipo_viagem"].value,
        valor_max: Number(form.elements["valor_max"].value),
        data_inicio: form.elements["data_inicio"].value,
      };
      renderizar(aplicarFiltros(pacotes, f));
    });
  }

  // "Reserve já": guarda o id do pacote escolhido e vai para o carrinho.
  // Delegação de evento porque os modais são gerados dinamicamente.
  document.addEventListener("click", (e) => {
    const botao = e.target.closest("[data-reservar]");
    if (!botao) return;
    const id = Number(botao.getAttribute("data-reservar"));
    localStorage.setItem("pacote_reservado", String(id));
    window.location.href = "carrinho.html";
  });
});
