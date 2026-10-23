import { getRegulationsStatus, queryRAGCopilot } from "../api.js?v=enterprise-11";
import { escapeHtml, formatDocumentTitle } from "./dom.js?v=enterprise-7";

let activeClaimId = "";

function appendMessage(text, type = "assistant", extra = "") {
  const messages = document.getElementById("chatMessages");
  const message = document.createElement("article");
  message.className = `chat-message chat-message-${type}`;
  message.innerHTML = `<p>${escapeHtml(text)}</p>${extra}`;
  messages.append(message);
  messages.scrollTop = messages.scrollHeight;
  return message;
}

function renderCitations(citations = []) {
  if (!citations.length) return "";
  return `<div class="citation-list">${citations.map((citation) => `<div class="citation-card"><strong>${escapeHtml(formatDocumentTitle(citation.source_document))} · hlm. ${escapeHtml(citation.page_number)}</strong><p>${escapeHtml(citation.excerpt)}</p></div>`).join("")}</div>`;
}

function renderDraftCard(text, disputeId = "") {
  const safeText = escapeHtml(text);
  const savedNotice = disputeId
    ? '<p class="dispute-saved-notice">Draf tersimpan dengan ID ' + escapeHtml(disputeId) + '. Buka menu Sanggahan untuk meninjau status dan tindak lanjutnya.</p><button class="copy-draft-button" type="button" data-open-disputes>Buka daftar sanggahan</button>'
    : "";
  return '<div class="dispute-draft-card"><pre>' + safeText + '</pre><button class="copy-draft-button" type="button" data-copy-draft="' + safeText + '">Salin draf sanggahan</button>' + savedNotice + '</div>';
}

async function submitQuestion(event) {
  event.preventDefault();
  const input = document.getElementById("chatQuery");
  const query = input.value.trim();
  if (!query) return;
  appendMessage(query, "user");
  input.value = "";
  const pending = appendMessage("Menelusuri dokumen regulasi…", "assistant");
  try {
    const result = await queryRAGCopilot(query, activeClaimId || null);
    pending.remove();
    appendMessage(result.answer, "assistant", `${renderCitations(result.citations)}${result.dispute_template ? renderDraftCard(result.dispute_template) : ""}`);
  } catch (error) {
    pending.remove();
    appendMessage(error.message, "error");
  }
}

export function setActiveClaim(claimId) {
  activeClaimId = claimId || "";
  const input = document.getElementById("draftClaimId");
  if (input && activeClaimId) input.value = activeClaimId;
}

export function initChatbot() {
  document.getElementById("chatQueryForm").addEventListener("submit", submitQuestion);
  document.getElementById("openChatDisputeModalButton").addEventListener("click", () => {
    document.dispatchEvent(new CustomEvent("klaimguard:open-dispute-modal", { detail: { claimId: activeClaimId } }));
  });
  document.querySelectorAll("[data-chat-prompt]").forEach((button) => {
    button.addEventListener("click", () => {
      const input = document.getElementById("chatQuery");
      input.value = button.dataset.chatPrompt;
      input.focus();
    });
  });
  document.getElementById("chatMessages").addEventListener("click", async (event) => {
    if (event.target.closest("[data-open-disputes]")) {
      document.dispatchEvent(new Event("klaimguard:open-disputes"));
      return;
    }
    const button = event.target.closest("[data-copy-draft]");
    if (!button) return;
    const text = button.dataset.copyDraft;
    try {
      await navigator.clipboard.writeText(text);
      button.textContent = "Tersalin";
    } catch {
      button.textContent = "Salin tidak tersedia";
    }
  });

  getRegulationsStatus().then((status) => {
    const label = document.getElementById("ragStatus");
    label.textContent = status.index_ready
      ? `${status.indexed_documents} dokumen · ${status.indexed_chunks ?? "—"} potongan`
      : `${status.available_document_count} PDF tersedia · indeks belum aktif`;
    label.classList.toggle("is-offline", !status.index_ready);
  }).catch(() => {
    const label = document.getElementById("ragStatus");
    label.textContent = "Status indeks tidak dapat dimuat";
    label.classList.add("is-offline");
  });
}
