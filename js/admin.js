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
const criarPacote = (d) => apiFetch("/catalogo/pacotes", { method: "POST", body: JSON.stringify(d) });
const atualizarPacote = (id, d) => apiFetch(`/catalogo/pacotes/${id}`, { method: "PUT", body: JSON.stringify(d) });
const excluirPacote = (id) => apiFetch(`/catalogo/pacotes/${id}`, { method: "DELETE" });

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

  function entrarModoEdicao(p) {
    campoId.value = p.id_pacote;
    formPacote.elements["preco_base"].value = p.preco_base;
    formPacote.elements["estoque"].value = p.estoque;
    formPacote.elements["tipo_viagem"].value = p.tipo_viagem || "";
    formPacote.elements["nivel"].value = p.nivel || "";
    formPacote.elements["data_inicio"].value = p.data_inicio;
    formPacote.elements["data_fim"].value = p.data_fim;
    btnSalvar.textContent = "Salvar alterações";
    btnCancelar.hidden = false;
    formPacote.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function sairModoEdicao() {
    formPacote.reset();
    campoId.value = "";
    btnSalvar.textContent = "Adicionar pacote";
    btnCancelar.hidden = true;
  }

  async function carregarPacotes() {
    try {
      const res = await listarPacotes();
      const pacotes = res.pacotes || [];
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
      tipo_viagem: formPacote.elements["tipo_viagem"].value || null,
      nivel: formPacote.elements["nivel"].value || null,
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

  // Carga inicial.
  carregarPacotes();
  carregarContas();
});
