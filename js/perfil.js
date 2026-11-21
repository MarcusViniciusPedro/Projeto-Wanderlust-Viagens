// Meu perfil (self-service). Usa apiFetch de js/api.js.
//   GET  /auth/me  -> carrega os dados
//   PUT  /auth/me  -> atualização parcial (só campos preenchidos)
//   DELETE /auth/me -> exclui a própria conta
// Logout é só no front: limpa o token do localStorage.

function mostrar(caixa, msg, tipo) {
  caixa.textContent = msg;
  caixa.classList.remove("feedback-erro", "feedback-ok");
  caixa.classList.add(tipo === "ok" ? "feedback-ok" : "feedback-erro");
  caixa.hidden = false;
}

function limparSessao() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("papel");
  localStorage.removeItem("id_turista");
}

document.addEventListener("DOMContentLoaded", async () => {
  const bloqueio = document.getElementById("perfil-bloqueio");
  const conteudo = document.getElementById("perfil-conteudo");

  if (!localStorage.getItem("access_token")) {
    bloqueio.hidden = false;
    conteudo.hidden = true;
    return;
  }

  const form = document.getElementById("form-perfil");
  const feedback = document.getElementById("perfil-feedback");
  const btnSalvar = document.getElementById("btn-salvar-perfil");
  const btnLogout = document.getElementById("btn-logout");
  const btnExcluir = document.getElementById("btn-excluir-perfil");
  const papelEl = document.getElementById("perfil-papel");

  // Carrega os dados atuais do perfil.
  try {
    const me = await apiFetch("/auth/me");
    papelEl.textContent = me.papel || "—";
    form.elements["nome"].value = me.nome || "";
    form.elements["nome_social"].value = me.nome_social || "";
    form.elements["pronome"].value = me.pronome || "";
    form.elements["email"].value = me.email || "";
    form.elements["telefone"].value = me.telefone || "";
    // cep não vem no UsuarioSaida; fica em branco (editável mesmo assim).
    bloqueio.hidden = true;
    conteudo.hidden = false;
  } catch (erro) {
    // Token inválido/expirado (401) ou erro de rede.
    bloqueio.hidden = false;
    conteudo.hidden = true;
    return;
  }

  // Salvar: envia só os campos preenchidos (atualização parcial).
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!form.checkValidity()) {
      form.reportValidity();
      return;
    }
    const dados = {};
    for (const campo of ["nome", "nome_social", "pronome", "email", "telefone", "cep"]) {
      const v = form.elements[campo].value.trim();
      if (v) dados[campo] = v;
    }
    btnSalvar.disabled = true;
    feedback.hidden = true;
    try {
      const atualizado = await apiFetch("/auth/me", {
        method: "PUT",
        body: JSON.stringify(dados),
      });
      papelEl.textContent = atualizado.papel || papelEl.textContent;
      mostrar(feedback, "Perfil atualizado com sucesso.", "ok");
    } catch (erro) {
      mostrar(feedback, erro.message || "Não foi possível salvar as alterações.", "erro");
    } finally {
      btnSalvar.disabled = false;
    }
  });

  // Logout: limpa a sessão e volta para a home.
  btnLogout.addEventListener("click", () => {
    limparSessao();
    window.location.href = "../index.html";
  });

  // Excluir a própria conta.
  btnExcluir.addEventListener("click", async () => {
    if (!confirm("Tem certeza que deseja excluir sua conta? Esta ação é definitiva.")) return;
    btnExcluir.disabled = true;
    feedback.hidden = true;
    try {
      await apiFetch("/auth/me", { method: "DELETE" });
      limparSessao();
      alert("Sua conta foi removida.");
      window.location.href = "../index.html";
    } catch (erro) {
      mostrar(feedback, erro.message || "Não foi possível excluir a conta.", "erro");
      btnExcluir.disabled = false;
    }
  });
});
