// Fluxo de login em duas etapas (2FA) usando o helper apiFetch de js/api.js.
//
// Etapa 1: POST /auth/login {email, senha} -> {desafio_2fa, token_desafio, detalhe}
// Etapa 2: POST /auth/2fa/verificar {token_desafio, codigo} -> {access_token, token_type, papel}
//
// Observacao: /auth/* dependem do banco. Sem SQL Server configurado o backend
// responde HTTP 503 e a mensagem (erro.detail) e exibida ao usuario.

(function () {
  "use strict";

  // Guarda o desafio emitido na etapa 1 para reapresentar na etapa 2.
  let tokenDesafio = null;

  const formLogin = document.getElementById("form-login");
  const form2fa = document.getElementById("form-2fa");
  const caixaMsg = document.getElementById("login-msg");

  // Se a pagina nao tiver o markup esperado, nao faz nada.
  if (!formLogin || !form2fa) {
    return;
  }

  function mostrarMensagem(texto, tipo) {
    if (!caixaMsg) {
      return;
    }
    caixaMsg.textContent = texto;
    caixaMsg.hidden = false;
    caixaMsg.classList.remove("login-msg-erro", "login-msg-sucesso");
    if (tipo === "erro") {
      caixaMsg.classList.add("login-msg-erro");
    } else if (tipo === "sucesso") {
      caixaMsg.classList.add("login-msg-sucesso");
    }
  }

  formLogin.addEventListener("submit", async function (evento) {
    evento.preventDefault();
    const email = document.getElementById("login-email").value.trim();
    const senha = document.getElementById("login-senha").value;

    try {
      const resposta = await apiFetch("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, senha }),
      });
      // Etapa 1 concluida: guarda o desafio e revela a etapa 2.
      tokenDesafio = resposta.token_desafio;
      formLogin.hidden = true;
      form2fa.hidden = false;
      mostrarMensagem(
        resposta.detalhe || "Codigo de verificacao enviado por SMS.",
        "sucesso"
      );
    } catch (erro) {
      mostrarMensagem(erro.message, "erro");
    }
  });

  form2fa.addEventListener("submit", async function (evento) {
    evento.preventDefault();
    const codigo = document.getElementById("login-codigo").value.trim();

    if (!tokenDesafio) {
      mostrarMensagem(
        "Sessao de login expirada. Refaca a etapa 1.",
        "erro"
      );
      return;
    }

    try {
      const resposta = await apiFetch("/auth/2fa/verificar", {
        method: "POST",
        body: JSON.stringify({ token_desafio: tokenDesafio, codigo }),
      });
      // Etapa 2 concluida: persiste o token para o apiFetch reutilizar.
      localStorage.setItem("access_token", resposta.access_token);
      if (resposta.papel) {
        localStorage.setItem("papel", resposta.papel);
      }
      mostrarMensagem(
        `Login realizado com sucesso. Logado como ${resposta.papel}.`,
        "sucesso"
      );
      // Redireciona para a home apos um curto intervalo.
      setTimeout(function () {
        window.location.href = "../index.html";
      }, 1200);
    } catch (erro) {
      mostrarMensagem(erro.message, "erro");
    }
  });
})();
