import { Navigate, Route, Routes } from "react-router-dom";
import PublicLayout from "./layouts/PublicLayout.jsx";
import AdminLayout from "./layouts/AdminLayout.jsx";
import Register from "./pages/Register.jsx";
import Verify from "./pages/Verify.jsx";
import Meeting from "./pages/Meeting.jsx";
import VirtualClass from "./pages/VirtualClass.jsx";
import AdminLogin from "./pages/AdminLogin.jsx";
import AdminUsers from "./pages/AdminUsers.jsx";
import AdminParticipants from "./pages/AdminParticipants.jsx";
import AdminMeeting from "./pages/AdminMeeting.jsx";
import ProtectedRoute from "./components/ProtectedRoute.jsx";

export default function App() {
  return (
    <Routes>
      <Route path="/admin/login" element={<AdminLogin />} />
      <Route path="/admin" element={<AdminLayout />}>
        <Route index element={<Navigate to="/admin/users" replace />} />
        <Route path="users" element={<AdminUsers />} />
        <Route path="virtual-class" element={<VirtualClass mode="admin-teacher" />} />
        <Route path="participants" element={<AdminParticipants />} />
        <Route path="meeting" element={<AdminMeeting />} />
      </Route>

      <Route element={<PublicLayout />}>
        <Route path="/" element={<Navigate to="/verify" replace />} />
        <Route path="/register" element={<Register />} />
        <Route path="/verify" element={<Verify />} />
        <Route
          path="/meeting"
          element={
            <ProtectedRoute>
              <Meeting />
            </ProtectedRoute>
          }
        />
        <Route path="/join-class" element={<VirtualClass mode="student" />} />
      </Route>
    </Routes>
  );
}
