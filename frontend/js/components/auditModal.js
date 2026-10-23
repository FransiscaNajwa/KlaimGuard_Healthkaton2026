import { getClaimDetail, postFeedback } from "../api.js?v=enterprise-9";
import { escapeHtml, formatIdr, parseBillingCodes } from "./dom.js";

let activeClaimId = "";
let afterSaveCallback = async () => {};

function renderCodeRows(items) {
  if (!items.length) return '<tr><td colspan="5">Rincian kode belum tersedia.</td></tr>';
  return items.map((item) => `<tr>
    <td><strong>${escapeHtml(item.code)}</strong></td>
    <td>${escapeHtml(item.code_type)}</td>
    <td><span class="status-badge ${item.status === "VIOLATION" ? "status-badge-upcoding" : "status-badge-safe"}">${escapeHtml(item.status === "VIOLATION" ? "Pelanggaran" : "Valid")}</span></td>
    <td>${escapeHtml(item.clinical_note)}</td>
    <td>${escapeHtml(item.rule_source || item.description)}</td>
  </tr>`).join("");
}

function renderDetail(claim) {
  const body = document.getElementById("auditModalBody");
  const canVerify = document.body.dataset.role === "admin_audit";
  const rule = claim.rule;
  const risk = Number.isFinite(Number(claim.risk_score)) ? `${(Number(claim.risk_score) * 100).toLocaleString("id-ID", { maximumFractionDigits: 1 })}%` : "Tidak tersedia";
  const codes = claim.code_breakdown?.length
    ? claim.code_breakdown
    : parseBillingCodes(claim.admin_billing_code).map((code, index) => ({ code, code_type: index ? "ICD-10-SECONDARY" : "ICD-10-PRIMARY", status: "VALID", clinical_note: claim.doctor_notes, description: `Billing code ${code}` }));
  const tariff = Number(claim.approved_tariff) || 0;
  const narrative = claim.reason_narrative || claim.audit_notes || "Analisis tidak menghasilkan narasi tambahan.";
  document.getElementById("auditModalTitle").textContent = "Detail Pemeriksaan Klaim";
  body.innerHTML = `
    <section class="evidence-block"><h3>Informasi Klaim</h3>
      <div class="detail-summary">
        <div class="detail-stat"><span>ID Klaim</span><strong>${escapeHtml(claim.claim_id)}</strong></div>
        <div class="detail-stat"><span>SEP Tersamarkan</span><strong>${escapeHtml(claim.sep_number || "Belum tersedia")}</strong></div>
        <div class="detail-stat"><span>Lama Rawat (LOS)</span><strong>${escapeHtml(claim.length_of_stay)} hari</strong></div>
        <div class="detail-stat"><span>Status Audit</span><strong>${claim.is_fraud ? "FLAGGED" : "AMAN"}</strong></div>
        <div class="detail-stat"><span>Skor Risiko AI</span><strong>${escapeHtml(risk)}</strong></div>
      </div>
    </section>
    <section class="evidence-block"><h3>Perbandingan Klinis & Koding</h3>
      <h4>Catatan Dokter</h4><div class="evidence-note">${escapeHtml(claim.doctor_notes)}</div>
      <h4>Kode ICD yang diajukan</h4><div class="code-breakdown-wrap"><table class="code-breakdown-table">
        <thead><tr><th>Kode</th><th>Tipe</th><th>Status</th><th>Catatan klinis</th><th>Deskripsi / sumber</th></tr></thead>
        <tbody>${renderCodeRows(codes)}</tbody>
      </table></div>
    </section>
    <section class="evidence-block"><h3>Rincian Tarif</h3><div class="detail-summary">
      <div class="detail-stat"><span>Tagihan Rumah Sakit</span><strong>${escapeHtml(formatIdr(claim.total_charge))}</strong></div>
      <div class="detail-stat"><span>Standar Tarif INA-CBG</span><strong>${tariff > 0 ? escapeHtml(formatIdr(tariff)) : "Belum tersedia untuk analisis manual"}</strong></div>
      <div class="detail-stat"><span>Potensi Hemat</span><strong>${escapeHtml(formatIdr(claim.potential_saving))}</strong></div>
    </div></section>
    <section class="evidence-block"><h3>Analisis AI & Dasar Regulasi (XAI)</h3><div class="evidence-note">${escapeHtml(narrative)}</div>
      ${rule ? `<div class="legal-evidence"><strong>${escapeHtml(rule.legal_source)}</strong><br>${escapeHtml(rule.regulation_ref)}<br><br>${escapeHtml(rule.clinical_narrative)}<br><br><strong>Rekomendasi:</strong> ${escapeHtml(rule.recommendation)}</div>` : ""}
    </section>
    <section class="feedback-panel"><h3>Keputusan Verifikator</h3>
      ${canVerify ? `<div class="detail-actions"><button class="button button-primary" id="approveClaimButton" type="button" ${claim.manual_only ? "disabled" : ""}>Setujui Klaim</button><button class="button button-quiet" id="overrideClaimButton" type="button" ${claim.manual_only ? "disabled" : ""}>Override Keputusan AI</button></div>
      <p class="feedback-result" id="feedbackResult" aria-live="polite">${claim.manual_only ? "Analisis manual bersifat sementara; keputusan audit tersedia untuk klaim yang tersimpan." : "Keputusan manusia disimpan pada jejak audit."}</p>` : `<p class="feedback-result">Mode baca saja: keputusan klaim hanya dapat disimpan oleh Admin Audit.</p>`}
    </section>`;
  if (!canVerify) return;
  document.getElementById("approveClaimButton").addEventListener("click", () => {
    if (claim.is_fraud) openOverride("APPROVED_SAFE");
    else saveDecision("APPROVED_SAFE", "Klaim disetujui setelah pemeriksaan verifikator.");
  });
  document.getElementById("overrideClaimButton").addEventListener("click", () => {
    openOverride(claim.is_fraud ? "APPROVED_SAFE" : "CONFIRMED_FRAUD");
  });
}

