import axios from "axios";

/**
 * In Vite dev, default to same-origin requests so `/api/*` is proxied (vite.config.js)
 * and you avoid localhost vs 127.0.0.1 CORS mismatches. Set VITE_API_BASE_URL for a
 * direct backend URL. Production builds should set VITE_API_BASE_URL unless API is same-host.
 */
function apiBaseUrl() {
  const fromEnv = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "");
  if (fromEnv) return fromEnv;
  if (import.meta.env.DEV) return "";
  return "http://127.0.0.1:8000";
}

export const api = axios.create({
  baseURL: apiBaseUrl(),
  timeout: 120000,
});

export const API_PREFIX = "/api/v1";

export function authHeader(token) {
  return token ? { Authorization: `Bearer ${token}` } : {};
}
