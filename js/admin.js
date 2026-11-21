// Painel do Administrador: CRUD de pacotes e RUD de contas.
// Protegido por papel no FRONT (exibição) e no BACK (toda rota admin exige
// Bearer JWT com permissão; 401/403 se não for admin). Usa apiFetch de api.js.

function formatarMoeda(v) {
  return Number(v).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function mostrar(caixa, msg, tipo) {
  caixa.textContent = msg;
  caixa.classList.remove("feedback-erro", "feedback-ok");
  caixa.classList.add(tipo === "ok" ? "feedback-ok" : "feedback-erro");
  caixa.hidden = false;
}

function escapar(texto) {
  const div = document.createElement("div");
  div.textContent = texto ?? "";
  return div.innerHTML;
}

// ---------- API ----------
const listarPacotes = () => apiFetch("/catalogo/pacotes");
const listarDestinos = () => apiFetch("/catalogo/destinos");
const criarPacote = (d) => apiFetch("/catalogo/pacotes", { method: "POST", body: JSON.stringify(d) });
const atualizarPacote = (id, d) => apiFetch(`/catalogo/pacotes/${id}`, { method: "PUT", body: JSON.stringify(d) });
const excluirPacote = (id) => apiFetch(`/catalogo/pacotes/${id}`, { method: "DELETE" });

const criarDestino = (d) => apiFetch("/catalogo/destinos", { method: "POST", body: JSON.stringify(d) });
const atualizarDestino = (id, d) => apiFetch(`/catalogo/destinos/${id}`, { method: "PUT", body: JSON.stringify(d) });
const excluirDestino = (id) => apiFetch(`/catalogo/destinos/${id}`, { method: "DELETE" });

const listarHospedagens = () => apiFetch("/catalogo/hospedagens");
const criarHospedagem = (d) => apiFetch("/catalogo/hospedagens", { method: "POST", body: JSON.stringify(d) });
const atualizarHospedagem = (id, d) => apiFetch(`/catalogo/hospedagens/${id}`, { method: "PUT", body: JSON.stringify(d) });
const excluirHospedagem = (id) => apiFetch(`/catalogo/hospedagens/${id}`, { method: "DELETE" });

const listarContas = () => apiFetch("/auth/admin/contas");
const alterarStatusConta = (id, novo_status, motivo) =>
  apiFetch(`/auth/admin/contas/${id}/status`, { method: "PATCH", body: JSON.stringify({ novo_status, motivo }) });
const excluirConta = (id) => apiFetch(`/auth/admin/contas/${id}`, { method: "DELETE" });

document.addEventListener("DOMContentLoaded", () => {
  const bloqueio = document.getElementById("admin-bloqueio");
  const painel = document.getElementById("admin-painel");

  // Gate de exibição: só mostra o painel se o papel salvo for Administrador.
  // (O back é a barreira real: as rotas rejeitam quem não for admin.)
  const logado = !!localStorage.getItem("access_token");
  const papel = localStorage.getItem("papel");
  const ehAdmin = logado && papel === "Administrador";

  if (!ehAdmin) {
    if (logado) {
      document.getElementById("admin-bloqueio-msg").textContent =
        "Sua conta não tem permissão de administrador.";
    }
    bloqueio.hidden = false;
    painel.hidden = true;
    return;
  }

  bloqueio.hidden = true;
  painel.hidden = false;

  // ======================= PACOTES =======================
  const formPacote = document.getElementById("form-pacote");
  const pacoteFeedback = document.getElementById("pacote-feedback");
  const tabelaPacotes = document.getElementById("tabela-pacotes");
  const btnSalvar = document.getElementById("btn-salvar-pacote");
  const btnCancelar = document.getElementById("btn-cancelar-pacote");
  const campoId = document.getElementById("pacote-id");
  const selectDestino = document.getElementById("pacote-destino");
  const selectTipoPac = document.getElementById("pacote-tipo");
  const inputTipoNovo = document.getElementById("pacote-tipo-novo");

  // Mostra o campo de texto quando o admin escolhe "Outro (novo tipo)".
  selectTipoPac.addEventListener("change", () => {
    const novo = selectTipoPac.value === "__novo__";
    inputTipoNovo.hidden = !novo;
    if (novo) inputTipoNovo.focus();
  });

  // Tipo escolhido: texto digitado quando "Outro", senão o valor do select.
  function tipoEscolhido() {
    if (selectTipoPac.value === "__novo__") {
      return inputTipoNovo.value.trim() || null;
    }
    return selectTipoPac.value || null;
  }

  // Popula o select com os tipos já existentes nos pacotes (antes de "Outro").
  function popularTiposExistentes(pacotes) {
    const tipos = [...new Set(pacotes.map((p) => p.tipo_viagem).filter(Boolean))].sort();
    const atual = selectTipoPac.value;
    // Remove opções dinâmicas antigas (mantém "—" e "Outro").
    [...selectTipoPac.options].forEach((o) => {
      if (o.value && o.value !== "__novo__") o.remove();
    });
    const optNovo = selectTipoPac.querySelector('option[value="__novo__"]');
    for (const t of tipos) {
      const opt = document.createElement("option");
      opt.value = t;
      opt.textContent = t.charAt(0).toUpperCase() + t.slice(1);
      selectTipoPac.insertBefore(opt, optNovo);
    }
    if (atual) selectTipoPac.value = atual;
  }

  async function carregarDestinos() {
    try {
      const destinos = await listarDestinos();
      for (const d of destinos) {
        const opt = document.createElement("option");
        opt.value = d.id_destino;
        opt.textContent = `${d.cidade} - ${d.estado}`;
        selectDestino.appendChild(opt);
      }
    } catch (erro) {
      mostrar(pacoteFeedback, erro.message || "Não foi possível carregar os destinos.", "erro");
    }
  }

  function entrarModoEdicao(p) {
    campoId.value = p.id_pacote;
    formPacote.elements["preco_base"].value = p.preco_base;
    formPacote.elements["estoque"].value = p.estoque;
    // Tipo: como os tipos existentes já estão no select, basta selecionar.
    selectTipoPac.value = p.tipo_viagem || "";
    inputTipoNovo.hidden = true;
    inputTipoNovo.value = "";
    formPacote.elements["nivel"].value = p.nivel || "";
    formPacote.elements["data_inicio"].value = p.data_inicio;
    formPacote.elements["data_fim"].value = p.data_fim;
    formPacote.elements["fk_destino"].value = p.fk_destino;
    btnSalvar.textContent = "Salvar alterações";
    btnCancelar.hidden = false;
    formPacote.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function sairModoEdicao() {
    formPacote.reset();
    campoId.value = "";
    inputTipoNovo.hidden = true;
    inputTipoNovo.value = "";
    btnSalvar.textContent = "Adicionar pacote";
    btnCancelar.hidden = true;
  }

  async function carregarPacotes() {
    try {
      const res = await listarPacotes();
      const pacotes = res.pacotes || [];
      popularTiposExistentes(pacotes);
      tabelaPacotes.innerHTML = pacotes
        .map(
          (p) => `<tr>
            <td>${p.id_pacote}</td>
            <td>${formatarMoeda(p.preco_base)}</td>
            <td>${p.data_inicio} a ${p.data_fim}</td>
            <td>${p.estoque}</td>
            <td>${escapar(p.tipo_viagem) || "—"}</td>
            <td>${escapar(p.nivel) || "—"}</td>
            <td class="text-nowrap">
              <button class="btn btn-sm btn-outline-primary" data-editar='${JSON.stringify(p)}'>Editar</button>
              <button class="btn btn-sm btn-outline-danger" data-excluir-pacote="${p.id_pacote}">Excluir</button>
            </td>
          </tr>`
        )
        .join("");
      if (!pacotes.length) {
        tabelaPacotes.innerHTML = `<tr><td colspan="7" class="text-center text-muted">Nenhum pacote cadastrado.</td></tr>`;
      }
    } catch (erro) {
      mostrar(pacoteFeedback, erro.message || "Não foi possível carregar os pacotes.", "erro");
    }
  }

  formPacote.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!formPacote.checkValidity()) {
      formPacote.reportValidity();
      return;
    }
    const dados = {
      preco_base: Number(formPacote.elements["preco_base"].value),
      estoque: Number(formPacote.elements["estoque"].value),
      data_inicio: formPacote.elements["data_inicio"].value,
      data_fim: formPacote.elements["data_fim"].value,
      tipo_viagem: tipoEscolhido(),
      nivel: formPacote.elements["nivel"].value || null,
      fk_destino: Number(formPacote.elements["fk_destino"].value),
    };
    if (dados.data_fim < dados.data_inicio) {
      mostrar(pacoteFeedback, "A data final não pode ser anterior à inicial.", "erro");
      return;
    }
    btnSalvar.disabled = true;
    pacoteFeedback.hidden = true;
    try {
      const id = campoId.value;
      if (id) {
        await atualizarPacote(id, dados);
        mostrar(pacoteFeedback, `Pacote ${id} atualizado.`, "ok");
      } else {
        const novo = await criarPacote(dados);
        mostrar(pacoteFeedback, `Pacote ${novo.id_pacote} criado.`, "ok");
      }
      sairModoEdicao();
      carregarPacotes();
      recarregarSelectPacotes(); // hospedagem reflete o novo pacote
    } catch (erro) {
      mostrar(pacoteFeedback, erro.message || "Não foi possível salvar o pacote.", "erro");
    } finally {
      btnSalvar.disabled = false;
    }
  });

  btnCancelar.addEventListener("click", sairModoEdicao);

  tabelaPacotes.addEventListener("click", async (e) => {
    const bEditar = e.target.closest("[data-editar]");
    const bExcluir = e.target.closest("[data-excluir-pacote]");
    if (bEditar) {
      entrarModoEdicao(JSON.parse(bEditar.getAttribute("data-editar")));
    } else if (bExcluir) {
      const id = bExcluir.getAttribute("data-excluir-pacote");
      if (!confirm(`Excluir o pacote ${id}? Esta ação não pode ser desfeita.`)) return;
      try {
        await excluirPacote(id);
        mostrar(pacoteFeedback, `Pacote ${id} excluído.`, "ok");
        carregarPacotes();
        recarregarSelectPacotes();
      } catch (erro) {
        mostrar(pacoteFeedback, erro.message || "Não foi possível excluir o pacote.", "erro");
      }
    }
  });

  // ======================= CONTAS =======================
  const contaFeedback = document.getElementById("conta-feedback");
  const tabelaContas = document.getElementById("tabela-contas");

  function acoesConta(c) {
    const botoes = [];
    if (c.status !== "Banido") {
      botoes.push(`<button class="btn btn-sm btn-outline-warning" data-banir="${c.id_passageiro}">Banir</button>`);
    }
    if (c.status !== "Ativo") {
      botoes.push(`<button class="btn btn-sm btn-outline-success" data-reativar="${c.id_passageiro}">Reativar</button>`);
    }
    botoes.push(`<button class="btn btn-sm btn-outline-danger" data-excluir-conta="${c.id_passageiro}">Excluir</button>`);
    return botoes.join(" ");
  }

  async function carregarContas() {
    try {
      const contas = await listarContas();
      tabelaContas.innerHTML = contas
        .map(
          (c) => `<tr>
            <td>${c.id_passageiro}</td>
            <td>${escapar(c.nome)}</td>
            <td>${escapar(c.email) || "—"}</td>
            <td>${escapar(c.papel)}</td>
            <td>${escapar(c.status)}</td>
            <td class="text-nowrap">${acoesConta(c)}</td>
          </tr>`
        )
        .join("");
      if (!contas.length) {
        tabelaContas.innerHTML = `<tr><td colspan="6" class="text-center text-muted">Nenhuma conta encontrada.</td></tr>`;
      }
    } catch (erro) {
      mostrar(contaFeedback, erro.message || "Não foi possível carregar as contas.", "erro");
    }
  }

  tabelaContas.addEventListener("click", async (e) => {
    const banir = e.target.closest("[data-banir]");
    const reativar = e.target.closest("[data-reativar]");
    const excluir = e.target.closest("[data-excluir-conta]");
    try {
      if (banir) {
        const id = banir.getAttribute("data-banir");
        const motivo = prompt("Motivo do banimento (opcional):") || null;
        await alterarStatusConta(id, "Banido", motivo);
        mostrar(contaFeedback, `Conta ${id} banida.`, "ok");
        carregarContas();
      } else if (reativar) {
        const id = reativar.getAttribute("data-reativar");
        await alterarStatusConta(id, "Ativo", null);
        mostrar(contaFeedback, `Conta ${id} reativada.`, "ok");
        carregarContas();
      } else if (excluir) {
        const id = excluir.getAttribute("data-excluir-conta");
        if (!confirm(`Excluir a conta ${id}? Esta ação não pode ser desfeita.`)) return;
        await excluirConta(id);
        mostrar(contaFeedback, `Conta ${id} excluída.`, "ok");
        carregarContas();
      }
    } catch (erro) {
      mostrar(contaFeedback, erro.message || "Não foi possível concluir a operação.", "erro");
    }
  });

  // ======================= DESTINOS =======================
  const formDestino = document.getElementById("form-destino");
  const destinoFeedback = document.getElementById("destino-feedback");
  const tabelaDestinos = document.getElementById("tabela-destinos");
  const btnSalvarDestino = document.getElementById("btn-salvar-destino");
  const btnCancelarDestino = document.getElementById("btn-cancelar-destino");
  const destinoId = document.getElementById("destino-id");

  function sairEdicaoDestino() {
    formDestino.reset();
    destinoId.value = "";
    btnSalvarDestino.textContent = "Adicionar destino";
    btnCancelarDestino.hidden = true;
  }

  async function carregarDestinosTabela() {
    try {
      const destinos = await listarDestinos();
      tabelaDestinos.innerHTML = destinos
        .map(
          (d) => `<tr>
            <td>${d.id_destino}</td>
            <td>${escapar(d.cidade)}</td>
            <td>${escapar(d.estado)}</td>
            <td>${escapar(d.pais)}</td>
            <td>${escapar(d.categoria) || "—"}</td>
            <td class="text-nowrap">
              <button class="btn btn-sm btn-outline-primary" data-editar-destino='${JSON.stringify(d)}'>Editar</button>
              <button class="btn btn-sm btn-outline-danger" data-excluir-destino="${d.id_destino}">Excluir</button>
            </td>
          </tr>`
        )
        .join("");
      if (!destinos.length) {
        tabelaDestinos.innerHTML = `<tr><td colspan="6" class="text-center text-muted">Nenhum destino cadastrado.</td></tr>`;
      }
    } catch (erro) {
      mostrar(destinoFeedback, erro.message || "Não foi possível carregar os destinos.", "erro");
    }
  }

  formDestino.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!formDestino.checkValidity()) {
      formDestino.reportValidity();
      return;
    }
    const dados = {
      cidade: formDestino.elements["cidade"].value.trim(),
      estado: formDestino.elements["estado"].value.trim(),
      pais: formDestino.elements["pais"].value.trim(),
      categoria: formDestino.elements["categoria"].value.trim() || null,
      descricao: formDestino.elements["descricao"].value.trim() || null,
    };
    btnSalvarDestino.disabled = true;
    destinoFeedback.hidden = true;
    try {
      const id = destinoId.value;
      if (id) {
        await atualizarDestino(id, dados);
        mostrar(destinoFeedback, `Destino ${id} atualizado.`, "ok");
      } else {
        const novo = await criarDestino(dados);
        mostrar(destinoFeedback, `Destino ${novo.id_destino} criado.`, "ok");
      }
      sairEdicaoDestino();
      carregarDestinosTabela();
      recarregarSelectDestinos(); // o select de pacote reflete o novo destino
    } catch (erro) {
      mostrar(destinoFeedback, erro.message || "Não foi possível salvar o destino.", "erro");
    } finally {
      btnSalvarDestino.disabled = false;
    }
  });

  btnCancelarDestino.addEventListener("click", sairEdicaoDestino);

  tabelaDestinos.addEventListener("click", async (e) => {
    const bEditar = e.target.closest("[data-editar-destino]");
    const bExcluir = e.target.closest("[data-excluir-destino]");
    if (bEditar) {
      const d = JSON.parse(bEditar.getAttribute("data-editar-destino"));
      destinoId.value = d.id_destino;
      formDestino.elements["cidade"].value = d.cidade;
      formDestino.elements["estado"].value = d.estado;
      formDestino.elements["pais"].value = d.pais;
      formDestino.elements["categoria"].value = d.categoria || "";
      formDestino.elements["descricao"].value = d.descricao || "";
      btnSalvarDestino.textContent = "Salvar alterações";
      btnCancelarDestino.hidden = false;
      formDestino.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } else if (bExcluir) {
      const id = bExcluir.getAttribute("data-excluir-destino");
      if (!confirm(`Excluir o destino ${id}? Pacotes que o usam podem impedir a exclusão.`)) return;
      try {
        await excluirDestino(id);
        mostrar(destinoFeedback, `Destino ${id} excluído.`, "ok");
        carregarDestinosTabela();
        recarregarSelectDestinos();
      } catch (erro) {
        mostrar(destinoFeedback, erro.message || "Não foi possível excluir o destino.", "erro");
      }
    }
  });

  // Repopula o select de destino do formulário de pacote.
  async function recarregarSelectDestinos() {
    try {
      const destinos = await listarDestinos();
      const atual = selectDestino.value;
      selectDestino.innerHTML = "";
      for (const d of destinos) {
        const opt = document.createElement("option");
        opt.value = d.id_destino;
        opt.textContent = `${d.cidade} - ${d.estado}`;
        selectDestino.appendChild(opt);
      }
      if (atual) selectDestino.value = atual;
    } catch (erro) {
      /* silencioso: a tabela de destinos já reporta erros */
    }
  }

  // ======================= HOSPEDAGENS =======================
  const formHospedagem = document.getElementById("form-hospedagem");
  const hospedagemFeedback = document.getElementById("hospedagem-feedback");
  const tabelaHospedagens = document.getElementById("tabela-hospedagens");
  const btnSalvarHospedagem = document.getElementById("btn-salvar-hospedagem");
  const btnCancelarHospedagem = document.getElementById("btn-cancelar-hospedagem");
  const hospedagemId = document.getElementById("hospedagem-id");
  const selectPacoteHosp = document.getElementById("hospedagem-pacote");

  function sairEdicaoHospedagem() {
    formHospedagem.reset();
    hospedagemId.value = "";
    btnSalvarHospedagem.textContent = "Adicionar hospedagem";
    btnCancelarHospedagem.hidden = true;
  }

  // Popula o select de pacotes da hospedagem.
  async function recarregarSelectPacotes() {
    try {
      const res = await listarPacotes();
      const pacotes = res.pacotes || [];
      const atual = selectPacoteHosp.value;
      selectPacoteHosp.innerHTML = "";
      for (const p of pacotes) {
        const opt = document.createElement("option");
        opt.value = p.id_pacote;
        const local = p.cidade ? `${p.cidade} - ${p.estado}` : `Pacote ${p.id_pacote}`;
        opt.textContent = `#${p.id_pacote} · ${local}`;
        selectPacoteHosp.appendChild(opt);
      }
      if (atual) selectPacoteHosp.value = atual;
    } catch (erro) {
      mostrar(hospedagemFeedback, erro.message || "Não foi possível carregar os pacotes.", "erro");
    }
  }

  async function carregarHospedagens() {
    try {
      const hosps = await listarHospedagens();
      tabelaHospedagens.innerHTML = hosps
        .map(
          (h) => `<tr>
            <td>${h.id_hospedagem}</td>
            <td>${escapar(h.nome)}</td>
            <td>#${h.fk_Pacote_id_pacote}</td>
            <td>${escapar(h.rua)}, ${h.numero} (${escapar(h.cep)})</td>
            <td>${escapar(h.tipo_quarto) || "—"}</td>
            <td>${escapar(h.regime_alimentacao) || "—"}</td>
            <td class="text-nowrap">
              <button class="btn btn-sm btn-outline-primary" data-editar-hospedagem='${JSON.stringify(h)}'>Editar</button>
              <button class="btn btn-sm btn-outline-danger" data-excluir-hospedagem="${h.id_hospedagem}">Excluir</button>
            </td>
          </tr>`
        )
        .join("");
      if (!hosps.length) {
        tabelaHospedagens.innerHTML = `<tr><td colspan="7" class="text-center text-muted">Nenhuma hospedagem cadastrada.</td></tr>`;
      }
    } catch (erro) {
      mostrar(hospedagemFeedback, erro.message || "Não foi possível carregar as hospedagens.", "erro");
    }
  }

  formHospedagem.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!formHospedagem.checkValidity()) {
      formHospedagem.reportValidity();
      return;
    }
    const dados = {
      fk_Pacote_id_pacote: Number(selectPacoteHosp.value),
      nome: formHospedagem.elements["nome"].value.trim(),
      rua: formHospedagem.elements["rua"].value.trim(),
      numero: Number(formHospedagem.elements["numero"].value),
      cep: formHospedagem.elements["cep"].value.trim(),
      tipo_quarto: formHospedagem.elements["tipo_quarto"].value.trim() || null,
      regime_alimentacao: formHospedagem.elements["regime_alimentacao"].value.trim() || null,
    };
    btnSalvarHospedagem.disabled = true;
    hospedagemFeedback.hidden = true;
    try {
      const id = hospedagemId.value;
      if (id) {
        await atualizarHospedagem(id, dados);
        mostrar(hospedagemFeedback, `Hospedagem ${id} atualizada.`, "ok");
      } else {
        const nova = await criarHospedagem(dados);
        mostrar(hospedagemFeedback, `Hospedagem ${nova.id_hospedagem} criada.`, "ok");
      }
      sairEdicaoHospedagem();
      carregarHospedagens();
    } catch (erro) {
      mostrar(hospedagemFeedback, erro.message || "Não foi possível salvar a hospedagem.", "erro");
    } finally {
      btnSalvarHospedagem.disabled = false;
    }
  });

  btnCancelarHospedagem.addEventListener("click", sairEdicaoHospedagem);

  tabelaHospedagens.addEventListener("click", async (e) => {
    const bEditar = e.target.closest("[data-editar-hospedagem]");
    const bExcluir = e.target.closest("[data-excluir-hospedagem]");
    if (bEditar) {
      const h = JSON.parse(bEditar.getAttribute("data-editar-hospedagem"));
      hospedagemId.value = h.id_hospedagem;
      selectPacoteHosp.value = h.fk_Pacote_id_pacote;
      formHospedagem.elements["nome"].value = h.nome;
      formHospedagem.elements["rua"].value = h.rua;
      formHospedagem.elements["numero"].value = h.numero;
      formHospedagem.elements["cep"].value = h.cep;
      formHospedagem.elements["tipo_quarto"].value = h.tipo_quarto || "";
      formHospedagem.elements["regime_alimentacao"].value = h.regime_alimentacao || "";
      btnSalvarHospedagem.textContent = "Salvar alterações";
      btnCancelarHospedagem.hidden = false;
      formHospedagem.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } else if (bExcluir) {
      const id = bExcluir.getAttribute("data-excluir-hospedagem");
      if (!confirm(`Excluir a hospedagem ${id}?`)) return;
      try {
        await excluirHospedagem(id);
        mostrar(hospedagemFeedback, `Hospedagem ${id} excluída.`, "ok");
        carregarHospedagens();
      } catch (erro) {
        mostrar(hospedagemFeedback, erro.message || "Não foi possível excluir a hospedagem.", "erro");
      }
    }
  });

  // ======================= ESTATÍSTICAS (RF10) =======================
  const formEstat = document.getElementById("form-estatisticas");
  const estatFeedback = document.getElementById("estat-feedback");
  const tabelaEstat = document.getElementById("tabela-estatisticas");
  const campoAno = document.getElementById("estat-ano");
  if (campoAno) campoAno.value = new Date().getFullYear();

  async function carregarEstatisticas(ano) {
    try {
      // Retorno: { "destino": [12 contagens jan..dez] }
      const dados = await apiFetch(`/estatisticas/turistas-por-destino?ano=${ano}`);
      const destinos = Object.keys(dados);
      if (!destinos.length) {
        tabelaEstat.innerHTML =
          `<tr><td colspan="14" class="text-center text-muted">Nenhum dado para ${ano}.</td></tr>`;
        return;
      }
      tabelaEstat.innerHTML = destinos
        .map((nome) => {
          const meses = dados[nome] || [];
          const celulas = Array.from({ length: 12 }, (_, i) => `<td>${meses[i] ?? 0}</td>`).join("");
          const total = meses.reduce((a, b) => a + (b || 0), 0);
          return `<tr><td>${escapar(nome)}</td>${celulas}<td><strong>${total}</strong></td></tr>`;
        })
        .join("");
    } catch (erro) {
      mostrar(estatFeedback, erro.message || "Não foi possível carregar as estatísticas.", "erro");
    }
  }

  if (formEstat) {
    formEstat.addEventListener("submit", (e) => {
      e.preventDefault();
      estatFeedback.hidden = true;
      carregarEstatisticas(Number(campoAno.value) || new Date().getFullYear());
    });
  }

  // Carga inicial.
  carregarDestinos();
  carregarPacotes();
  carregarDestinosTabela();
  recarregarSelectPacotes();
  carregarHospedagens();
  carregarContas();
  carregarEstatisticas(new Date().getFullYear());
});
