import {
  createDispute,
  getDisputes,
  markDisputeSent,
  reviewDispute,
  submitDispute,
  updateDispute,
} from "../api.js?v=enterprise-11";
import { escapeHtml, formatNumber } from "./dom.js?v=enterprise-8";

const labels = {
  draft: "Draf",
  in_review: "Menunggu tinjauan",
  approved: "Disetujui",
  needs_revision: "Perlu revisi",
  sent: "Terkirim",
  closed: "Ditutup",
};

let role = "";
let toast = () => {};
let records = [];
let active = null;

function openDetailOverlay() {
  const overlay = document.getElementById("disputeDetailOverlay");
  overlay.classList.remove("hidden");
  overlay.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
}

function closeDetailOverlay() {
  const overlay = document.getElementById("disputeDetailOverlay");
  overlay.classList.add("hidden");
  overlay.setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";
  active = null;
}

function setDetail(item) {
  if (!item) return;
  active = item;
  const audit = role === "admin_audit";
  const editable = !audit && ["draft", "needs_revision"].includes(item.status);
  document.getElementById("disputeDetailId").textContent = item.dispute_id;
  document.getElementById("disputeDetailTitle").textContent = "Klaim " + item.claim_id;
  document.getElementById("disputeDetailMeta").textContent =
    "SEP " + item.sep_number + " · " + (labels[item.status] || item.status) + " · dibuat oleh " + item.created_by;
  const editor = document.getElementById("disputeLetterBody");
  editor.value = item.letter_body;
  editor.readOnly = !editable;
  document.getElementById("disputeReviewNote").textContent = item.review_notes
    ? "Catatan Admin Audit: " + item.review_notes
    : "";
  const citations = document.getElementById("disputeCitationList");
  citations.replaceChildren();
  (item.citations || []).forEach((citation) => {
    const row = document.createElement("li");
    const title = document.createElement("strong");
    title.textContent = citation.source_document + " · halaman " + citation.page_number;
    const excerpt = document.createElement("p");
    excerpt.textContent = citation.excerpt;
    row.append(title, excerpt);
    citations.append(row);
  });
  document.getElementById("disputeBpjsActions").classList.toggle("hidden", !editable);
  document.getElementById("disputeSentForm").classList.toggle("hidden", audit || item.status !== "approved");
  document.getElementById("disputeAuditActions").classList.toggle("hidden", !audit || !["in_review", "sent"].includes(item.status));
  document.getElementById("approveDisputeButton").classList.toggle("hidden", item.status !== "in_review");
  document.getElementById("requestDisputeRevisionButton").classList.toggle("hidden", item.status !== "in_review");
  document.getElementById("closeDisputeButton").classList.toggle("hidden", item.status !== "sent");
  const history = document.getElementById("disputeHistoryList");
  history.replaceChildren();
  (item.history || []).forEach((entry) => {
    const row = document.createElement("li");
    const time = entry.created_at ? new Date(entry.created_at).toLocaleString("id-ID") : "—";
    const status = document.createElement("strong");
    status.textContent = labels[entry.to_status] || entry.to_status;
    const detail = document.createElement("span");
    detail.textContent = time + " · " + entry.actor_id + (entry.notes ? " — " + entry.notes : "");
    row.append(status, detail);
    history.append(row);
  });
  openDetailOverlay();
}

async function load() {
  const body = document.getElementById("disputeListBody");
  body.innerHTML = '<tr><td colspan="5" class="table-message">Memuat sanggahan…</td></tr>';
  try {
    const status = document.getElementById("disputeStatusFilter").value;
    records = await getDisputes(status);
    document.getElementById("disputeListSummary").textContent = formatNumber(records.length) + " sanggahan tersimpan";
    body.replaceChildren();
    if (!records.length) {
      body.innerHTML = '<tr><td colspan="5" class="table-message">Belum ada sanggahan pada status ini.</td></tr>';
      return;
    }
    records.forEach((item) => {
      const row = document.createElement("tr");
      [item.dispute_id, item.claim_id, labels[item.status] || item.status,
        item.updated_at ? new Date(item.updated_at).toLocaleString("id-ID") : "—"].forEach((value) => {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.append(cell);
      });
      const action = document.createElement("td");
      const button = document.createElement("button");
      button.className = "button button-quiet";
      button.type = "button";
      button.textContent = "Buka";
      button.addEventListener("click", () => setDetail(item));
      action.append(button);
      row.append(action);
      body.append(row);
    });
    if (active) {
      const refreshed = records.find((item) => item.dispute_id === active.dispute_id);
      if (refreshed) setDetail(refreshed);
    }
  } catch (error) {
    body.innerHTML = '<tr><td colspan="5" class="table-message is-error">' + escapeHtml(error.message) + "</td></tr>";
  }
}

async function withActive(action, successMessage) {
  if (!active) return;
  try {
    const updated = await action(active);
    toast(successMessage);
    await load();
    setDetail(updated);
  } catch (error) {
    toast(error.message, true);
  }
}

