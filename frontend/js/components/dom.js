export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

export function formatIdr(value, compact = false) {
  return new Intl.NumberFormat("id-ID", {
    style: "currency",
    currency: "IDR",
    maximumFractionDigits: 0,
    notation: compact ? "compact" : "standard",
  }).format(Number(value) || 0);
}

export function formatNumber(value) {
  return new Intl.NumberFormat("id-ID").format(Number(value) || 0);
}

export function parseBillingCodes(value) {
  if (Array.isArray(value)) return value.map(String);
  if (typeof value !== "string") return [];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return value.trim() ? [value.trim()] : [];
  }
}

export function normalizeCode(value) {
  return String(value ?? "").replace(/[.\s]/g, "").toUpperCase();
}

const REGULATION_TITLES = new Map([
  ["2015permenkes036", "Permenkes Nomor 36 Tahun 2015"],
  ["2016permenkes076", "Permenkes Nomor 76 Tahun 2016"],
  ["2019 buku panduan icd 10-9cm dalam bidang urologi", "Buku Panduan ICD-10 dan ICD-9-CM Bidang Urologi 2019"],
  ["panduan manual verifikasi klaim ina-cbg edisi 1", "Panduan Manual Verifikasi Klaim INA-CBG Edisi 1"],
  ["panduan manual verifikasi klaim ina-cbg edisi 2", "Panduan Manual Verifikasi Klaim INA-CBG Edisi 2"],
  ["permenkes nomor 3 tahun 2023", "Permenkes Nomor 3 Tahun 2023"],
]);

export function formatDocumentTitle(value) {
  const fileName = String(value ?? "").split(/[\\/]/).pop() || "";
  const normalized = fileName
    .replace(/\.pdf$/i, "")
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return REGULATION_TITLES.get(normalized.toLowerCase()) || normalized;
}