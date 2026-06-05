import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getAdminToken } from "./AdminLogin.jsx";
import { api, API_PREFIX } from "../services/api.js";

function authBearer() {
  const token = getAdminToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

const FILTERS = [
  { id: "qualified", label: "Fully qualified", hint: "90%+ dwell + face threshold + completed normally" },
  { id: "dwell_only", label: "90%+ dwell only", hint: "Met scheduled meeting time threshold (may lack face)" },
  { id: "all", label: "Everyone logged", hint: "All attendance rows for this room" },
];

function parseFilenameFromDisposition(cd) {
  if (!cd || typeof cd !== "string") return null;
  const mStar = cd.match(/filename\*=UTF-8''([^;]+)/i);
  if (mStar) {
    try {
      return decodeURIComponent(mStar[1].trim());
    } catch {
      return mStar[1].trim();
    }
  }
  const m = cd.match(/filename="([^"]+)"/i);
  if (m) return m[1];
  const m2 = cd.match(/filename=([^;\s]+)/i);
  return m2 ? m2[1] : null;
}

export default function AdminParticipants() {
  const navigate = useNavigate();
  const [roomId, setRoomId] = useState("");
  const [filterMode, setFilterMode] = useState("qualified");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [exportBusy, setExportBusy] = useState("");

  useEffect(() => {
    if (!getAdminToken()) navigate("/admin/login", { replace: true });
  }, [navigate]);

  const fetchParticipants = async () => {
    const rid = roomId.trim();
    if (!rid) {
      setError("Enter a room / meeting identifier.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const { data } = await api.get(`${API_PREFIX}/admin/participants/room/${encodeURIComponent(rid)}`, {
        headers: authBearer(),
        params: { filter_mode: filterMode },
      });
      setRows(Array.isArray(data) ? data : []);
    } catch (e) {
      const msg = e?.response?.data?.detail;
      setError(typeof msg === "string" ? msg : e?.message || "Failed to load participants.");
      setRows([]);
    } finally {
      setLoading(false);
    }
  };

  const downloadExport = async (fmt) => {
    const rid = roomId.trim();
    if (!rid) {
      setError("Enter a room / meeting identifier before exporting.");
      return;
    }
    setExportBusy(fmt);
    setError("");
    try {
      const res = await api.get(`${API_PREFIX}/admin/participants/room/${encodeURIComponent(rid)}/export`, {
        headers: authBearer(),
        params: { fmt, filter_mode: filterMode },
        responseType: "blob",
      });
      const blob = new Blob([res.data], { type: res.headers["content-type"] || "application/octet-stream" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download =
        parseFilenameFromDisposition(res.headers["content-disposition"]) || `participants_${rid}_${filterMode}.${fmt}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      let msg = e?.message || "Export failed.";
      if (e?.response?.data instanceof Blob) {
        try {
          const text = await e.response.data.text();
          const parsed = JSON.parse(text);
          if (typeof parsed?.detail === "string") msg = parsed.detail;
        } catch {
          /* ignore */
        }
      }
      setError(msg);
    } finally {
      setExportBusy("");
    }
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-white">Meeting participants</h2>
        <p className="mt-1 text-sm text-slate-400">
          Enter the Jitsi room ID used for the session (same value teachers configure in Virtual class studio). Scheduled
          classes apply the 90% dwell rule against the planned start/end; ad-hoc rooms treat dwell as satisfied for logging.
        </p>
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 shadow-inner shadow-black/30">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex min-w-[200px] flex-1 flex-col gap-1 text-sm">
            <span className="text-slate-400">Room ID</span>
            <input
              value={roomId}
              onChange={(e) => setRoomId(e.target.value)}
              placeholder="e.g. securefacemeet-room-abc"
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none ring-emerald-500/40 focus:ring-2"
            />
          </label>
          <label className="flex min-w-[220px] flex-col gap-1 text-sm">
            <span className="text-slate-400">Filter</span>
            <select
              value={filterMode}
              onChange={(e) => setFilterMode(e.target.value)}
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none ring-emerald-500/40 focus:ring-2"
            >
              {FILTERS.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={fetchParticipants}
            disabled={loading}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
          >
            {loading ? "Loading…" : "Load"}
          </button>
        </div>
        <p className="mt-3 text-xs text-slate-500">
          {FILTERS.find((f) => f.id === filterMode)?.hint}
        </p>
        {error ? <p className="mt-3 text-sm text-rose-300">{error}</p> : null}

        <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-800 pt-4">
          <span className="self-center text-xs uppercase tracking-wider text-slate-500">Export</span>
          {["csv", "xlsx", "pdf"].map((fmt) => (
            <button
              key={fmt}
              type="button"
              disabled={!!exportBusy}
              onClick={() => downloadExport(fmt)}
              className="rounded-md border border-slate-700 bg-slate-800/80 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700 disabled:opacity-50"
            >
              {exportBusy === fmt ? "Preparing…" : fmt.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/30">
        <table className="min-w-full divide-y divide-slate-800 text-left text-sm">
          <thead className="bg-slate-900/80 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-3 py-2">ID</th>
              <th className="px-3 py-2">Name</th>
              <th className="px-3 py-2">Enroll ID</th>
              <th className="px-3 py-2">Class</th>
              <th className="px-3 py-2">Dwell %</th>
              <th className="px-3 py-2">Face OK</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Join</th>
              <th className="px-3 py-2">Exit</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800 text-slate-200">
            {rows.length === 0 && !loading ? (
              <tr>
                <td colSpan={9} className="px-3 py-8 text-center text-slate-500">
                  No rows yet. Enter a room ID and choose Load.
                </td>
              </tr>
            ) : (
              rows.map((r) => (
                <tr key={r.log_id} className="hover:bg-slate-800/40">
                  <td className="px-3 py-2 font-mono text-xs text-slate-300">{r.user_id}</td>
                  <td className="px-3 py-2">
                    <div className="font-medium text-white">{r.full_name}</div>
                    <div className="text-xs text-slate-500">{r.email}</div>
                  </td>
                  <td className="px-3 py-2 text-slate-300">{r.student_external_id || "—"}</td>
                  <td className="px-3 py-2 text-slate-300">{r.student_class || "—"}</td>
                  <td className="px-3 py-2 tabular-nums">{r.dwell_percent != null ? `${r.dwell_percent}%` : "—"}</td>
                  <td className="px-3 py-2">{r.meets_face_threshold ? "Yes" : "No"}</td>
                  <td className="px-3 py-2">
                    <span
                      className={
                        r.status === "valid"
                          ? "text-emerald-400"
                          : r.status === "removed"
                            ? "text-amber-400"
                            : "text-slate-400"
                      }
                    >
                      {r.status}
                    </span>
                  </td>
                  <td className="max-w-[140px] truncate px-3 py-2 text-xs text-slate-400">{r.join_time || "—"}</td>
                  <td className="max-w-[140px] truncate px-3 py-2 text-xs text-slate-400">{r.exit_time || "—"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
