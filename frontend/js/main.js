import {
  analyzeClaim,
  login,
  logout,
  getAnalytics,
  getAuditLogs,
  getClaims,
  getCurrentUser,
  getRules,
  getStats,
  runBatchAudit,
} from "./api.js?v=enterprise-11";
import { openModal, closeModal } from "./components/auditModal.js?v=enterprise-10";
import { renderTable } from "./components/claimTable.js";
import { escapeHtml, formatDocumentTitle, formatIdr, formatNumber } from "./components/dom.js?v=enterprise-8";
import { initChatbot, setActiveClaim } from "./components/chatbotWidget.js?v=enterprise-10";
import { initDisputeWorkflow } from "./components/disputeWorkflow.js?v=enterprise-1";
import { renderPagination } from "./components/pagination.js";
import { renderStats } from "./components/statsCard.js?v=enterprise-8";
import { initTheme } from "./components/themeManager.js";

const state = {
  page: 1,
  limit: 10,
  search: "",
  status: "",
  fraudType: "",
  rules: [],
  stats: null,
  analyticsData: null,
  analyticsFilter: { category: "all", cost: "all" },
  auditPage: 0,
  loading: false,
  batchResults: [],
  batchPage: 1,
  batchPageSize: 10,
  reportSources: [],
};

let financialComparisonChart;
let losCorrelationChart;
let costRiskDistChart;
let topAnomaliesChart;

let searchTimer;

function showToast(message, isError = false) {
  const region = document.getElementById("toastRegion");
  const toast = document.createElement("div");
  toast.className = `toast ${isError ? "is-error" : ""}`;
  toast.textContent = message;
  region.append(toast);
  window.setTimeout(() => toast.remove(), 4400);
}

function configureRoleAccess(role) {
  const canAnalyze = role === "admin_audit";
  document.querySelector(".manual-form-section").classList.toggle("is-hidden", !canAnalyze);
  document.getElementById("batchNavItem").classList.toggle("is-hidden", !canAnalyze);
  document.getElementById("batchTab").classList.toggle("is-hidden", !canAnalyze);
  const restrictedControls = [
    ...document.querySelectorAll("#manualFormCollapse input, #manualFormCollapse select, #manualFormCollapse button"),
    document.getElementById("toggleManualFormBtn"),
    document.getElementById("batchAuditBtn"),
    ...document.querySelectorAll("#batchAuditForm input, #batchAuditForm button, [data-batch-size]"),
  ];
  restrictedControls.forEach((control) => {
    control.disabled = !canAnalyze;
    control.classList.toggle("is-hidden", !canAnalyze);
    control.title = canAnalyze ? "" : "Hanya Admin Audit yang dapat menjalankan analisis.";
  });
}

function showAuthenticatedApp(user) {
  document.body.dataset.role = user.role;
  document.getElementById("loginView").classList.add("is-hidden");
  document.getElementById("appContainer").classList.remove("is-hidden");
  document.getElementById("profileName").textContent = user.user_id;
  const isAuditAdmin = user.role === "admin_audit";
  document.getElementById("profileRole").textContent = isAuditAdmin ? "Admin Audit" : "Admin BPJS";
  initTheme();
  initChatbot();
  initDisputeWorkflow(user.role, showToast);
  bindFilters();
  configureRoleAccess(user.role);
  activateTab("dashboard");
  loadDashboardData();
}

function bindLogin() {
  const passwordInput = document.getElementById("loginPassword");
  const passwordToggle = document.getElementById("togglePasswordButton");
  passwordToggle.addEventListener("click", () => {
    const showPassword = passwordInput.type === "password";
    passwordInput.type = showPassword ? "text" : "password";
    passwordToggle.setAttribute("aria-label", showPassword ? "Sembunyikan password" : "Tampilkan password");
    passwordToggle.setAttribute("aria-pressed", String(showPassword));
    passwordToggle.querySelector(".password-eye-show").classList.toggle("is-hidden", showPassword);
    passwordToggle.querySelector(".password-eye-hide").classList.toggle("is-hidden", !showPassword);
    passwordInput.focus();
  });

  document.getElementById("loginForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const button = document.getElementById("loginButton");
    const error = document.getElementById("loginError");
    button.disabled = true;
    error.textContent = "";
    try {
      const user = await login(String(form.get("username")).trim(), String(form.get("password")));
      showAuthenticatedApp(user);
    } catch (loginError) {
      error.textContent = loginError.message;
    } finally {
      button.disabled = false;
    }
  });
  document.getElementById("logoutButton").addEventListener("click", async () => {
    const button = document.getElementById("logoutButton");
    button.disabled = true;
    try {
      await logout();
      window.location.replace("/");
    } catch (error) {
      button.disabled = false;
      showToast(`Gagal keluar: ${error.message}`, true);
    }
  });
}

