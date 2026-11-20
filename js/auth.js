// Cadastro de usuário (RF1): envia o formulário para POST /auth/cadastro.
// Usa apiFetch() definido em js/api.js.

function cadastrarUsuario(dados) {
  return apiFetch("/auth/cadastro", {
    method: "POST",
    body: JSON.stringify(dados),
  });
}

// Lê os campos do formulário e monta o corpo esperado pela API.
// Campos opcionais em branco são omitidos (o back-end aceita ausência).
function coletarDadosCadastro(form) {
  const valor = (nome) => form.elements[nome].value.trim();

  const dados = {
    nome: valor("nome"),
    data_nascimento: valor("data_nascimento"), // formato YYYY-MM-DD (input date)
    cpf: valor("cpf"),
    email: valor("email"),
    senha: form.elements["senha"].value,
  };

  for (const opcional of ["nome_social", "pronome", "cep", "telefone"]) {
    const v = valor(opcional);
    if (v) dados[opcional] = v;
  }

  return dados;
}

function mostrarFeedback(caixa, mensagem, tipo) {
  caixa.textContent = mensagem;
  caixa.classList.remove("feedback-erro", "feedback-ok");
  caixa.classList.add(tipo === "ok" ? "feedback-ok" : "feedback-erro");
  caixa.hidden = false;
}

// Login em duas etapas (RF2):
//   Etapa 1 -> POST /auth/login devolve um token_desafio.
//   Etapa 2 -> POST /auth/2fa/verificar troca token_desafio + código pelo JWT.
function iniciarLogin(email, senha) {
  return apiFetch("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, senha }),
  });
}

function verificar2fa(tokenDesafio, codigo) {
  return apiFetch("/auth/2fa/verificar", {
    method: "POST",
    body: JSON.stringify({ token_desafio: tokenDesafio, codigo }),
  });
}

function inicializarCadastro() {
  const form = document.getElementById("form-cadastro");
  if (!form) return;

  const feedback = document.getElementById("cadastro-feedback");
  const botao = document.getElementById("btn-cadastrar");

  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();

    if (!form.checkValidity()) {
      form.reportValidity();
      return;
    }

    botao.disabled = true;
    feedback.hidden = true;

    try {
      const usuario = await cadastrarUsuario(coletarDadosCadastro(form));
      const nome = usuario.nome_social || usuario.nome || "";
      mostrarFeedback(
        feedback,
        `Cadastro concluído com sucesso${nome ? `, ${nome}` : ""}! Redirecionando para o login...`,
        "ok"
      );
      form.reset();
      setTimeout(() => {
        window.location.href = "login.html";
      }, 1500);
    } catch (erro) {
      mostrarFeedback(
        feedback,
        erro.message || "Não foi possível concluir o cadastro. Tente novamente.",
        "erro"
      );
      botao.disabled = false;
    }
  });
}

function inicializarLogin() {
  const formLogin = document.getElementById("form-login");
  if (!formLogin) return;

  const form2fa = document.getElementById("form-2fa");
  const feedback = document.getElementById("login-feedback");
  const btnLogin = document.getElementById("btn-login");
  const btn2fa = document.getElementById("btn-2fa");
  const voltar = document.getElementById("voltar-login");

  let tokenDesafio = null;

  formLogin.addEventListener("submit", async (evento) => {
    evento.preventDefault();

    if (!formLogin.checkValidity()) {
      formLogin.reportValidity();
      return;
    }

    btnLogin.disabled = true;
    feedback.hidden = true;

    try {
      const email = formLogin.elements["email"].value.trim();
      const senha = formLogin.elements["senha"].value;
      const resposta = await iniciarLogin(email, senha);
      tokenDesafio = resposta.token_desafio;

      formLogin.hidden = true;
      form2fa.hidden = false;
      mostrarFeedback(
        feedback,
        resposta.detalhe || "Código de verificação enviado por SMS.",
        "ok"
      );
      form2fa.elements["codigo"].focus();
    } catch (erro) {
      mostrarFeedback(
        feedback,
        erro.message || "Não foi possível entrar. Verifique seus dados.",
        "erro"
      );
    } finally {
      btnLogin.disabled = false;
    }
  });

  form2fa.addEventListener("submit", async (evento) => {
    evento.preventDefault();

    if (!form2fa.checkValidity()) {
      form2fa.reportValidity();
      return;
    }

    btn2fa.disabled = true;
    feedback.hidden = true;

    try {
      const codigo = form2fa.elements["codigo"].value.trim();
      const resposta = await verificar2fa(tokenDesafio, codigo);
      localStorage.setItem("access_token", resposta.access_token);
      if (resposta.papel) localStorage.setItem("papel", resposta.papel);
      // id do turista logado, usado como fk_conta_turista ao registrar a venda.
      if (resposta.id_passageiro != null) {
        localStorage.setItem("id_turista", String(resposta.id_passageiro));
      }

      mostrarFeedback(feedback, "Login concluído! Redirecionando...", "ok");
      setTimeout(() => {
        window.location.href = "../index.html";
      }, 1200);
    } catch (erro) {
      mostrarFeedback(
        feedback,
        erro.message || "Código inválido. Tente novamente.",
        "erro"
      );
      btn2fa.disabled = false;
    }
  });

  voltar.addEventListener("click", (evento) => {
    evento.preventDefault();
    tokenDesafio = null;
    form2fa.hidden = true;
    form2fa.reset();
    formLogin.hidden = false;
    feedback.hidden = true;
    formLogin.elements["email"].focus();
  });
}

document.addEventListener("DOMContentLoaded", () => {
  inicializarCadastro();
  inicializarLogin();
});
