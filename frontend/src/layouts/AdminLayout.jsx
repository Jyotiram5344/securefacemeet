import { useEffect } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { getAdminToken, setAdminToken } from "../pages/AdminLogin.jsx";

export default function AdminLayout() {
  const navigate = useNavigate();

  useEffect(() => {
    if (!getAdminToken()) navigate("/admin/login", { replace: true });
  }, [navigate]);

  const logout = () => {
    setAdminToken("");
    navigate("/register", { replace: true });
  };

  const linkCls = ({ isActive }) =>
    [
      "block rounded-lg px-3 py-2 text-sm transition-colors",
      isActive ? "bg-emerald-600/90 text-white" : "text-slate-300 hover:bg-slate-800 hover:text-white",
    ].join(" ");

  return (
    <div className="flex min-h-screen bg-slate-950 text-slate-100">
      <aside className="flex w-64 shrink-0 flex-col border-r border-slate-800 bg-slate-900/95">
        <div className="border-b border-slate-800 px-4 py-4">
          <p className="text-xs uppercase tracking-[0.2em] text-slate-500">SecureFaceMeet</p>
          <p className="mt-1 text-lg font-semibold text-white">Control center</p>
        </div>
        <nav className="flex flex-1 flex-col gap-1 p-3">
          <NavLink to="/admin/users" end className={linkCls}>
            Directory & access
          </NavLink>
          <NavLink to="/admin/virtual-class" className={linkCls}>
            Virtual class studio
          </NavLink>
          <NavLink to="/admin/participants" className={linkCls}>
            Meeting participants
          </NavLink>
        </nav>
        <div className="border-t border-slate-800 p-3">
          <button
            type="button"
            onClick={logout}
            className="w-full rounded-lg border border-rose-900/70 bg-rose-950/40 px-3 py-2 text-sm font-medium text-rose-100 hover:bg-rose-950/70"
          >
            Log out
          </button>
          <p className="mt-3 text-[11px] text-slate-500">Ends the admin JWT session stored in local storage.</p>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="border-b border-slate-800 bg-slate-900/60 px-6 py-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-xl font-semibold text-white">Administrator workspace</h1>
              <p className="text-sm text-slate-400">
                Consolidated directory controls and curated meeting authoring — mirror of production security desk UI patterns.
              </p>
            </div>
          </div>
        </header>
        <main className="flex-1 overflow-auto bg-slate-950/90 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
