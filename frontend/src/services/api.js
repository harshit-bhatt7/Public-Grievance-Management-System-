/**
 * Centralized API service.
 *
 * Every backend call goes through this module rather than components
 * calling fetch() directly. `credentials: "include"` is required on
 * every call so the browser sends/receives the HttpOnly refresh-token
 * cookie set by the backend (see docs/architecture.md for the token
 * storage strategy).
 */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function request(path, { method = "GET", body, accessToken, isFormData = false } = {}) {
  const headers = {};
  if (!isFormData) {
    headers["Content-Type"] = "application/json";
  }
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    credentials: "include", // send/receive the HttpOnly refresh-token cookie
    body: isFormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (response.status === 204) {
    return null;
  }

  let data = null;
  try {
    data = await response.json();
  } catch {
    // No JSON body (e.g. some error responses) — that's fine.
  }

  if (!response.ok) {
    const message = (data && data.detail) || `Request to ${path} failed with status ${response.status}`;
    throw new ApiError(message, response.status, data && data.detail);
  }

  return data;
}

// --- Foundation (Step 1) ---

export function getApiStatus() {
  return request("/");
}

export function getHealth() {
  return request("/api/health");
}

export function getDatabaseHealth() {
  return request("/api/health/db");
}

// --- Authentication (Step 2) ---

export function registerCitizen({ name, email, phone, password }) {
  return request("/api/auth/register", {
    method: "POST",
    body: { name, email, phone: phone || null, password },
  });
}

export function login({ email, password }) {
  return request("/api/auth/login", {
    method: "POST",
    body: { email, password },
  });
}

/** Attempts to obtain a new access token using the HttpOnly refresh cookie. */
export function refreshSession() {
  return request("/api/auth/refresh", { method: "POST", body: {} });
}

export function logout() {
  return request("/api/auth/logout", { method: "POST", body: {} });
}

export function getCurrentUser(accessToken) {
  return request("/api/auth/me", { accessToken });
}

export { ApiError };

// --- Grievances (Step 3) ---

export function getCategories() {
  return request("/api/categories");
}

export function createGrievance(payload, accessToken) {
  return request("/api/grievances", {
    method: "POST",
    body: payload,
    accessToken,
  });
}

export function getMyGrievances(accessToken) {
  return request("/api/grievances/my", { accessToken });
}

export function getGrievance(grievanceNumber, accessToken) {
  return request(`/api/grievances/${encodeURIComponent(grievanceNumber)}`, { accessToken });
}

export function uploadAttachment(grievanceNumber, file, accessToken) {
  const formData = new FormData();
  formData.append("file", file);
  return request(`/api/grievances/${encodeURIComponent(grievanceNumber)}/attachments`, {
    method: "POST",
    body: formData,
    accessToken,
    isFormData: true,
  });
}

// --- Privacy (Step 6) ---

export function updateGrievancePrivacy(grievanceNumber, privacyMode, accessToken) {
  return request(`/api/grievances/${encodeURIComponent(grievanceNumber)}/privacy`, {
    method: "PATCH",
    body: { privacy_mode: privacyMode },
    accessToken,
  });
}

// --- Officer (Step 7) ---

export function getOfficerDashboard(accessToken) {
  return request("/api/officer/dashboard", { accessToken });
}

export function getOfficerGrievances(accessToken, filters = {}) {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.category_id) params.set("category_id", filters.category_id);
  if (filters.grievance_number) params.set("grievance_number", filters.grievance_number);
  const query = params.toString();
  return request(`/api/officer/grievances${query ? `?${query}` : ""}`, { accessToken });
}

export function getOfficerGrievanceDetail(grievanceNumber, accessToken) {
  return request(`/api/officer/grievances/${encodeURIComponent(grievanceNumber)}`, { accessToken });
}

export function claimGrievance(grievanceNumber, accessToken) {
  return request(`/api/officer/grievances/${encodeURIComponent(grievanceNumber)}/claim`, {
    method: "POST",
    body: {},
    accessToken,
  });
}

