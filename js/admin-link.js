// Revela o acesso ao painel do Administrador (ícone de cadeado) no menu,
// apenas quando o usuário logado tem papel "Administrador". Para os demais,
// nada é exibido — o painel fica "escondido" atrás do cadeado.
//
// Observação: isto é só UX de exibição. A barreira real é o back-end, que
// rejeita (401/403) qualquer chamada às rotas de admin sem token/permissão.

// Ajusta o menu conforme a sessão: quando logado, mostra "Meu perfil" e
// "Sair" e oculta "Login"/"Cadastre-se"; se for Administrador, revela o
// cadeado do painel de admin. Logout limpa o token no front.
//
// Observação: isto é só UX de exibição. A barreira real é o back-end, que
// rejeita (401/403) qualquer chamada protegida sem token/permissão.

document.addEventListener("DOMContentLoaded", () => {
  const menu = document.querySelector(".menu-lista");
  if (!menu) return;

  const logado = !!localStorage.getItem("access_token");
  const papel = localStorage.getItem("papel");
  const emPages = window.location.pathname.includes("/pages/");
  const p = (arquivo) => (emPages ? arquivo : `pages/${arquivo}`);

  if (!logado) return; // visitante: menu padrão (Login/Cadastre-se visíveis).

  // Oculta Login e Cadastre-se para quem já está logado.
  menu.querySelectorAll('a.nav-link').forEach((a) => {
    const href = a.getAttribute("href") || "";
    if (href.endsWith("login.html") || href.endsWith("cadastro.html")) {
      a.closest("li")?.remove();
    }
  });

  // "Meu perfil".
  const liPerfil = document.createElement("li");
  liPerfil.className = "nav-item";
  liPerfil.innerHTML = `<a class="nav-link" href="${p("perfil.html")}">Meu perfil</a>`;
  menu.appendChild(liPerfil);

  // Cadeado do admin (só para Administrador).
  if (papel === "Administrador") {
    const iconHref = emPages ? "../imgs/cadeado.svg" : "imgs/cadeado.svg";
    const liAdmin = document.createElement("li");
    liAdmin.className = "nav-item";
    liAdmin.innerHTML =
      `<a class="nav-link admin-link-cadeado" href="${p("admin.html")}" title="Painel do administrador">` +
      `<img src="${iconHref}" alt="Administração"></a>`;
    menu.appendChild(liAdmin);
  }

  // "Sair" (logout no front).
  const liSair = document.createElement("li");
  liSair.className = "nav-item";
  liSair.innerHTML = `<a class="nav-link" href="#" id="menu-logout">Sair</a>`;
  menu.appendChild(liSair);
  liSair.querySelector("#menu-logout").addEventListener("click", (e) => {
    e.preventDefault();
    localStorage.removeItem("access_token");
    localStorage.removeItem("papel");
    localStorage.removeItem("id_turista");
    window.location.href = emPages ? "../index.html" : "index.html";
  });
});
