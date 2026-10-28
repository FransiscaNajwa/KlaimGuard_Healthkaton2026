const API_ROOT = "/api/v1";

async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    credentials: "same-origin",
    headers: { Accept: "application/json", ...options.headers },
  });
  if (response.status === 204) return null;

  const contentType = response.headers.get("content-type") || "";
  const responseText = await response.text();
  let body = responseText;
  if (responseText && contentType.includes("application/json")) {
    try {
      body = JSON.parse(responseText);
    } catch {
      throw new Error("Server mengirim respons JSON yang tidak valid.");
    }
  }
  if (!response.ok) {
    const detail = typeof body === "object" ? body.detail || body.message : body;
    if (Array.isArray(detail)) {
      const isResponseValidation = detail.some((item) => item?.loc?.[0] === "response");
      if (isResponseValidation) {
        throw new Error("Format jawaban chatbot dari server tidak sesuai. Muat ulang aplikasi; jika masih muncul, restart backend.");
      }
      const messages = detail.map((item) => item?.msg).filter(Boolean);
      throw new Error(messages.join("; ") || `Request gagal (${response.status}).`);
    }
    const message = typeof detail === "string" ? detail : body?.message;
    throw new Error(message || `Request gagal (${response.status}).`);
  }
  return body;
}

export function login(username, password) {
  return request(`${API_ROOT}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
}

export function logout() {
  return request(`${API_ROOT}/auth/logout`, { method: "POST" });
}

export function getCurrentUser() {
  return request(`${API_ROOT}/auth/me`);
}

export function getStats() {
  return request(`${API_ROOT}/stats/overview`);
}

export function getAnalytics() {
  return request(`${API_ROOT}/stats/analytics`);
}

export function getClaims(page, limit, search = "", status = "", fraudType = "") {
  const params = new URLSearchParams({ skip: String((page - 1) * limit), limit: String(limit) });
  if (search.trim()) params.set("search", search.trim());
  if (status) params.set("status", status);
  if (fraudType) params.set("fraud_type", fraudType);
  return request(`${API_ROOT}/claims/?${params}`);
}

export function getAuditLogs(page = 1, limit = 10) {
  return request(`${API_ROOT}/audit/logs?${new URLSearchParams({ page: String(page), limit: String(limit) })}`);
}
export function getHospitalActivity(page = 1, limit = 50) {
  return request(`${API_ROOT}/audit/hospital-activity?${new URLSearchParams({ page: String(page), limit: String(limit) })}`);
}

export function getClaimDetail(claimId) {
  return request(`${API_ROOT}/claims/${encodeURIComponent(claimId)}`);
}

export function getRules() {
  return request(`${API_ROOT}/rules/`);
}

export function getRegulationsStatus() {
  return request(`${API_ROOT}/copilot/regulations-status`);
}

export function runBatchAudit(limit = 100) {
  return request(`${API_ROOT}/claims/simulate-batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ limit }),
  });
}

export function postFeedback(payload) {
  return request(`${API_ROOT}/feedback/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function queryRAGCopilot(query, claimId = null) {
  return request(`${API_ROOT}/copilot/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, claim_id: claimId }),
  });
}

export function draftDispute(claimId) {
  return request(`${API_ROOT}/copilot/draft-dispute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ claim_id: claimId }),
  });
}

export function getDisputes(status = "") {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  return request(API_ROOT + "/disputes/?" + params);
}

export function deleteDispute(disputeId) {
  return request(API_ROOT + "/disputes/" + encodeURIComponent(disputeId), { method: "DELETE" });
}

export function getDisputeSummary() {
  return request(API_ROOT + "/disputes/summary");
}

export function createDispute(claimId, templateCode = "formal") {
  return request(API_ROOT + "/disputes/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ claim_id: claimId, template_code: templateCode }),
  });
}

export function addDisputeComment(disputeId, body) {
  return request(API_ROOT + "/disputes/" + encodeURIComponent(disputeId) + "/comments", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ body }),
  });
}

export function updateDispute(disputeId, letterBody) {
  return request(API_ROOT + "/disputes/" + encodeURIComponent(disputeId), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ letter_body: letterBody }),
  });
}

export function submitDispute(disputeId) {
  return request(API_ROOT + "/disputes/" + encodeURIComponent(disputeId) + "/submit", { method: "POST" });
}

export function reviewDispute(disputeId, action, notes = "") {
  return request(API_ROOT + "/disputes/" + encodeURIComponent(disputeId) + "/review", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, notes }),
  });
}

export function markDisputeSent(disputeId, recipient, submissionReference) {
  return request(API_ROOT + "/disputes/" + encodeURIComponent(disputeId) + "/sent", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ recipient, submission_reference: submissionReference }),
  });
}

export function getRsDashboard() { return request(`${API_ROOT}/rs/dashboard`); }
export function getRsClarifications() { return request(`${API_ROOT}/rs/clarifications`); }
export function getRsClarification(id) { return request(`${API_ROOT}/rs/clarifications/${encodeURIComponent(id)}`); }
export function saveRsResponse(id, explanationType, notes) {
  return request(`${API_ROOT}/rs/clarifications/${encodeURIComponent(id)}/response`, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ explanation_type: explanationType, notes }),
  });
}
export function uploadRsDocument(id, file) {
  const data = new FormData(); data.append("file", file);
  return request(`${API_ROOT}/rs/clarifications/${encodeURIComponent(id)}/documents`, { method: "POST", body: data });
}
export function submitRsResponse(id) {
  return request(`${API_ROOT}/rs/clarifications/${encodeURIComponent(id)}/submit`, { method: "POST" });
}
export function getRsProfile() { return request(`${API_ROOT}/rs/profile`); }
export function getFacilities() { return request(`${API_ROOT}/facilities`); }
export function searchFacilityClaims(search = "") {
  return request(`${API_ROOT}/facilities/claim-options?${new URLSearchParams({ search })}`);
}
export function createFacility(payload) {
  return request(`${API_ROOT}/facilities`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
export function reevaluateDispute(id, action, notes = "") {
  return request(`${API_ROOT}/disputes/${encodeURIComponent(id)}/reevaluate`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, notes }),
  });
}

export function analyzeClaim(payload) {
  return request(`${API_ROOT}/claims/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