async function bootstrap() {
  bindLogin();
  try {
    const user = await getCurrentUser();
    showAuthenticatedApp(user);
  } catch {
    document.getElementById("loginView").classList.remove("is-hidden");
  }
}

function setConnectionStatus(connected, totalClaims = 0) {
  const status = document.getElementById("connectionStatus");
  const text = status.querySelector(".status-text");
  const dot = status.querySelector(".status-dot");
  if (connected) {
    text.textContent = `Terhubung: INA-CBGs Engine v5.5 (${formatNumber(totalClaims)} Klaim)`;
    status.classList.add("status-connected");
    status.classList.remove("status-disconnected");
  } else {
    text.textContent = "Koneksi backend bermasalah";
    status.classList.add("status-disconnected");
    status.classList.remove("status-connected");
  }
  dot?.classList.toggle("is-error", !connected);
}

function setTableMessage(message, isError = false) {
  const body = document.getElementById("claimsTableBody");
  body.innerHTML = `<tr><td colspan="7" class="table-message ${isError ? "is-error" : ""}">${escapeHtml(message)}</td></tr>`;
}

async function loadDashboardData() {
  if (state.loading) return;
  state.loading = true;
  try {
    const [stats, pageData, rules] = await Promise.all([
      getStats(),
      getClaims(state.page, state.limit, state.search, state.status, state.fraudType),
      state.rules.length ? Promise.resolve(state.rules) : getRules(),
    ]);
    state.rules = rules;
    state.stats = stats;
    renderStats(stats);
    renderTable(pageData.data, (claim) => {
      setActiveClaim(claim.claim_id);
      openModal(claim, async () => {
        await loadDashboardData();
        showToast("Keputusan manusia tercatat pada audit trail.");
      });
    }, rules);
    renderPagination({ ...pageData, limit: state.limit }, (page) => {
      if (page < 1 || page > pageData.total_pages || page === state.page) return;
      state.page = page;
      loadDashboardData();
    });
    document.getElementById("resultSummary").textContent = `${formatNumber(pageData.total_records)} klaim ditemukan dalam hasil filter`;
    setConnectionStatus(true, stats.total_claims);
  } catch (error) {
    setConnectionStatus(false);
    setTableMessage(`Data tidak dapat dimuat: ${error.message}`, true);
    showToast(error.message, true);
  } finally {
    state.loading = false;
  }
}