export function updateGrievanceStatusAsOfficer(grievanceNumber, statusValue, remarks, accessToken) {
  return request(`/api/officer/grievances/${encodeURIComponent(grievanceNumber)}/status`, {
    method: "POST",
    body: { status: statusValue, remarks: remarks || null },
    accessToken,
  });
}

// --- Step 9 AI Intelligence ---
export function analyzeAIGrievance(grievanceNumber, accessToken) {
  return request(`/api/ai/grievances/${encodeURIComponent(grievanceNumber)}/analyze`, { method: "POST", body: {}, accessToken });
}
export function getAISummary(grievanceNumber, accessToken) {
  return request(`/api/ai/grievances/${encodeURIComponent(grievanceNumber)}/summary`, { method: "POST", body: {}, accessToken });
}
export function getAIPriority(grievanceNumber, accessToken) {
  return request(`/api/ai/grievances/${encodeURIComponent(grievanceNumber)}/priority`, { method: "POST", body: {}, accessToken });
}
export function getAIDuplicates(grievanceNumber, accessToken) {
  return request(`/api/ai/grievances/${encodeURIComponent(grievanceNumber)}/duplicates`, { method: "POST", body: {}, accessToken });
}
export function getAICopilot(grievanceNumber, accessToken) {
  return request(`/api/ai/grievances/${encodeURIComponent(grievanceNumber)}/copilot`, { method: "POST", body: {}, accessToken });
}
export function getAIResponseDraft(grievanceNumber, accessToken) {
  return request(`/api/ai/grievances/${encodeURIComponent(grievanceNumber)}/response-draft`, { method: "POST", body: {}, accessToken });
}
export function getAIResolutionAnalysis(grievanceNumber, evidence, accessToken) {
  return request(`/api/ai/grievances/${encodeURIComponent(grievanceNumber)}/resolution-analysis`, { method: "POST", body: { evidence }, accessToken });
}
export function getAISLARisk(grievanceNumber, accessToken) {
  return request(`/api/ai/grievances/${encodeURIComponent(grievanceNumber)}/sla-risk`, { method: "POST", body: {}, accessToken });
}
export function reviewAIRecommendation(recommendationId, state, remarks, accessToken) {
  return request(`/api/ai/recommendations/${encodeURIComponent(recommendationId)}/review`, { method: "POST", body: { state, remarks: remarks || null }, accessToken });
}
export function askCitizenAIAssistant(question, grievanceNumber, accessToken) {
  return request("/api/ai/assistant", { method: "POST", body: { question, grievance_number: grievanceNumber || null }, accessToken });
}
export function transcribeVoiceText(reviewedText, language, accessToken) {
  return request("/api/ai/transcribe", { method: "POST", body: { reviewed_text: reviewedText || null, language: language || null }, accessToken });
}
export function getAIAnalytics(accessToken) { return request("/api/ai/analytics", { accessToken }); }
export function getAIHotspots(accessToken) { return request("/api/ai/hotspots", { accessToken }); }
export function getAIEmergingIssues(accessToken) { return request("/api/ai/emerging-issues", { accessToken }); }
export function getAIAlerts(accessToken) { return request("/api/ai/alerts", { accessToken }); }
export function getAICategorySuggestion(grievanceNumber, accessToken) {
  return request(`/api/ai/grievances/${encodeURIComponent(grievanceNumber)}/category-suggestion`, { method: "POST", body: {}, accessToken });
}

// --- Step 10 Resolution & Citizen Verification ---
export function getResolutionReview(grievanceNumber, accessToken) {
  return request(`/api/grievances/${encodeURIComponent(grievanceNumber)}/resolutions`, { accessToken });
}

export function getResolution(grievanceNumber, accessToken) {
  return request(`/api/grievances/${encodeURIComponent(grievanceNumber)}/resolution`, { accessToken });
}

export function acceptResolution(grievanceNumber, accessToken) {
  return request(`/api/grievances/${encodeURIComponent(grievanceNumber)}/resolution/accept`, {
    method: "POST",
    body: {},
    accessToken,
  });
}

export function disputeResolution(grievanceNumber, reason, accessToken) {
  return request(`/api/grievances/${encodeURIComponent(grievanceNumber)}/resolution/dispute`, {
    method: "POST",
    body: { reason },
    accessToken,
  });
}

