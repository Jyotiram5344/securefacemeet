import { Link, Outlet, useNavigate } from "react-router-dom";
import { getMeetingToken } from "../components/ProtectedRoute.jsx";

export default function PublicLayout() {
  const navigate = useNavigate();
  const hasMeetingToken = !!getMeetingToken();

  const handleMeetingClick = (e) => {
    if (!hasMeetingToken) {
      e.preventDefault();
      navigate("/verify", { replace: false });
    }
  };

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4">
          <Link to="/" className="text-lg font-semibold tracking-tight text-white">
            SecureFaceMeet
          </Link>
          <nav className="flex flex-wrap gap-4 text-sm text-slate-300">
            <Link className="hover:text-white" to="/register">
              Register
            </Link>
            <Link className="hover:text-white" to="/verify">
              Verify
            </Link>
            <Link
              className={hasMeetingToken ? "hover:text-white" : "cursor-not-allowed text-slate-500"}
            to="/verify"
              onClick={handleMeetingClick}
            >
              Meeting
            </Link>
            <Link className="hover:text-white" to="/join-class">
              Join class
            </Link>
            <Link className="hover:text-white" to="/admin/login">
              Admin
            </Link>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  );
}
