import { formatNumber } from "./dom.js";

function pageItems(currentPage, totalPages) {
  if (totalPages <= 5) return Array.from({ length: totalPages }, (_, index) => index + 1);
  const pages = new Set([1, totalPages, currentPage - 1, currentPage, currentPage + 1]);
  return [...pages].filter((page) => page >= 1 && page <= totalPages).sort((a, b) => a - b);
}

export function renderPagination(meta, onPageChange, containerId = "paginationContainer") {
  const container = document.getElementById(containerId);
  const page = Number(meta.current_page) || 1;
  const totalPages = Number(meta.total_pages) || 0;
  const total = Number(meta.total_records) || 0;
  const limit = Number(meta.limit) || 50;
  const start = total ? (page - 1) * limit + 1 : 0;
  const end = Math.min(page * limit, total);
  const pages = pageItems(page, totalPages);
  let previous = 0;
  const pageButtons = pages.map((number) => {
    const gap = previous && number - previous > 1 ? '<span class="page-ellipsis">…</span>' : "";
    previous = number;
    return `${gap}<button class="page-button ${number === page ? "is-current" : ""}" type="button" data-page="${number}" ${number === page ? 'aria-current="page"' : ""}>${number}</button>`;
  }).join("");

  container.innerHTML = `<span class="pagination-info">Menampilkan <strong>${formatNumber(start)}–${formatNumber(end)}</strong> dari <strong>${formatNumber(total)}</strong> klaim</span>
    <nav class="pagination-controls" aria-label="Navigasi halaman">
      <button class="page-button" type="button" data-page="${page - 1}" aria-label="Halaman sebelumnya" ${page <= 1 ? "disabled" : ""}>‹</button>
      ${pageButtons}
      <button class="page-button" type="button" data-page="${page + 1}" aria-label="Halaman berikutnya" ${page >= totalPages ? "disabled" : ""}>›</button>
    </nav>`;
  container.querySelectorAll("[data-page]").forEach((button) => {
    button.addEventListener("click", () => onPageChange(Number(button.dataset.page)));
  });
}