function bindFilters() {
  document.getElementById("claimSearch").addEventListener("input", (event) => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
      state.search = event.target.value;
      state.page = 1;
      loadDashboardData();
    }, 300);
  });
  document.getElementById("statusFilter").addEventListener("change", (event) => {
    state.status = event.target.value;
    state.page = 1;
    loadDashboardData();
  });
  document.getElementById("categoryFilter").addEventListener("change", (event) => {
    state.fraudType = event.target.value;
    state.page = 1;
    loadDashboardData();
  });
  document.getElementById("pageSize").addEventListener("change", (event) => {
    state.limit = Number(event.target.value);
    state.page = 1;
    loadDashboardData();
  });
  document.getElementById("refreshButton").addEventListener("click", loadDashboardData);
  document.getElementById("batchAuditBtn").addEventListener("click", () => {
    runBatch(100, document.getElementById("batchAuditBtn"));
  });
  document.getElementById("batchAuditForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const limit = Number(document.getElementById("batchLimit").value);
    runBatch(limit, document.getElementById("batchRunButton"));
  });
  document.querySelectorAll("[data-batch-size]").forEach((chip) => {
    chip.addEventListener("click", () => {
      document.getElementById("batchLimit").value = chip.dataset.batchSize;
      document.querySelectorAll("[data-batch-size]").forEach((item) => item.classList.toggle("is-active", item === chip));
    });
  });
  document.getElementById("toggleManualFormBtn").addEventListener("click", (event) => {
    const button = event.currentTarget;
    const expanded = button.getAttribute("aria-expanded") !== "true";
    button.setAttribute("aria-expanded", String(expanded));
    document.getElementById("manualFormCollapse").classList.toggle("is-open", expanded);
    document.getElementById("manualFormCollapse").setAttribute("aria-hidden", String(!expanded));
  });
  document.getElementById("refreshAuditButton").addEventListener("click", loadAuditHistory);
  document.getElementById("refreshAnalyticsBtn")?.addEventListener("click", loadReportData);
  document.getElementById("exportPdfBtn")?.addEventListener("click", exportReportPdf);
  document.getElementById("analyticsCategoryFilter")?.addEventListener("change", (e) => {
    state.analyticsFilter.category = e.target.value;
    applyAnalyticsFilter();
  });
  document.getElementById("analyticsCostFilter")?.addEventListener("change", (e) => {
    state.analyticsFilter.cost = e.target.value;
    applyAnalyticsFilter();
  });
  document.querySelectorAll("[data-analytics-preset]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-analytics-preset]").forEach((b) => b.classList.remove("is-active"));
      btn.classList.add("is-active");
      const preset = btn.dataset.analyticsPreset;
      const catSelect = document.getElementById("analyticsCategoryFilter");
      const costSelect = document.getElementById("analyticsCostFilter");
      if (preset === "all") {
        if (catSelect) catSelect.value = "all";
        if (costSelect) costSelect.value = "all";
        state.analyticsFilter = { category: "all", cost: "all" };
      } else if (preset === "upcoding") {
        if (catSelect) catSelect.value = "upcoding";
        if (costSelect) costSelect.value = "all";
        state.analyticsFilter = { category: "upcoding", cost: "all" };
      } else if (preset === "unbundling") {
        if (catSelect) catSelect.value = "unbundling";
        if (costSelect) costSelect.value = "all";
        state.analyticsFilter = { category: "unbundling", cost: "all" };
      } else if (preset === "high_risk") {
        if (costSelect) costSelect.value = "critical";
        state.analyticsFilter.cost = "critical";
      }
      applyAnalyticsFilter();
    });
  });
  document.getElementById("claimForm").addEventListener("submit", analyzeManualClaim);
  document.getElementById("sidebarToggleBtn").addEventListener("click", (event) => {
    const button = event.currentTarget;
    const collapsed = document.getElementById("appSidebar").classList.toggle("collapsed");
    button.setAttribute("aria-expanded", String(!collapsed));
    button.setAttribute("aria-label", collapsed ? "Buka sidebar" : "Tutup sidebar");
    button.title = collapsed ? "Buka sidebar" : "Tutup sidebar";
  });
  document.querySelectorAll(".sidebar-nav [data-tab]").forEach((item) => {
    item.addEventListener("click", () => activateTab(item.dataset.tab));
  });
}

function renderBatchResultsPage(page = state.batchPage) {
  const section = document.getElementById("batchResultTableSection");
  const total = state.batchResults.length;
  const totalPages = Math.ceil(total / state.batchPageSize);
  if (!total) {
    section.classList.add("hidden");
    return;
  }
  state.batchPage = page;
  section.classList.remove("hidden");
  const pageClaims = state.batchResults.slice(
    (page - 1) * state.batchPageSize,
    page * state.batchPageSize,
  );
  renderTable(pageClaims, (claim) => {
    setActiveClaim(claim.claim_id);
    openModal(claim, async () => {
      await loadDashboardData();
      showToast("Keputusan manusia tercatat pada audit trail.");
    });
  }, state.rules, "batchResultsTableBody");
  renderPagination(
    { total_records: total, current_page: page, total_pages: totalPages, limit: state.batchPageSize },
    renderBatchResultsPage,
    "batchResultsPaginationContainer",
  );
}

