import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, API_PREFIX } from "../services/api.js";

export const ADMIN_TOKEN_KEY = "securefacemeet_admin_access_token";

export function getAdminToken() {
  return localStorage.getItem(ADMIN_TOKEN_KEY);
}

export function setAdminToken(token) {
  if (token) localStorage.setItem(ADMIN_TOKEN_KEY, token);
  else localStorage.removeItem(ADMIN_TOKEN_KEY);
}

export default function AdminLogin() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [msg, setMsg] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setMsg("");
    setLoading(true);
    try {
      const { data } = await api.post(`${API_PREFIX}/admin/login`, { username: username.trim(), password });
      setAdminToken(data.access_token);
      navigate("/admin/users", { replace: true });
    } catch (err) {
      const detail = typeof err.response?.data?.detail === "string" ? err.response.data.detail : err.message || "";
      setMsg(detail || "Login denied.");
      setAdminToken("");
      navigate("/register")
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-md space-y-6 rounded-xl border border-slate-800 bg-slate-950/70 p-6">
      <div>
        <h1 className="text-2xl font-semibold text-white">Administrator access</h1>
        <p className="mt-2 text-sm text-slate-400">
          Credentials originate from backend environment (<span className="font-mono">ADMIN_USERNAME</span> ·{" "}
          <span className="font-mono">ADMIN_PASSWORD</span>). Issue a fresh token before every operations shift.
        </p>
      </div>
      <form className="space-y-4" onSubmit={submit}>
        <label className="block text-sm text-slate-300">
          Username
          <input className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white" value={username} onChange={(e) => setUsername(e.target.value)} />
        </label>
        <label className="block text-sm text-slate-300">
          Password
          <input
            type="password"
            className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <button
          disabled={loading}
          type="submit"
          className="w-full rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
        >
          {loading ? "Signing in…" : "Sign in"}
        </button>
        {msg && <p className="text-sm text-rose-300">{msg}</p>}
      </form>
    </div>
  );
}