function openOverride(decision) {
  const modal = document.getElementById("overrideModal");
  document.getElementById("overrideDecision").value = decision;
  document.getElementById("overrideNotes").value = "";
  document.getElementById("overrideResult").textContent = "";
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  document.getElementById("overrideNotes").focus();
}

function closeOverride() {
  const modal = document.getElementById("overrideModal");
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
}

async function saveDecision(decision, notes, result = document.getElementById("feedbackResult")) {
  const submit = document.getElementById("saveOverride");
  if (decision !== "APPROVED_SAFE" || activeClaimId && document.getElementById("overrideModal").classList.contains("hidden") === false) {
    if (notes.trim().length < 10) {
      if (result) { result.textContent = "Alasan wajib berisi minimal 10 karakter."; result.classList.add("is-error"); }
      return;
    }
  }
  if (submit) submit.disabled = true;
  if (result) { result.textContent = "Menyimpan keputusan…"; result.classList.remove("is-error", "is-success"); }
  try {
    await postFeedback({ claim_id: activeClaimId, verifier_id: "VERIF-BPJS-001", decision, notes });
    if (result) { result.textContent = "Keputusan tersimpan di jejak audit."; result.classList.add("is-success"); }
    closeOverride();
    await afterSaveCallback();
    closeModal();
  } catch (error) {
    if (result) { result.textContent = error.message; result.classList.add("is-error"); }
  } finally {
    if (submit) submit.disabled = false;
  }
}

async function submitOverride(event) {
  event.preventDefault();
  await saveDecision(
    document.getElementById("overrideDecision").value,
    document.getElementById("overrideNotes").value,
    document.getElementById("overrideResult"),
  );
}

export async function openClaimDetail(claimOrId, onSaveCallback = () => {}) {
  const claimId = typeof claimOrId === "string" ? claimOrId : claimOrId.claim_id;
  const claim = typeof claimOrId === "string" ? null : claimOrId;
  const drawer = document.getElementById("claimDetailDrawer");
  const body = document.getElementById("auditModalBody");
  activeClaimId = claimId;
  afterSaveCallback = onSaveCallback;
  drawer.classList.add("is-open");
  drawer.setAttribute("aria-hidden", "false");
  document.body.dataset.drawerOpen = "true";
  body.innerHTML = '<p class="modal-loading">Memuat detail pemeriksaan…</p>';
  if (claim && (claim.reason_narrative || claim.rule || claim.code_breakdown?.length)) {
    renderDetail(claim);
    return;
  }
  try {
    const detail = await getClaimDetail(claimId);
    renderDetail(detail);
  } catch (error) {
    body.innerHTML = `<p class="modal-error">${escapeHtml(error.message)}</p>`;
  }
}

export const openModal = openClaimDetail;

export function closeModal() {
  const drawer = document.getElementById("claimDetailDrawer");
  drawer.classList.remove("is-open");
  drawer.setAttribute("aria-hidden", "true");
  document.body.dataset.drawerOpen = "false";
  document.getElementById("auditModalBody").replaceChildren();
  closeOverride();
  activeClaimId = "";
  afterSaveCallback = async () => {};
}

document.getElementById("overrideForm")?.addEventListener("submit", submitOverride);
document.getElementById("closeOverrideModal")?.addEventListener("click", closeOverride);
document.getElementById("cancelOverride")?.addEventListener("click", closeOverride);
document.querySelector("[data-close-override]")?.addEventListener("click", closeOverride);

document.getElementById("closeAuditModal")?.addEventListener("click", closeModal);
document.querySelector("[data-close-modal]")?.addEventListener("click", closeModal);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeModal();
});