async function runBatch(limit = 100, button = document.getElementById("batchAuditBtn")) {
  const label = button.querySelector(".button-label");
  const original = label?.textContent || button.textContent;
  button.disabled = true;
  button.classList.add("is-loading");
  if (label) label.textContent = "Memeriksa klaim…";
  try {
    const result = await runBatchAudit(limit);
    showToast(`${formatNumber(result.processed_count)} klaim diproses · ${formatNumber(result.flagged_count)} ditandai · ${formatIdr(result.total_saved_idr)} potensi hemat`);
    const resultPanel = document.getElementById("batchResults");
    resultPanel.innerHTML = [
      ["Klaim diproses", formatNumber(result.processed_count)],
      ["Indikasi anomali", formatNumber(result.flagged_count)],
      ["Klaim aman", formatNumber(result.processed_count - result.flagged_count)],
      ["Potensi hemat", formatIdr(result.total_saved_idr)],
    ].map(([title, value]) => `<div class="batch-result-item"><span>${escapeHtml(title)}</span><strong>${escapeHtml(value)}</strong></div>`).join("");
    resultPanel.classList.remove("hidden");
    const batchSummary = document.getElementById("batchSummary");
    const processedCount = Number(result.processed_count) || 0;
    const flaggedCount = Number(result.flagged_count) || 0;
    const flaggedRate = processedCount ? (flaggedCount / processedCount) * 100 : 0;
    const duration = Number(result.execution_time_seconds) || 0;
    batchSummary.innerHTML = [
      ["Total Processed", formatNumber(processedCount)],
      ["Flagged Rate", `${flaggedRate.toLocaleString("id-ID", { maximumFractionDigits: 1 })}%`],
      ["Estimasi Durasi Pemrosesan", `${duration.toLocaleString("id-ID", { maximumFractionDigits: 2 })} dtk`],
    ].map(([title, value]) => `<div class="batch-summary-item"><span>${escapeHtml(title)}</span><strong>${escapeHtml(value)}</strong></div>`).join("");
    batchSummary.classList.remove("hidden");
    state.batchResults = Array.isArray(result.results) ? result.results : [];
    renderBatchResultsPage(1);
    await loadDashboardData();
  } catch (error) {
    showToast(error.message, true);
  } finally {
    button.disabled = false;
    button.classList.remove("is-loading");
    if (label) label.textContent = original;
    else button.textContent = original;
  }
}

function activateTab(tabName) {
  if (tabName === "batch" && document.body.dataset.role !== "admin_audit") return;
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("hidden", panel.id !== `${tabName}Tab`);
  });
  document.querySelectorAll(".sidebar-nav [data-tab]").forEach((item) => {
    const active = item.dataset.tab === tabName;
    item.classList.toggle("active", active);
    item.setAttribute("aria-current", active ? "page" : "false");
  });
  if (tabName === "audit") loadAuditHistory();
  if (tabName === "disputes") document.dispatchEvent(new Event("klaimguard:load-disputes"));
  if (tabName === "reports") loadReportData();
}

async function loadAuditHistory(page) {
  const body = document.getElementById("auditHistoryBody");
  body.innerHTML = '<tr><td colspan="6" class="table-message">Memuat riwayat...</td></tr>';
  try {
    const targetPage = page || 1;
    const pageData = await getAuditLogs(targetPage, state.limit);
    state.auditPage = targetPage;
    if (!pageData.data.length) {
      body.innerHTML = '<tr><td colspan="6" class="table-message">Belum ada keputusan audit yang tersimpan.</td></tr>';
    } else {
      body.innerHTML = pageData.data.map((entry) => {
        const created = entry.timestamp ? new Date(entry.timestamp).toLocaleString("id-ID") : "-";
        const hash = String(entry.current_hash || "");
        return `<tr><td>${escapeHtml(created)}</td><td><strong>${escapeHtml(entry.claim_id)}</strong></td><td>${escapeHtml(entry.verifier_id)}</td><td>${escapeHtml(entry.decision)}</td><td>${escapeHtml(entry.notes || "-")}</td><td><code title="${escapeHtml(hash)}">${escapeHtml(hash.slice(0, 12) || "-")}</code></td></tr>`;
      }).join("");
    }
    renderPagination(pageData, (nextPage) => loadAuditHistory(nextPage), "auditPagination");
  } catch (error) {
    body.innerHTML = `<tr><td colspan="6" class="table-message is-error">${escapeHtml(error.message)}</td></tr>`;
  }
}

const CLINICAL_CODE_NAMES = {
  '["H10.9", "13.41"]': "Katarak & Fakoemulsifikasi [H10.9, 13.41]",
  '["I25.9", "R57.0"]': "Iskemia Jantung + Syok Kardiogenik [I25.9, R57.0]",
  '["A01.0", "A09"]': "Demam Tifoid + Diare Berat [A01.0, A09]",
  '["D64.9", "D61.9"]': "Anemia Defisiensi + Anemia Aplastik [D64.9, D61.9]",
  '["I10", "N17"]': "Hipertensi + Gagal Ginjal Akut [I10, N17]",
  '["K29.1", "K92.1"]': "Gastritis Akut + Perdarahan Lambung [K29.1, K92.1]",
  '["E11.9", "R02"]': "Diabetes Melitus + Gangren [E11.9, R02]",
  '["47.09", "54.11"]': "Apendektomi + Laparatomi Eksplorasi [47.09, 54.11]",
  '["J06.9", "J20.9"]': "ISPA + Bronkitis Akut [J06.9, J20.9]",
  '["39.95", "99.21"]': "Hemodialisa + Injeksi Terpisah [39.95, 99.21]",
};