export function submitResolutionFeedback(grievanceNumber, { rating, feedback }, accessToken) {
  return request(`/api/grievances/${encodeURIComponent(grievanceNumber)}/feedback`, {
    method: "POST",
    body: { accepted: false, rating: rating || null, feedback: feedback || null },
    accessToken,
  });
}

export function submitOfficerResolution(grievanceNumber, payload, files, accessToken) {
  const formData = new FormData();
  formData.append("resolution_summary", payload.resolution_summary);
  formData.append("actions_taken", payload.actions_taken);
  formData.append("resolution_date", payload.resolution_date);
  if (payload.remarks) formData.append("remarks", payload.remarks);
  if (payload.completion_percentage !== "" && payload.completion_percentage != null) {
    formData.append("completion_percentage", String(payload.completion_percentage));
  }
  if (payload.external_reference) formData.append("external_reference", payload.external_reference);
  (files || []).forEach((file) => formData.append("evidence", file));
  return request(`/api/officer/grievances/${encodeURIComponent(grievanceNumber)}/resolution`, {
    method: "POST",
    body: formData,
    accessToken,
    isFormData: true,
  });
}

export function getOfficerResolutions(grievanceNumber, accessToken) {
  return request(`/api/officer/grievances/${encodeURIComponent(grievanceNumber)}/resolutions`, { accessToken });
}

export async function downloadResolutionEvidence(grievanceNumber, evidenceId, accessToken, officer = false) {
  const prefix = officer ? "/api/officer" : "/api";
  const response = await fetch(
    `${API_BASE_URL}${prefix}/grievances/${encodeURIComponent(grievanceNumber)}/resolutions/evidence/${encodeURIComponent(evidenceId)}`,
    { credentials: "include", headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {} }
  );
  if (!response.ok) {
    let detail = "Could not download evidence.";
    try { const data = await response.json(); detail = data.detail || detail; } catch {}
    throw new ApiError(detail, response.status, detail);
  }
  return response.blob();
}

// --- Step 11 Admin Governance ---
export function getAdminDashboard(accessToken) { return request("/api/admin/dashboard", { accessToken }); }
export function getAdminGrievances(accessToken, filters={}) {
  const p=new URLSearchParams(); Object.entries(filters).forEach(([k,v])=>{if(v!==undefined&&v!==null&&v!=="")p.set(k,v)});
  return request(`/api/admin/grievances${p.toString()?`?${p}`:""}`,{accessToken});
}
export function getAdminOfficers(accessToken){return request("/api/admin/officers",{accessToken});}
export function createAdminOfficer(payload,accessToken){return request("/api/admin/officers",{method:"POST",body:payload,accessToken});}
export function updateAdminOfficer(id,payload,accessToken){return request(`/api/admin/officers/${id}`,{method:"PATCH",body:payload,accessToken});}
export function deactivateAdminOfficer(id,accessToken){return request(`/api/admin/officers/${id}/deactivate`,{method:"POST",body:{},accessToken});}
export function getAdminDepartments(accessToken){return request("/api/admin/departments",{accessToken});}
export function createAdminDepartment(payload,accessToken){return request("/api/admin/departments",{method:"POST",body:payload,accessToken});}
export function updateAdminDepartment(id,payload,accessToken){return request(`/api/admin/departments/${id}`,{method:"PATCH",body:payload,accessToken});}
export function deactivateAdminDepartment(id,accessToken){return request(`/api/admin/departments/${id}/deactivate`,{method:"POST",body:{},accessToken});}
export function getAdminCategories(accessToken){return request("/api/admin/categories",{accessToken});}
export function createAdminCategory(payload,accessToken){return request("/api/admin/categories",{method:"POST",body:payload,accessToken});}
export function updateAdminCategory(id,payload,accessToken){return request(`/api/admin/categories/${id}`,{method:"PATCH",body:payload,accessToken});}
export function deactivateAdminCategory(id,accessToken){return request(`/api/admin/categories/${id}/deactivate`,{method:"POST",body:{},accessToken});}
export function getAdminPrivacyRequests(accessToken){return request("/api/admin/privacy/requests",{accessToken});}
export function approveAdminPrivacyRequest(id,remarks,accessToken){return request(`/api/admin/privacy/requests/${id}/approve`,{method:"POST",body:{approve:true,remarks:remarks||null},accessToken});}
export function rejectAdminPrivacyRequest(id,remarks,accessToken){return request(`/api/admin/privacy/requests/${id}/reject`,{method:"POST",body:{approve:false,remarks:remarks||null},accessToken});}
export function getAdminAudit(accessToken,filters={}){const p=new URLSearchParams();Object.entries(filters).forEach(([k,v])=>{if(v)p.set(k,v)});return request(`/api/admin/audit${p.toString()?`?${p}`:""}`,{accessToken});}
export function verifyAdminAudit(accessToken){return request("/api/admin/audit/verify",{accessToken});}
export function getAdminAI(accessToken){return request("/api/admin/ai",{accessToken});}
export function getAdminAnalytics(accessToken){return request("/api/admin/analytics",{accessToken});}
export function getAdminPublicStatisticsGovernance(accessToken){return request("/api/admin/public-statistics/governance",{accessToken});}
export function getAdminResolutions(accessToken){return request("/api/admin/resolutions",{accessToken});}

