import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { getMeetingToken, setMeetingToken } from "../components/ProtectedRoute.jsx";
import { api, API_PREFIX, authHeader } from "../services/api.js";

function loadJitsiScript() {
  if (window.JitsiMeetExternalAPI) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://meet.jit.si/external_api.js";
    script.async = true;
    script.onload = resolve;
    script.onerror = () => reject(new Error("Could not load Jitsi API script."));
    document.body.appendChild(script);
  });
}

export default function MeetingRoom() {
  const [searchParams] = useSearchParams();
  const [meetingId, setMeetingId] = useState("");
  const [joined, setJoined] = useState(false);
  const [joinError, setJoinError] = useState("");

  const containerRef = useRef(null);
  const jitsiApiRef = useRef(null);
  const meetingToken = getMeetingToken();

  const meetingClaims = useMemo(() => {
    const parts = (meetingToken || "").split(".");
    if (parts.length < 2) return null;
    try {
      const payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
      const pad = payload.length % 4 ? "=".repeat(4 - (payload.length % 4)) : "";
      return JSON.parse(window.atob(payload + pad));
    } catch (_e) {
      return null;
    }
  }, [meetingToken]);

  useEffect(() => {
    const r = (searchParams.get("room") || "").trim();
    if (r) setMeetingId(r);
  }, [searchParams]);
  const leaveMeeting = () => {
    try {
      jitsiApiRef.current?.executeCommand?.("hangup");
    } catch (_e) {
      /* noop */
    }
    try {
      jitsiApiRef.current?.dispose?.();
    } catch (_e) {
      /* noop */
    }
    jitsiApiRef.current = null;
    setJoined(false);
  };

  const bindJoinToBackend = async (room) => {
    const { data } = await api.post(
      `${API_PREFIX}/meeting/session/join`,
      { meeting_id: room },
      { headers: { ...authHeader(meetingToken) } }
    );
    return data;
  };

  const bindLeaveToBackend = async (room) => {
    try {
      await api.post(
        `${API_PREFIX}/meeting/session/leave`,
        { meeting_id: room, removed: false },
        { headers: { ...authHeader(meetingToken) } }
      );
    } catch (_e) {
      // Avoid blocking Jitsi teardown on API failures.
    }
  };

  const joinMeeting = async () => {
    const room = meetingId.trim();
    if (!room) {
      setJoinError("Enter meeting ID.");
      return;
    }
    if (!meetingToken) {
      setJoinError("Meeting token missing. Complete verify, liveness and token generation first.");
      return;
    }
    if (meetingClaims?.room_id && String(meetingClaims.room_id).trim() !== room) {
      setJoinError("This token is bound to another room. Go back to Verify page for this room.");
      return;
    }
    try {
      setJoinError("");
      await bindJoinToBackend(room);
      await loadJitsiScript();

      const domain = (import.meta.env.VITE_JITSI_BASE_URL || "https://meet.jit.si")
        .replace(/^https?:\/\//, "")
        .replace(/\/$/, "");

      if (jitsiApiRef.current) {
        jitsiApiRef.current.dispose();
      }

      const apiObj = new window.JitsiMeetExternalAPI(domain, {
        roomName: room.replace(/\s+/g, ""),
        parentNode: containerRef.current,
        width: "100%",
        height: "100%",
        userInfo: {
          displayName: meetingClaims?.name || meetingClaims?.full_name || meetingClaims?.email || "Verified User",
          email: meetingClaims?.email || "",
        },
        configOverwrite: {
          prejoinConfig: {
            enabled: false,
          },
        },
      });
      jitsiApiRef.current = apiObj;

      apiObj.addEventListener("videoConferenceJoined", () => setJoined(true));
      apiObj.addEventListener("readyToClose", async () => {
        await bindLeaveToBackend(room);
        leaveMeeting();
      });
      apiObj.addEventListener("videoConferenceLeft", async () => {
        await bindLeaveToBackend(room);
        leaveMeeting();
      });
    } catch (e) {
      if (e?.response?.status === 401 || e?.response?.status === 403) {
        setMeetingToken("");
      }
      setJoinError(e.message || "Failed to join meeting.");
    }
  };

  useEffect(() => {
    return () => leaveMeeting();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold text-white">Virtual Meeting</h1>
      <div className="flex flex-wrap gap-2">
        <input
          className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
          placeholder="Enter Jitsi meeting ID"
          value={meetingId}
          onChange={(e) => setMeetingId(e.target.value)}
        />
        <button
          type="button"
          onClick={joinMeeting}
          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500"
        >
          {joined ? "Re-join" : "Join meeting"}
        </button>
        {joined && (
          <button
            type="button"
            onClick={leaveMeeting}
            className="rounded-lg border border-rose-900 bg-rose-950/40 px-4 py-2 text-sm font-medium text-rose-100 hover:bg-rose-950/70"
          >
            Leave
          </button>
        )}
      </div>

      {joinError ? <p className="text-sm text-red-400">{joinError}</p> : null}

      <div className="relative h-[620px] overflow-hidden rounded-xl border border-slate-800 bg-black">
        <div ref={containerRef} className="h-full w-full" />
      </div>
    </div>
  );
}