function formatMiliar(num) {
  if (num >= 1000000000) {
    return (num / 1000000000).toLocaleString("id-ID", { minimumFractionDigits: 1, maximumFractionDigits: 2 }) + " M";
  }
  if (num >= 1000000) {
    return (num / 1000000).toLocaleString("id-ID", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + " Jt";
  }
  return formatNumber(num);
}

function applyAnalyticsFilter() {
  const { category, cost } = state.analyticsFilter;
  const statusEl = document.getElementById("analyticsFilterStatus");
  let filterText = [];
  if (category !== "all") filterText.push(`Kategori: ${category.toUpperCase()}`);
  if (cost !== "all") filterText.push(`Biaya: ${cost}`);
  if (statusEl) {
    statusEl.textContent = filterText.length
      ? `Filter Aktif: ${filterText.join(" · ")}`
      : "Menampilkan data menyeluruh";
  }
  renderAllAnalyticsCharts();
}

function renderAllAnalyticsCharts() {
  const analytics = state.analyticsData;
  if (!analytics || typeof window.Chart === "undefined") return;
  const filterCat = state.analyticsFilter.category;

  // Chart 1: Financial Comparison (Grouped Bar)
  financialComparisonChart?.destroy();
  const fin = analytics.financial_summary;
  let labels = ["Klaim Aman", "Upcoding", "Unbundling"];
  let chargeData = [fin.safe_charge, fin.upcoding_charge, fin.unbundling_charge];
  let approvedData = [fin.safe_approved, fin.upcoding_approved, fin.unbundling_approved];
  let savingData = [0, fin.upcoding_saving, fin.unbundling_saving];

  if (filterCat === "upcoding") {
    labels = ["Upcoding"];
    chargeData = [fin.upcoding_charge];
    approvedData = [fin.upcoding_approved];
    savingData = [fin.upcoding_saving];
  } else if (filterCat === "unbundling") {
    labels = ["Unbundling"];
    chargeData = [fin.unbundling_charge];
    approvedData = [fin.unbundling_approved];
    savingData = [fin.unbundling_saving];
  } else if (filterCat === "safe") {
    labels = ["Klaim Aman"];
    chargeData = [fin.safe_charge];
    approvedData = [fin.safe_approved];
    savingData = [0];
  }

  const ctx1 = document.getElementById("financialComparisonChart");
  if (ctx1) {
    financialComparisonChart = new window.Chart(ctx1, {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: "Total Tagihan RS",
            data: chargeData,
            backgroundColor: "#0284c7",
            borderRadius: 6,
          },
          {
            label: "Tarif Disetujui INA-CBG",
            data: approvedData,
            backgroundColor: "#10b981",
            borderRadius: 6,
          },
          {
            label: "Potensi Penghematan",
            data: savingData,
            backgroundColor: "#ef4444",
            borderRadius: 6,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: "top", labels: { boxWidth: 12, font: { size: 11, family: "Plus Jakarta Sans" } } },
          tooltip: {
            callbacks: {
              label: (context) => `${context.dataset.label}: ${formatIdr(context.raw)}`,
            },
          },
        },
        scales: {
          y: {
            beginAtZero: true,
            ticks: {
              callback: (value) => "Rp " + formatMiliar(value),
              font: { size: 10 },
            },
          },
          x: { ticks: { font: { size: 11, weight: "600" } } },
        },
      },
    });
  }

  // Chart 2: LOS Correlation (Dual Axis: Bar + Line)
  losCorrelationChart?.destroy();
  const losItems = analytics.los_breakdown || [];
  const losLabels = losItems.map((item) => `${item.length_of_stay} Hari`);
  const losVolume = losItems.map((item) => item.count);
  const losFraudRate = losItems.map((item) => item.fraud_rate_pct);
  const losAvgCharge = losItems.map((item) => item.avg_charge);

  const ctx2 = document.getElementById("losCorrelationChart");
  if (ctx2) {
    losCorrelationChart = new window.Chart(ctx2, {
      data: {
        labels: losLabels,
        datasets: [
          {
            type: "bar",
            label: "Volume Pasien",
            data: losVolume,
            backgroundColor: "rgba(14, 165, 233, 0.45)",
            borderColor: "#0284c7",
            borderWidth: 1,
            borderRadius: 4,
            yAxisID: "y",
          },
          {
            type: "line",
            label: "Tingkat Anomali (%)",
            data: losFraudRate,
            borderColor: "#dc2626",
            backgroundColor: "#dc2626",
            pointRadius: 4,
            pointHoverRadius: 6,
            tension: 0.35,
            yAxisID: "y1",
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: "top", labels: { boxWidth: 12, font: { size: 11 } } },
          tooltip: {
            callbacks: {
              afterLabel: (ctx) => {
                const idx = ctx.dataIndex;
                return `Rata-rata Tagihan: ${formatIdr(losAvgCharge[idx])}`;
              },
            },
          },
        },
        scales: {
          y: {
            type: "linear",
            position: "left",
            beginAtZero: true,
            title: { display: true, text: "Jumlah Klaim", font: { size: 10 } },
            ticks: { font: { size: 10 } },
          },
          y1: {
            type: "linear",
            position: "right",
            min: 0,
            max: 100,
            title: { display: true, text: "% Anomali", font: { size: 10 } },
            ticks: {
              callback: (v) => v + "%",
              font: { size: 10 },
            },
            grid: { drawOnChartArea: false },
          },
          x: { ticks: { font: { size: 10 } } },
        },
      },
    });
  }

  // Chart 3: Cost Risk Distribution (Segmented Donut)
  costRiskDistChart?.destroy();
  const buckets = analytics.cost_buckets || [];
  const bucketLabels = buckets.map((b) => `${b.bucket} (${b.fraud_rate_pct}% anomali)`);
  const bucketCounts = buckets.map((b) => b.count);
  const bucketSavings = buckets.map((b) => b.total_saving);

  const ctx3 = document.getElementById("costRiskDistChart");
  if (ctx3) {
    costRiskDistChart = new window.Chart(ctx3, {
      type: "doughnut",
      data: {
        labels: bucketLabels,
        datasets: [
          {
            data: bucketCounts,
            backgroundColor: ["#10b981", "#3b82f6", "#f59e0b", "#ef4444"],
            borderWidth: 2,
            hoverOffset: 6,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "60%",
        plugins: {
          legend: { position: "bottom", labels: { boxWidth: 12, font: { size: 10 } } },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const idx = ctx.dataIndex;
                return ` ${formatNumber(bucketCounts[idx])} Klaim · Potensi Hemat: ${formatIdr(bucketSavings[idx])}`;
              },
            },
          },
        },
      },
    });
  }

  // Chart 4: Top Anomalies (Horizontal Bar)
  topAnomaliesChart?.destroy();
  let anomalyList = analytics.top_anomalies || [];
  if (filterCat !== "all") {
    anomalyList = anomalyList.filter((a) => a.fraud_type === filterCat);
  }
  const top8 = anomalyList.slice(0, 8);
  const anomalyLabels = top8.map((a) => CLINICAL_CODE_NAMES[a.admin_billing_code] || a.admin_billing_code);
  const anomalyValues = top8.map((a) => a.total_saving);
  const anomalyColors = top8.map((a) => a.fraud_type === "upcoding" ? "#ef4444" : "#f59e0b");

  const ctx4 = document.getElementById("topAnomaliesChart");
  if (ctx4) {
    topAnomaliesChart = new window.Chart(ctx4, {
      type: "bar",
      data: {
        labels: anomalyLabels,
        datasets: [
          {
            label: "Potensi Penghematan",
            data: anomalyValues,
            backgroundColor: anomalyColors,
            borderRadius: 4,
          },
        ],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const item = top8[ctx.dataIndex];
                return [
                  `Potensi Hemat: ${formatIdr(item.total_saving)}`,
                  `Total: ${formatNumber(item.count)} Klaim · Tipe: ${item.fraud_type.toUpperCase()}`,
                  `Regulasi: ${item.rule_code} (${item.regulation_ref})`,
                ];
              },
            },
          },
        },
        scales: {
          x: {
            beginAtZero: true,
            ticks: {
              callback: (v) => "Rp " + formatMiliar(v),
              font: { size: 10 },
            },
          },
          y: {
            ticks: {
              font: { size: 10, weight: "600" },
              callback: function(val) {
                const label = this.getLabelForValue(val);
                return label.length > 28 ? label.substring(0, 26) + "…" : label;
              },
            },
          },
        },
      },
    });
  }
}