// --- Step 12 Notifications ---
export function getNotifications(accessToken) { return request('/api/notifications', { accessToken }); }
export function getUnreadNotificationCount(accessToken) { return request('/api/notifications/unread-count', { accessToken }); }
export function markNotificationRead(id, accessToken) { return request(`/api/notifications/${id}/read`, { method:'POST', body:{}, accessToken }); }
export function markAllNotificationsRead(accessToken) { return request('/api/notifications/read-all', { method:'POST', body:{}, accessToken }); }
export function getNotificationPreferences(accessToken) { return request('/api/notifications/preferences', { accessToken }); }
export function updateNotificationPreferences(payload, accessToken) { return request('/api/notifications/preferences', { method:'PATCH', body:payload, accessToken }); }
export function getNotificationConfig(accessToken) { return request('/api/notifications/config', { accessToken }); }
export function subscribePush(subscription, accessToken) { const json=subscription.toJSON(); return request('/api/notifications/push/subscribe', { method:'POST', body:{ endpoint:json.endpoint, p256dh:json.keys.p256dh, auth:json.keys.auth }, accessToken }); }
export function unsubscribePush(endpoint, accessToken) { return request(`/api/notifications/push/subscribe?endpoint=${encodeURIComponent(endpoint)}`, { method:'DELETE', accessToken }); }

// --- Step 13 Public Statistics ---
export function getPublicStatistics(params = {}) { const q=new URLSearchParams(params).toString(); return request(`/api/public/statistics/summary${q?`?${q}`:""}`); }
export function getPublicLocations(params = {}) { const q=new URLSearchParams(params).toString(); return request(`/api/public/statistics/location${q?`?${q}`:""}`); }
export function getPublicTrends(params = {}) { const q=new URLSearchParams(params).toString(); return request(`/api/public/statistics/trends${q?`?${q}`:""}`); }
export function getPublicCategories(params = {}) { const q=new URLSearchParams(params).toString(); return request(`/api/public/statistics/categories${q?`?${q}`:""}`); }
export function getPublicDepartments(params = {}) { const q=new URLSearchParams(params).toString(); return request(`/api/public/statistics/departments${q?`?${q}`:""}`); }
export function getPublicRankings(params = {}) { const q=new URLSearchParams(params).toString(); return request(`/api/public/statistics/rankings${q?`?${q}`:""}`); }

export function getPublicMostImproved(params = {}) { const q=new URLSearchParams(params).toString(); return request(`/api/public/statistics/most-improved${q?`?${q}`:""}`); }
export function getPublicCategoryRankings(params = {}) { const { level="district", category_id, ...rest }=params; const q=new URLSearchParams(rest).toString(); return request(`/api/public/statistics/rankings/${level}/category/${category_id}${q?`?${q}`:""}`); }

