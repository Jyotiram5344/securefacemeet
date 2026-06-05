import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ADMIN_TOKEN_KEY, getAdminToken, setAdminToken } from "./AdminLogin.jsx";
import { api, API_PREFIX } from "../services/api.js";

const ROLE_PRESETS = ["A", "B", "FACULTY", "CSE-A", "CS-E", "IT-A"];

function authBearer() {
  const token = getAdminToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export default function AdminUsers() {
  const navigate = useNavigate();
  const [rows, setRows] = useState([]);
  const [metaClasses, setMetaClasses] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [enabledFilter, setEnabledFilter] = useState("");
  const [classFilter, setClassFilter] = useState("");
  const [previewId, setPreviewId] = useState(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [bulkIds, setBulkIds] = useState(() => new Set());
  const [bulkBusy, setBulkBusy] = useState(false);

  useEffect(() => {
    if (!getAdminToken()) navigate("/admin/login", { replace: true });
  }, [navigate]);

  useEffect(() => {
    let active = true;
    const loadMeta = async () => {
      const sessionToken = getAdminToken();
      if (!sessionToken) return;
      try {
        const { data } = await api.get(`${API_PREFIX}/admin/meta/student-classes`, {
          headers: authBearer(),
        });
        if (active) setMetaClasses(Array.isArray(data) ? data : []);
      } catch (_e) {
        if (active) setMetaClasses([]);
      }
    };
    loadMeta();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    const hydrate = async () => {
      const sessionToken = getAdminToken();
      if (!sessionToken) return;
      setLoading(true);
      setError("");
      try {
        const params = {};
        if (query.trim()) params.q = query.trim();
        if (roleFilter) params.role = roleFilter;
        if (classFilter) params.student_class = classFilter;
        if (enabledFilter === "true") params.enabled = true;
        if (enabledFilter === "false") params.enabled = false;
        const { data } = await api.get(`${API_PREFIX}/admin/users`, {
          headers: authBearer(),
          params,
        });
        if (active) {
          const list = Array.isArray(data) ? data : [];
          setRows(list);
          setBulkIds((prev) => {
            const next = new Set();
            prev.forEach((id) => {
              if (list.some((r) => r.id === id)) next.add(id);
            });
            return next;
          });
        }
      } catch (err) {
        if (active) setError(typeof err.response?.data?.detail === "string" ? err.response.data.detail : err.message || "");
        if (err.response?.status === 401) {
          setAdminToken("");
          navigate("/admin/login", { replace: true });
        }
      } finally {
        if (active) setLoading(false);
      }
    };
    hydrate();
    return () => {
      active = false;
    };
  }, [query, roleFilter, enabledFilter, classFilter, navigate]);

  useEffect(() => {
    const sessionToken = getAdminToken();
    if (!previewId || !sessionToken) {
      setPreviewUrl("");
      return undefined;
    }
    let revoked = false;
    const loadPreview = async () => {
      try {
        const res = await api.get(`${API_PREFIX}/admin/users/${previewId}/face`, {
          headers: authBearer(),
          responseType: "blob",
        });
        if (revoked) return;
        const url = URL.createObjectURL(res.data);
        setPreviewUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          return url;
        });
      } catch {
        setPreviewUrl("");
      }
    };
    loadPreview();
    return () => {
      revoked = true;
      setPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return "";
      });
    };
  }, [previewId]);

  const classOptions = useMemo(() => Array.from(new Set([...ROLE_PRESETS, ...metaClasses])).sort(), [metaClasses]);

  const toggleBulk = (id) => {
    setBulkIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const allRowsSelected = rows.length > 0 && rows.every((r) => bulkIds.has(r.id));

  const toggleSelectAllRows = () => {
    setBulkIds((prev) => {
      if (allRowsSelected) return new Set();
      return new Set(rows.map((r) => r.id));
    });
  };

  const patchUserClass = async (row, raw) => {
    const label = String(raw || "").trim().toUpperCase();
    await api.patch(
      `${API_PREFIX}/admin/users/${row.id}`,
      { student_class: label || null },
      { headers: { ...authBearer(), "Content-Type": "application/json" } }
    );
    setRows((prev) => prev.map((r) => (r.id === row.id ? { ...r, student_class: label || null } : r)));
  };

  const toggleEnabled = async (row, nextValue) => {
    await api.patch(
      `${API_PREFIX}/admin/users/${row.id}`,
      { is_enabled: nextValue },
      { headers: { ...authBearer(), "Content-Type": "application/json" } }
    );
    setRows((prev) => prev.map((r) => (r.id === row.id ? { ...r, is_enabled: nextValue } : r)));
  };

  const changeRole = async (row, newRole) => {
    await api.patch(
      `${API_PREFIX}/admin/users/${row.id}`,
      { role: newRole },
      { headers: { ...authBearer(), "Content-Type": "application/json" } }
    );
    setRows((prev) => prev.map((r) => (r.id === row.id ? { ...r, role: newRole } : r)));
  };

  const removeUser = async (row) => {
    if (!window.confirm(`Irreversible delete for ${row.full_name}?`)) return;
    await api.delete(`${API_PREFIX}/admin/users/${row.id}`, { headers: authBearer() });
    setRows((prev) => prev.filter((r) => r.id !== row.id));
    setBulkIds((prev) => {
      const next = new Set(prev);
      next.delete(row.id);
      return next;
    });
    setPreviewId((current) => (current === row.id ? null : current));
  };

  const runBulkEnable = async (enable) => {
    const ids = [...bulkIds];
    if (!ids.length) return;
    const touched = new Set(ids);
    setBulkBusy(true);
    try {
      await api.post(
        `${API_PREFIX}/admin/users/bulk-status`,
        { user_ids: ids, is_enabled: enable },
        { headers: { ...authBearer(), "Content-Type": "application/json" } }
      );
      setRows((prev) => prev.map((r) => (touched.has(r.id) ? { ...r, is_enabled: enable } : r)));
      setBulkIds(new Set());
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || "Bulk update failed.");
    } finally {
      setBulkBusy(false);
    }
  };

  const stats = useMemo(() => {
    const enabledCt = rows.filter((r) => r.is_enabled).length;
    return { total: rows.length, enabled: enabledCt };
  }, [rows]);

  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-slate-800 bg-gradient-to-br from-slate-900 to-slate-950 p-4 shadow-lg shadow-black/30">
          <p className="text-xs uppercase text-slate-500">Matched accounts</p>
          <p className="mt-2 text-2xl font-semibold text-white">{stats.total}</p>
          <p className="text-xs text-slate-400">After search & filters.</p>
        </div>
        <div className="rounded-xl border border-emerald-900/60 bg-emerald-950/20 p-4">
          <p className="text-xs uppercase text-emerald-500/90">Eligible for biometrics</p>
          <p className="mt-2 text-2xl font-semibold text-emerald-300">{stats.enabled}</p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/50 p-4">
        <input
          className="min-w-[200px] flex-1 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white placeholder:text-slate-600"
          placeholder="Search name / email / ID"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value)}
        >
          <option value="">All roles</option>
          <option value="student">student</option>
          <option value="teacher">teacher</option>
          <option value="staff">staff</option>
        </select>
        <select
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
          value={classFilter}
          onChange={(e) => setClassFilter(e.target.value)}
        >
          <option value="">All classes</option>
          {classOptions.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <select
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
          value={enabledFilter}
          onChange={(e) => setEnabledFilter(e.target.value)}
        >
          <option value="">Enabled + disabled</option>
          <option value="true">Enabled only</option>
          <option value="false">Disabled only</option>
        </select>
      </div>

      {bulkIds.size > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-amber-800/70 bg-amber-950/30 px-4 py-3 text-sm text-amber-50">
          <span className="font-medium">{bulkIds.size} selected</span>
          <button
            type="button"
            disabled={bulkBusy}
            onClick={() => runBulkEnable(true)}
            className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
          >
            Enable selected
          </button>
          <button
            type="button"
            disabled={bulkBusy}
            onClick={() => runBulkEnable(false)}
            className="rounded-lg border border-rose-700 bg-rose-950/60 px-3 py-1.5 text-xs font-semibold text-rose-100 hover:bg-rose-950 disabled:opacity-50"
          >
            Disable selected
          </button>
        </div>
      )}

      {error && <p className="text-sm text-red-400">{error}</p>}
      {loading && <p className="text-xs text-slate-500">Synchronizing directory…</p>}

      <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/40 shadow-xl shadow-black/20">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-800 text-sm text-slate-200">
            <thead className="bg-slate-950/90 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
              <tr>
                <th className=" px-3 py-3 ">
                  <input
                    aria-label="Select all rows"
                    type="checkbox"
                    className="h-4 w-4 accent-emerald-500"
                    checked={allRowsSelected}
                    disabled={!rows.length}
                    onChange={toggleSelectAllRows}
                  />
                </th>
                <th className=" px-4 py-3 text-left ">ID</th>
                <th className=" px-4 py-3 text-left ">Name</th>
                <th className=" px-4 py-3 text-left ">Class</th>
                <th className=" px-4 py-3 text-left ">Email</th>
                <th className=" px-4 py-3 text-left ">External ID</th>
                <th className=" px-4 py-3 text-left ">Role</th>
                <th className=" px-4 py-3 text-left ">Enabled</th>
                <th className=" px-4 py-3 text-left ">Face</th>
                <th className=" px-4 py-3 text-right ">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {rows.map((row) => (
                <tr key={row.id} className="bg-slate-900/20 hover:bg-slate-900/55">
                  <td className=" px-4 py-3 ">
                    <input type="checkbox" className="h-4 w-4 accent-emerald-500" checked={bulkIds.has(row.id)} onChange={() => toggleBulk(row.id)} />
                  </td>
                  <td className=" px-4 py-3 font-mono text-xs text-slate-400">{row.id}</td>
                  <td className=" px-4 py-3 font-medium text-white">{row.full_name}</td>
                  <td className=" px-4 py-3 ">
                    <select
                      value={String(row.student_class || "")}
                      onChange={(e) => patchUserClass(row, e.target.value)}
                      className="max-w-[8rem] rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-white"
                    >
                      <option value="">—</option>
                      {classOptions.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className=" max-w-[12rem] truncate px-4 py-3 text-slate-400 ">{row.email}</td>
                  <td className=" px-4 py-3 text-xs text-emerald-200/90 ">{row.student_external_id || "—"}</td>
                  <td className=" px-4 py-3 ">
                    <select
                      value={row.role}
                      className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs"
                      onChange={(e) => changeRole(row, e.target.value)}
                    >
                      <option value="student">student</option>
                      <option value="teacher">teacher</option>
                      <option value="staff">staff</option>
                    </select>
                  </td>
                  <td className=" px-4 py-3 ">
                    <label className="inline-flex cursor-pointer items-center gap-2 text-xs">
                      <input
                        type="checkbox"
                        className="h-4 w-4 accent-emerald-400"
                        checked={Boolean(row.is_enabled)}
                        onChange={(e) => toggleEnabled(row, e.target.checked)}
                      />
                      <span className={row.is_enabled ? "text-emerald-400" : "text-rose-400"}>{row.is_enabled ? "Yes" : "No"}</span>
                    </label>
                  </td>
                  <td className=" px-4 py-3 ">
                    {row.has_face_image ? (
                      <button type="button" className="text-xs text-sky-300 underline" onClick={() => setPreviewId(row.id)}>
                        Preview
                      </button>
                    ) : (
                      <span className="text-xs text-slate-600">No JPEG</span>
                    )}
                  </td>
                  <td className=" px-4 py-3 text-right ">
                    <button type="button" className="text-xs text-rose-400 underline hover:text-rose-300" onClick={() => removeUser(row)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
              {!rows.length && !loading && (
                <tr>
                  <td colSpan={10} className="px-4 py-10 text-center text-xs text-slate-500">
                    No accounts matched this query.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr,minmax(0,360px)]">
        <section className="rounded-xl border border-slate-800 bg-slate-900/35 p-4">
          <h2 className="text-sm font-semibold text-white">Portrait workspace</h2>
          <p className="mt-1 text-xs text-slate-500">
            Reference frame used for cosine checks. Stored under <span className="font-mono text-slate-400">{ADMIN_TOKEN_KEY}</span> session.
          </p>
          {!previewUrl && <p className="mt-4 text-xs text-slate-500">Choose Preview on a roster row.</p>}
          {previewUrl && (
            <img alt="Enrollment portrait preview" src={previewUrl} className="mt-4 max-h-80 rounded-lg border border-slate-700 shadow-lg" />
          )}
        </section>
        <section className="rounded-xl border border-slate-800 bg-slate-900/35 p-4 text-xs text-slate-400">
          <h3 className="text-sm font-semibold text-slate-200">Operating notes</h3>
          <ul className="mt-3 list-inside list-disc space-y-2">
            <li>Row checkboxes funnel into bulk enable/disable for incident response.</li>
            <li>Class labels route teachers when composing virtual class cohorts.</li>
            <li>Disabled users halt verify + meeting tokens instantly on the backend.</li>
          </ul>
        </section>
      </div>
    </div>
  );
}