async function loadReportData() {
  const summary = document.getElementById("reportSummary");
  try {
    const [data, analytics, rules] = await Promise.all([
      state.stats || getStats(),
      getAnalytics(),
      state.rules.length ? Promise.resolve(state.rules) : getRules(),
    ]);

    state.stats = data;
    state.analyticsData = analytics;
    state.rules = rules;

    // Update 4 Executive KPI Cards
    const fin = analytics.financial_summary || {};
    const totalChargeEl = document.getElementById("analyticsTotalCharge");
    const totalSavingEl = document.getElementById("analyticsTotalSaving");
    const anomalyRateEl = document.getElementById("analyticsAnomalyRate");
    const anomalyBreakdownEl = document.getElementById("analyticsAnomalyBreakdown");
    const costDisparityEl = document.getElementById("analyticsCostDisparity");

    if (totalChargeEl) totalChargeEl.textContent = formatIdr(fin.total_charge || 0);
    if (totalSavingEl) totalSavingEl.textContent = formatIdr(fin.total_saving || 0);
    if (anomalyRateEl) {
      const rate = data.total_claims ? ((data.fraud_claims / data.total_claims) * 100).toFixed(1) : "0.0";
      anomalyRateEl.textContent = `${rate}%`;
    }
    if (anomalyBreakdownEl) {
      anomalyBreakdownEl.textContent = `${formatNumber(data.upcoding_count)} Upcoding · ${formatNumber(data.unbundling_count)} Unbundling`;
    }
    if (costDisparityEl) {
      const avgFraud = data.fraud_claims ? fin.fraud_charge / data.fraud_claims : 0;
      costDisparityEl.textContent = formatIdr(avgFraud);
    }

    // Populate High-Impact Table
    const highImpactBody = document.getElementById("highImpactTableBody");
    if (highImpactBody && analytics.high_impact_claims?.length) {
      highImpactBody.innerHTML = analytics.high_impact_claims.map((claim) => {
        const typeBadge = claim.fraud_type === "upcoding"
          ? '<span class="status-chip is-fraud">Upcoding</span>'
          : '<span class="status-chip is-fraud" style="background:#fff7ed;color:#c2410c;border-color:#ffedd5;">Unbundling</span>';
        return `<tr>
          <td><strong>${escapeHtml(claim.claim_id)}</strong><br><span style="font-size:11px;color:var(--text-secondary);">${escapeHtml(claim.sep_number)}</span></td>
          <td style="max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escapeHtml(claim.doctor_notes)}">${escapeHtml(claim.doctor_notes)}</td>
          <td><code>${escapeHtml(claim.admin_billing_code)}</code></td>
          <td>${formatIdr(claim.total_charge)}</td>
          <td>${formatIdr(claim.approved_tariff)}</td>
          <td style="color:#059669;font-weight:700;">${formatIdr(claim.potential_saving)}</td>
          <td>${typeBadge}</td>
          <td><button class="button button-quiet" type="button" data-high-impact-id="${escapeHtml(claim.claim_id)}" style="font-size:11px;padding:4px 9px;">Periksa ↗</button></td>
        </tr>`;
      }).join("");

      highImpactBody.querySelectorAll("[data-high-impact-id]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const targetId = btn.dataset.highImpactId;
          const claim = analytics.high_impact_claims.find((c) => c.claim_id === targetId);
          if (claim) {
            setActiveClaim(claim.claim_id);
            openModal(claim, async () => {
              await loadDashboardData();
              await loadReportData();
              showToast("Keputusan verifikator tersimpan.");
            });
          }
        });
      });
    }

    // Regulation Sources & Rules
    const sourceNames = rules.map((rule) => rule.legal_source).filter(Boolean);
    state.reportSources = [...new Set(sourceNames.map(formatDocumentTitle).filter(Boolean))];
    const sourceList = document.getElementById("reportSourcesList");
    if (sourceList) {
      sourceList.innerHTML = state.reportSources.length
        ? state.reportSources.map((title) => `<li>${escapeHtml(title)}</li>`).join("")
        : "<li>Belum ada sumber regulasi yang tersedia.</li>";
    }
    const sourcesMetaEl = document.getElementById("reportSourcesMeta");
    if (sourcesMetaEl) {
      sourcesMetaEl.textContent = `${formatNumber(state.reportSources.length)} sumber regulasi tercatat pada Rule Engine.`;
    }
    const ruleCountEl = document.getElementById("reportRuleCount");
    if (ruleCountEl) {
      ruleCountEl.textContent = `${formatNumber(rules.length)} aturan tercatat di Rule Engine.`;
    }

    const coverage = Number(data.audit_coverage_pct) || 0;
    if (summary) {
      summary.innerHTML = `<strong>Ringkasan Audit Dataset:</strong> Dari <strong>${formatNumber(data.total_claims)} klaim</strong> aktif FKRTL, teridentifikasi <strong>${formatNumber(data.safe_claims)} klaim aman</strong> (65%) dan <strong>${formatNumber(data.fraud_claims)} klaim anomali</strong> (35%). Total akumulasi paparan tagihan mencapai <strong>${formatIdr(fin.total_charge || 0)}</strong> dengan estimasi penghematan dana JKN sebesar <strong>${formatIdr(data.total_potential_saving_idr)}</strong>. Cakupan verifikasi manusia saat ini berada pada level <strong>${coverage.toLocaleString("id-ID", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%</strong>.`;
    }

    renderAllAnalyticsCharts();
  } catch (error) {
    if (summary) summary.textContent = `Laporan tidak dapat dimuat: ${error.message}`;
    showToast(`Gagal memuat analitik: ${error.message}`, true);
  }
}

