import { escapeHtml, formatIdr, normalizeCode, parseBillingCodes } from "./dom.js";

function getViolationCode(claim, codes, rules) {
  const billed = new Set(codes.map(normalizeCode));
  const matchingRule = rules.find((rule) =>
    billed.has(normalizeCode(rule.primary_code)) && billed.has(normalizeCode(rule.conflicting_code))
  );
  if (matchingRule) return normalizeCode(matchingRule.conflicting_code);
  return claim.is_fraud ? "*" : "";
}

function statusMarkup(claim) {
  if (!claim.is_fraud) return '<span class="status-badge status-badge-safe">✓ AMAN</span>';
  if (claim.fraud_type === "upcoding") {
    return '<span class="status-badge status-badge-upcoding">⚠ FLAGGED · Upcoding</span>';
  }
  if (claim.fraud_type === "unbundling") {
    return '<span class="status-badge status-badge-unbundling">⚠ FLAGGED · Unbundling</span>';
  }
  return '<span class="status-badge status-badge-review">⚠ Perlu Verifikasi</span>';
}

export function renderTable(claims, onRowClick, rules = [], bodyId = "claimsTableBody") {
  const body = document.getElementById(bodyId);
  if (!body) return;
  if (!claims.length) {
    body.innerHTML = '<tr><td colspan="7" class="table-message">Tidak ada klaim untuk filter ini.</td></tr>';
    return;
  }

  body.innerHTML = claims.map((claim, index) => {
    const codes = parseBillingCodes(claim.admin_billing_code);
    const violationCode = getViolationCode(claim, codes, rules);
    const chips = codes.length
      ? codes.map((code) => {
        const isViolation = violationCode === "*" || normalizeCode(code) === violationCode;
        const title = isViolation ? "Kode ditandai untuk verifikasi" : "Kode tercatat";
        return `<span class="chip-code ${isViolation ? "chip-code-violation" : "chip-code-valid"}" title="${title}">${escapeHtml(code)}</span>`;
      }).join("")
      : '<span class="claim-secondary">Tidak ada kode</span>';
    const saving = Number(claim.potential_saving) || 0;
    const tariff = Number(claim.approved_tariff) || 0;
    const costMarkup = claim.is_fraud && tariff > 0 && saving > 0
      ? `<span class="cost-requested is-fraud">${escapeHtml(formatIdr(claim.total_charge))}</span><span class="cost-approved">${escapeHtml(formatIdr(tariff))}</span><span class="saving-badge">Hemat ${escapeHtml(formatIdr(saving))}</span>`
      : `<span class="cost-requested">${escapeHtml(formatIdr(claim.total_charge))}</span>`;
    return `<tr>
      <td class="number-cell">${index + 1}</td>
      <td>
        <span class="claim-primary claim-id-cell">${escapeHtml(claim.claim_id)}</span>
        <span class="claim-secondary">SEP ${escapeHtml(claim.sep_number)}</span>
      </td>
      <td><span class="claim-notes">${escapeHtml(claim.doctor_notes)}</span></td>
      <td class="code-cell">${chips}</td>
      <td>${costMarkup}</td>
      <td class="status-cell">${statusMarkup(claim)}</td>
      <td class="action-cell"><button class="btn btn-outline-sm btn-detail" type="button" data-review="${escapeHtml(claim.claim_id)}">Lihat Detail ↗</button></td>
    </tr>`;
  }).join("");

  body.querySelectorAll("[data-review]").forEach((button) => {
    button.addEventListener("click", () => {
      const claim = claims.find((item) => item.claim_id === button.dataset.review);
      if (claim) onRowClick(claim);
    });
  });
}