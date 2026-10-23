import { escapeHtml, formatIdr, formatNumber } from "./dom.js";

const metrics = [
  { key: "total_claims", label: "Total Klaim", note: "Dataset FKRTL aktif", color: "#315f83" },
  { key: "safe_claims", label: "Klaim Aman", note: "Sesuai standar INA-CBG", color: "#2e7d32" },
  { key: "upcoding_count", label: "Indikasi Upcoding", note: "Anomali diagnosis & tarif", color: "#d32f2f" },
  { key: "unbundling_count", label: "Indikasi Unbundling", note: "Prosedur terpisah", color: "#f57c00" },
  { key: "total_potential_saving_idr", label: "Potensi Hemat", note: "Dana JKN terindikasi", color: "#148c83", currency: true },
];

export function renderStats(data) {
  const container = document.getElementById("kpiContainer");
  if (!container) return;
  container.innerHTML = metrics.map((metric) => {
    const value = metric.currency
      ? formatIdr(data[metric.key], true)
      : formatNumber(data[metric.key]);
    return `<article class="kpi-card" style="--metric-color:${metric.color}">
      <span class="kpi-card-label">${escapeHtml(metric.label)}</span>
      <strong class="kpi-card-value ${metric.currency ? "is-currency" : ""}">${escapeHtml(value)}</strong>
      <span class="kpi-card-note">${escapeHtml(metric.note)}</span>
    </article>`;
  }).join("");
  const coverage = document.getElementById("auditCoverage");
  if (coverage) coverage.textContent = `${Number(data.audit_coverage_pct || 0).toFixed(1)}%`;
}