function exportReportPdf() {
  if (!window.jspdf?.jsPDF) {
    window.print();
    return;
  }
  const pdf = new window.jspdf.jsPDF({ orientation: "portrait", unit: "mm", format: "a4" });
  const data = state.stats || {};
  const fin = state.analyticsData?.financial_summary || {};
  pdf.setFont("helvetica", "bold");
  pdf.setFontSize(16);
  pdf.text("KlaimGuard AI · Laporan Eksekutif Analitik & Audit Medis", 14, 18);
  pdf.setFont("helvetica", "normal");
  pdf.setFontSize(10);
  const lines = [
    `Total Klaim Diaudit: ${formatNumber(data.total_claims)} (Total Tagihan: ${formatIdr(fin.total_charge || 0)})`,
    `Klaim Aman: ${formatNumber(data.safe_claims)} · Indikasi Anomali: ${formatNumber(data.fraud_claims)} (${formatNumber(data.upcoding_count)} Upcoding, ${formatNumber(data.unbundling_count)} Unbundling)`,
    `Potensi Penghematan Dana JKN: ${formatIdr(data.total_potential_saving_idr)}`,
    `Cakupan Verifikasi Manusia: ${(data.audit_coverage_pct || 0).toFixed(1)}%`,
  ];
  pdf.text(lines, 14, 28);
  
  let currentY = 54;
  ["financialComparisonChart", "losCorrelationChart", "costRiskDistChart", "topAnomaliesChart"].forEach((id) => {
    const canvas = document.getElementById(id);
    if (canvas && currentY < 235) {
      try {
        pdf.addImage(canvas.toDataURL("image/png"), "PNG", 14, currentY, 180, 50);
        currentY += 54;
      } catch (e) {
        // canvas might be empty or tainted
      }
    }
  });
  pdf.save("KlaimGuard-Laporan-Eksekutif-Analitik.pdf");
  showToast("Laporan PDF berhasil diunduh.");
}

