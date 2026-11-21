const API_BASE = "http://localhost:8000";

// Normaliza e exibe nível/regime de forma UNIFORME, independentemente de como
// o valor foi gravado ("Café da manhã", "Cafe da manha", "cafe_da_manha" -> o
// mesmo rótulo). Só afeta a exibição; não altera os dados no banco.
function _normChave(v) {
  if (!v) return "";
  return String(v)
    .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .trim().toLowerCase()
    .replace(/[\s-]+/g, "_");
}

const ROTULOS_REGIME = {
  sem_refeicao: "Sem refeição", cafe_da_manha: "Café da manhã",
  meia_pensao: "Meia pensão", pensao_completa: "Pensão completa",
  all_inclusive: "All inclusive",
};
const ROTULOS_NIVEL = { economico: "Econômico", conforto: "Conforto", luxo: "Luxo" };

function rotuloRegime(v) {
  if (!v) return "—";
  return ROTULOS_REGIME[_normChave(v)] || v;
}
function rotuloNivel(v) {
  if (!v) return "—";
  return ROTULOS_NIVEL[_normChave(v)] || v;
}

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
