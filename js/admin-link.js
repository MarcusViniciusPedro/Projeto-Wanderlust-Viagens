// Revela o acesso ao painel do Administrador (ícone de cadeado) no menu,
// apenas quando o usuário logado tem papel "Administrador". Para os demais,
// nada é exibido — o painel fica "escondido" atrás do cadeado.
//
// Observação: isto é só UX de exibição. A barreira real é o back-end, que
// rejeita (401/403) qualquer chamada às rotas de admin sem token/permissão.

document.addEventListener("DOMContentLoaded", () => {
  const papel = localStorage.getItem("papel");
  const logado = !!localStorage.getItem("access_token");
  if (!logado || papel !== "Administrador") return;

  const menu = document.querySelector(".menu-lista");
  if (!menu) return;

  // Caminho para admin.html relativo à página atual.
  const emPages = window.location.pathname.includes("/pages/");
  const href = emPages ? "admin.html" : "pages/admin.html";
  const iconHref = emPages ? "../imgs/cadeado.svg" : "imgs/cadeado.svg";

  const li = document.createElement("li");
  li.className = "nav-item";
  li.innerHTML =
    `<a class="nav-link admin-link-cadeado" href="${href}" title="Painel do administrador">` +
    `<img src="${iconHref}" alt="Administração"></a>`;
  menu.appendChild(li);
});