async function analyzeManualClaim(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = document.getElementById("analyzeClaimBtn");
  const resultPanel = document.getElementById("manualResult");
  const values = new FormData(form);
  button.disabled = true;
  button.textContent = "Menganalisis…";
  try {
    const result = await analyzeClaim({
      claim_id: String(values.get("claim_id")).trim(),
      doctor_notes: String(values.get("doctor_notes")).trim(),
      admin_billing_code: String(values.get("admin_billing_code")).split(",").map((code) => code.trim()).filter(Boolean),
      length_of_stay: Number(values.get("length_of_stay")),
      total_charge: Number(values.get("total_charge")),
    });
    result.manual_only = true;
    resultPanel.classList.remove("hidden", "is-error");
    resultPanel.innerHTML = `<strong>${escapeHtml(result.is_fraud ? `FLAGGED · ${result.fraud_type || "anomali"}` : "AMAN")}</strong> · Skor risiko AI ${Math.round(Number(result.risk_score) * 100)}% · ${escapeHtml(result.reason_narrative)} <button class="detail-button" type="button" id="manualDetailButton">Lihat Detail ↗</button>`;
    document.getElementById("manualDetailButton").addEventListener("click", () => openModal(result, loadDashboardData));
  } catch (error) {
    resultPanel.classList.remove("hidden");
    resultPanel.classList.add("is-error");
    resultPanel.textContent = `Analisis gagal: ${error.message}`;
  } finally {
    button.disabled = false;
    button.textContent = "Analisis Klaim";
  }
}

bootstrap();
