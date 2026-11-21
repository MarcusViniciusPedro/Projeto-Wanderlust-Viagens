const API_BASE = "http://localhost:8000";

async function apiFetch(caminho, opcoes = {}) {
  const token = localStorage.getItem("access_token");
  const resposta = await fetch(API_BASE + caminho, {
    ...opcoes,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...opcoes.headers,
    },
  });
  if (!resposta.ok) {
    const erro = await resposta.json().catch(() => ({}));
    throw new Error(erro.detail || `Erro ${resposta.status}`);
  }
  // 204 No Content (ex.: DELETE) ou corpo vazio: não há JSON para parsear.
  if (resposta.status === 204) return null;
  const texto = await resposta.text();
  return texto ? JSON.parse(texto) : null;
}

// Exemplo de uso: estimar orçamento (não precisa de banco)
function estimarOrcamento(dados) {
  return apiFetch("/recomendacao/orcamento", {
    method: "POST",
    body: JSON.stringify(dados),
  });
}