function exportPdf() {
  if (!active) return;
  if (!window.jspdf?.jsPDF) {
    window.print();
    return;
  }
  const pdf = new window.jspdf.jsPDF({ orientation: "portrait", unit: "mm", format: "a4" });
  pdf.setFont("helvetica", "bold");
  pdf.setFontSize(14);
  pdf.text("Draf Sanggahan " + active.dispute_id, 14, 18);
  pdf.setFont("helvetica", "normal");
  pdf.setFontSize(10);
  const lines = pdf.splitTextToSize(document.getElementById("disputeLetterBody").value, 180);
  let y = 28;
  lines.forEach((line) => {
    if (y > 282) {
      pdf.addPage();
      y = 16;
    }
    pdf.text(line, 14, y);
    y += 5;
  });
  pdf.save("KlaimGuard-" + active.dispute_id + ".pdf");
  toast("PDF sanggahan berhasil diunduh.");
}

export function initDisputeWorkflow(currentRole, showToast) {
  role = currentRole;
  toast = showToast;
  document.getElementById("openDisputeModalButton").classList.toggle("is-hidden", role !== "admin_bpjs");
  document.getElementById("openChatDisputeModalButton").classList.toggle("is-hidden", role !== "admin_bpjs");
  const modal = document.getElementById("createDisputeModal");
  const claimInput = document.getElementById("newDisputeClaimId");
  const openModal = (claimId = "") => {
    if (claimId) claimInput.value = claimId;
    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
    claimInput.focus();
  };
  const closeModal = () => {
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
  };
  document.getElementById("openDisputeModalButton").addEventListener("click", () => openModal());
  document.getElementById("closeDisputeModalButton").addEventListener("click", closeModal);
  modal.addEventListener("click", (event) => {
    if (event.target.closest("[data-close-dispute-modal]")) closeModal();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.classList.contains("hidden")) closeModal();
  });
  document.addEventListener("klaimguard:open-dispute-modal", (event) => openModal(event.detail?.claimId || ""));
  document.getElementById("refreshDisputesButton").addEventListener("click", load);
  document.getElementById("disputeStatusFilter").addEventListener("change", () => {
    active = null;
    closeDetailOverlay();
    load();
  });
  // Close detail overlay
  document.getElementById("closeDisputeDetailButton").addEventListener("click", closeDetailOverlay);
  document.getElementById("disputeDetailBackdrop").addEventListener("click", closeDetailOverlay);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !document.getElementById("disputeDetailOverlay").classList.contains("hidden")) {
      closeDetailOverlay();
    }
  });
  document.getElementById("createDisputeForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = document.getElementById("newDisputeClaimId");
    const button = event.submitter;
    button.disabled = true;
    try {
      const item = await createDispute(input.value.trim());
      input.value = "";
      closeModal();
      toast("Draf " + item.dispute_id + " tersimpan.");
      await load();
      setDetail(item);
    } catch (error) {
      toast(error.message, true);
    } finally {
      button.disabled = false;
    }
  });
  document.getElementById("saveDisputeButton").addEventListener("click", () =>
    withActive((item) => updateDispute(item.dispute_id, document.getElementById("disputeLetterBody").value), "Perubahan draf tersimpan."));
  document.getElementById("submitDisputeButton").addEventListener("click", () =>
    withActive(async (item) => {
      const text = document.getElementById("disputeLetterBody").value;
      if (text !== item.letter_body) await updateDispute(item.dispute_id, text);
      return submitDispute(item.dispute_id);
    }, "Sanggahan diajukan untuk tinjauan Admin Audit."));
  document.getElementById("approveDisputeButton").addEventListener("click", () =>
    withActive((item) => reviewDispute(item.dispute_id, "approve", document.getElementById("disputeReviewNotes").value.trim()), "Draf sanggahan disetujui."));
  document.getElementById("requestDisputeRevisionButton").addEventListener("click", () =>
    withActive((item) => reviewDispute(item.dispute_id, "request_revision", document.getElementById("disputeReviewNotes").value.trim()), "Catatan revisi dikirim ke Admin BPJS."));
  document.getElementById("closeDisputeButton").addEventListener("click", () =>
    withActive((item) => reviewDispute(item.dispute_id, "close", document.getElementById("disputeReviewNotes").value.trim()), "Sanggahan ditutup."));
  document.getElementById("markDisputeSentButton").addEventListener("click", () =>
    withActive((item) => markDisputeSent(
      item.dispute_id,
      document.getElementById("disputeRecipient").value.trim(),
      document.getElementById("disputeReference").value.trim(),
    ), "Pengiriman sanggahan tercatat."));
  document.getElementById("exportDisputePdfButton").addEventListener("click", exportPdf);
  document.getElementById("disputeStatusFilter").value = "";
  document.addEventListener("klaimguard:load-disputes", load);
  document.addEventListener("klaimguard:open-disputes", () => {
    document.querySelector('.sidebar-nav [data-tab="disputes"]').click();
  });
}
