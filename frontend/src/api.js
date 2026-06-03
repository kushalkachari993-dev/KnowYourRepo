const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

function authHeaders() {
  const token = localStorage.getItem("kyr_access_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...authHeaders(),
      ...(options.headers || {}),
    },
  });

  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await response.json() : await response.text();

  if (!response.ok) {
    const detail = typeof data === "object" ? data.detail || data.message : data;
    throw new Error(detail || `Request failed with status ${response.status}`);
  }

  return data;
}

export const api = {
  config: () => request("/api/config"),
  status: () => request("/api/status"),
  signIn: (email, password) =>
    request("/api/auth/sign-in", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  signUp: (email, password) =>
    request("/api/auth/sign-up", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  signOut: () => request("/api/auth/sign-out", { method: "POST" }),
  estimateSource: (sourceUrl) =>
    request("/api/sources/estimate", {
      method: "POST",
      body: JSON.stringify({ source_url: sourceUrl }),
    }),
  ingestSource: (sourceUrl, sessionId) =>
    request("/api/ingest/source", {
      method: "POST",
      body: JSON.stringify({ source_url: sourceUrl, session_id: sessionId }),
    }),
  uploadFiles: (files, sessionId) => {
    const formData = new FormData();
    formData.append("session_id", sessionId);
    Array.from(files).forEach((file) => formData.append("files", file));
    return request("/api/ingest/upload", {
      method: "POST",
      body: formData,
    });
  },
  job: (jobId, sessionId) => request(`/api/jobs/${encodeURIComponent(jobId)}?session_id=${encodeURIComponent(sessionId)}`),
  search: ({ query, sessionId, topK, similarityThreshold }) =>
    request("/api/search", {
      method: "POST",
      body: JSON.stringify({
        query,
        session_id: sessionId,
        top_k: topK,
        similarity_threshold: similarityThreshold,
      }),
    }),
  chat: (question, chunks) =>
    request("/api/chat", {
      method: "POST",
      body: JSON.stringify({ question, chunks }),
    }),
};
