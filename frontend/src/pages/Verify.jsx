import { useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import CameraCapture from "../components/CameraCapture.jsx";
import { setMeetingToken } from "../components/ProtectedRoute.jsx";
import { api, API_PREFIX, authHeader } from "../services/api.js";

export default function Verify() {
  const [searchParams] = useSearchParams();
  const roomHint = (searchParams.get("room") || "").trim();

  const camRef = useRef(null);
  const [status, setStatus] = useState("");
  const [email, setEmail] = useState("");
  const [declaredClass, setDeclaredClass] = useState("");
  const [verifyToken, setVerifyToken] = useState("");
  const [livenessToken, setLivenessToken] = useState("");
  const [challengeToken, setChallengeToken] = useState("");
  const [challengeAction, setChallengeAction] = useState("");
  const [challengeInstruction, setChallengeInstruction] = useState("");
  const [meetingJwt, setMeetingJwt] = useState("");
  const [loading, setLoading] = useState(false);

  const blobToFile = (blob, name) => new File([blob], name, { type: "image/jpeg" });

  const runVerify = async () => {
    setLoading(true);
    setStatus("Capturing…");
    try {
      const blob = await camRef.current.captureBlob();
      const fd = new FormData();
      fd.append("file", blobToFile(blob, "frame.jpg"));
      if (email.trim()) fd.append("email", email.trim());
      if (declaredClass.trim()) fd.append("restrict_to_class", declaredClass.trim());
      const { data } = await api.post(`${API_PREFIX}/face/verify-face`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      if (!data.verified) {
        setStatus(data.message || "Not verified.");
        setVerifyToken("");
        setChallengeToken("");
        setChallengeAction("");
        setChallengeInstruction("");
        return;
      }
      setVerifyToken(data.verify_token);
      setChallengeToken("");
      setChallengeAction("");
      setChallengeInstruction("");
      setLivenessToken("");
      const cls = data.student_class ? ` · Class ${data.student_class}` : "";
      setStatus(`Verified: ${data.full_name || data.email}${cls}. Next: liveness.`);
    } catch (err) {
      const d = err.response?.data;
      setStatus(typeof d?.detail === "string" ? d.detail : err.message || "Verify failed.");
      setVerifyToken("");
    } finally {
      setLoading(false);
    }
  };

  const runLiveness = async () => {
    if (!verifyToken) {
      setStatus("Verify first.");
      return;
    }
    setLoading(true);
    try {
      if (!challengeToken) {
        const startRes = await api.post(
          `${API_PREFIX}/liveness/active-challenge/start`,
          {},
          { headers: { ...authHeader(verifyToken) } }
        );
        setChallengeToken(startRes.data.challenge_token);
        setChallengeAction(startRes.data.action);
        setChallengeInstruction(startRes.data.instruction);
        setStatus(`${startRes.data.instruction} Then click "Check liveness" again.`);
        return;
      }

      setStatus(`Capturing for active challenge (${challengeAction})…`);
      const blob = await camRef.current.captureBlob();
      const fd = new FormData();
      fd.append("challenge_token", challengeToken);
      fd.append("file", blobToFile(blob, "active-live.jpg"));
      const { data } = await api.post(`${API_PREFIX}/liveness/active-challenge/verify`, fd, {
        headers: {
          "Content-Type": "multipart/form-data",
          ...authHeader(verifyToken),
        },
      });
      if (!data.live) {
        setStatus(`${data.message} (yaw ${data.yaw_score?.toFixed?.(3) ?? data.yaw_score})`);
        setLivenessToken("");
        return;
      }
      setLivenessToken(data.liveness_token);
      setStatus("Active liveness OK. Generate meeting token.");
    } catch (err) {
      const d = err.response?.data;
      setStatus(typeof d?.detail === "string" ? d.detail : err.message || "Liveness failed.");
      setLivenessToken("");
    } finally {
      setLoading(false);
    }
  };

  const runMeetingToken = async () => {
    if (!livenessToken) {
      setStatus("Complete liveness first.");
      return;
    }
    setLoading(true);
    try {
      const body = roomHint ? { room_id: roomHint } : {};
      const { data } = await api.post(
        `${API_PREFIX}/meeting/generate-meeting-token`,
        body,
        { headers: { ...authHeader(livenessToken) } }
      );
      setMeetingJwt(data.access_token);
      setMeetingToken(data.access_token);
      setStatus("Meeting token issued. You can join the meeting.");
    } catch (err) {
      const d = err.response?.data;
      if (err.code === "ERR_NETWORK" || err.message === "Network Error") {
        setStatus(
          "Network error — is the API running? From SecureFaceMeet/backend run: uvicorn main:app --reload --host 127.0.0.1 --port 8000. In dev, use this app at http://localhost:5173 so /api is proxied, or set VITE_API_BASE_URL."
        );
        return;
      }
      setStatus(typeof d?.detail === "string" ? d.detail : err.message || "Token failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid gap-8 lg:grid-cols-2">
      <div>
        <h1 className="text-2xl font-semibold text-white">Verify & liveness</h1>
        <p className="mt-2 text-sm text-slate-400">
          All inference runs on the backend. The browser only captures frames and sends them over HTTPS in production.
        </p>
        {roomHint && (
          <p className="mt-2 text-sm text-amber-200/90">
            Virtual class room bound to this session:{" "}
            <span className="font-mono text-amber-100">{roomHint}</span> (included in your meeting token).
          </p>
        )}
        <div className="mt-4 space-y-2 text-sm text-slate-400">
          <label className="block">
            <span className="text-slate-300">Restrict to email (optional)</span>
            <input
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
              placeholder="user@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label className="block">
            <span className="text-slate-300">Declared class gate (optional)</span>
            <p className="mb-1 text-xs text-slate-500">
              If set, verification fails unless the matched account’s stored class matches this label (same as registration cohort).
            </p>
            <select
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
              value={declaredClass}
              onChange={(e) => setDeclaredClass(e.target.value)}
            >
              <option value="">No extra class check</option>
              <option value="A">A</option>
              <option value="B">B</option>
              <option value="FACULTY">FACULTY</option>
              <option value="CSE-A">CSE-A</option>
              <option value="IT-A">IT-A</option>
            </select>
          </label>
        </div>
        <div className="mt-6 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={loading}
            onClick={runVerify}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            1. Verify face
          </button>
          <button
            type="button"
            disabled={loading || !verifyToken}
            onClick={runLiveness}
            className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-500 disabled:opacity-50"
          >
            {challengeToken ? "2. Capture challenge" : "2. Check liveness"}
          </button>
          <button
            type="button"
            disabled={loading || !livenessToken}
            onClick={runMeetingToken}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
          >
            3. Meeting JWT
          </button>
          <Link
            to="/meeting"
            className={`rounded-lg px-4 py-2 text-sm font-medium ${
              meetingJwt ? "bg-slate-100 text-slate-900" : "cursor-not-allowed bg-slate-800 text-slate-500"
            }`}
            onClick={(e) => {
              if (!meetingJwt) e.preventDefault();
            }}
          >
            Join meeting
          </Link>
        </div>
        <p className="mt-4 text-sm text-slate-300">{status}</p>
        {challengeInstruction && !livenessToken && (
          <p className="mt-2 text-xs text-amber-300">Active challenge: {challengeInstruction}</p>
        )}
        {meetingJwt && (
          <p className="mt-2 break-all text-xs text-slate-500">
            Token stored locally for the meeting gate (short-lived).
          </p>
        )}
      </div>
      <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
        <CameraCapture ref={camRef} onStatus={setStatus} />
        <p className="mt-3 text-xs text-slate-500">
          Tip: use good lighting. Passive anti-spoof runs server-side on each liveness frame.
        </p>
      </div>
    </div>
  );
}
