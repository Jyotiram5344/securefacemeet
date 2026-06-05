import { Navigate } from "react-router-dom";

const MEETING_TOKEN_KEY = "securefacemeet_meeting_jwt";

export function getMeetingToken() {
  return localStorage.getItem(MEETING_TOKEN_KEY);
}

export function setMeetingToken(token) {
  if (token) localStorage.setItem(MEETING_TOKEN_KEY, token);
  else localStorage.removeItem(MEETING_TOKEN_KEY);
}

/**
 * Gate children behind presence of a meeting JWT (set after full verification flow).
 */
export default function ProtectedRoute({ children }) {
  const token = getMeetingToken();
  if (!token) {
    return <Navigate to="/verify" replace />;
  }
  return children;
}