// --- Step 14 Government Projects ---
export function getPublicProjects(filters = {}) { const p=new URLSearchParams(); Object.entries(filters).forEach(([k,v])=>{if(v!==undefined&&v!==null&&v!=='')p.set(k,v)}); return request(`/api/public/projects${p.toString()?`?${p}`:''}`); }
export function getPublicProject(id, accessToken) { return request(`/api/public/projects/${encodeURIComponent(id)}`, { accessToken }); }
export function getPublicProjectCategories() { return request('/api/public/projects/categories'); }
export function getPublicProjectDepartments() { return request('/api/public/projects/departments'); }
export function getPublicProjectStatistics() { return request('/api/public/projects/statistics'); }
export function getPublicProjectPerformance() { return request('/api/public/projects/performance'); }
export function followProject(id, accessToken) { return request(`/api/projects/${encodeURIComponent(id)}/follow`, {method:'POST',body:{},accessToken}); }
export function unfollowProject(id, accessToken) { return request(`/api/projects/${encodeURIComponent(id)}/follow`, {method:'DELETE',accessToken}); }
export function getFollowingProjects(accessToken) { return request('/api/projects/following',{accessToken}); }
export function getAdminProjects(accessToken) { return request('/api/admin/projects',{accessToken}); }
export function createAdminProject(payload, accessToken) { return request('/api/admin/projects',{method:'POST',body:payload,accessToken}); }
export function updateAdminProject(id,payload,accessToken) { return request(`/api/admin/projects/${encodeURIComponent(id)}`,{method:'PATCH',body:payload,accessToken}); }
export function addProjectMilestone(id,payload,accessToken) { return request(`/api/admin/projects/${encodeURIComponent(id)}/milestones`,{method:'POST',body:payload,accessToken}); }
export function updateProjectMilestone(id,mid,payload,accessToken) { return request(`/api/admin/projects/${encodeURIComponent(id)}/milestones/${encodeURIComponent(mid)}`,{method:'PATCH',body:payload,accessToken}); }
export function linkProjectGrievance(id,grievance_id,accessToken) { return request(`/api/admin/projects/${encodeURIComponent(id)}/grievances?grievance_id=${encodeURIComponent(grievance_id)}`,{method:'POST',body:{},accessToken}); }
export function uploadProjectDocument(id,file,meta,accessToken) { const f=new FormData(); f.append('file',file); if(meta?.document_type)f.append('document_type',meta.document_type); f.append('is_public',String(meta?.is_public!==false)); return request(`/api/admin/projects/${encodeURIComponent(id)}/documents`,{method:'POST',body:f,accessToken,isFormData:true}); }
export function uploadProjectPhoto(id,file,meta,accessToken) { const f=new FormData(); f.append('file',file); Object.entries(meta||{}).forEach(([k,v])=>{if(v!==undefined&&v!==null)f.append(k,String(v))}); return request(`/api/admin/projects/${encodeURIComponent(id)}/photos`,{method:'POST',body:f,accessToken,isFormData:true}); }

// --- Step 15 Existing Work Intelligence ---
export function checkExistingWork(payload, accessToken) {
  return request('/api/grievances/check-existing-work', { method:'POST', body:payload, accessToken });
}
export function getRelatedWork(grievanceNumber, accessToken) {
  return request(`/api/grievances/${encodeURIComponent(grievanceNumber)}/related-work`, { accessToken });
}
export function recordExistingWorkAction(grievanceNumber, action, matchIds, accessToken) {
  return request(`/api/grievances/${encodeURIComponent(grievanceNumber)}/existing-work-action`, {
    method:'POST', body:{action, match_ids:matchIds || []}, accessToken
  });
}
export function getOfficerPossibleMatches(grievanceNumber, accessToken) {
  return request(`/api/officer/grievances/${encodeURIComponent(grievanceNumber)}/possible-matches`, { accessToken });
}
export function reviewExistingWorkMatch(matchId, state, accessToken) {
  return request(`/api/officer/matches/${encodeURIComponent(matchId)}/review`, {method:'POST', body:{state}, accessToken});
}
