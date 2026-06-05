import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { getAdminToken } from "./AdminLogin.jsx";
import { api, API_PREFIX } from "../services/api.js";

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

export default function AdminMeeting() {
  const [searchParams] = useSearchParams();
  const [meetingId, setMeetingId] = useState("");
  const [joined, setJoined] = useState(false);
  const [joinError, setJoinError] = useState("");
  const [statusMsg, setStatusMsg] = useState("");
  const [autoExportFormat, setAutoExportFormat] = useState("csv");

  const containerRef = useRef(null);
  const jitsiApiRef = useRef(null);
  const downloadedForRoomRef = useRef(new Set());

  useEffect(() => {
    const r = (searchParams.get("room") || "").trim();
    if (r) setMeetingId(r);
  }, [searchParams]);

  const parseFilenameFromDisposition = (cd) => {
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
  };

  const authBearer = () => {
    const token = getAdminToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  };

  const downloadAttendanceExport = async (room, fmt) => {
    const rid = String(room || "").trim();
    if (!rid || downloadedForRoomRef.current.has(`${rid}:${fmt}`)) return;
    downloadedForRoomRef.current.add(`${rid}:${fmt}`);
    try {
      const res = await api.get(`${API_PREFIX}/admin/participants/room/${encodeURIComponent(rid)}/export`, {
        headers: authBearer(),
        params: { fmt, filter_mode: "qualified" },
        responseType: "blob",
      });
      const blob = new Blob([res.data], { type: res.headers["content-type"] || "application/octet-stream" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = parseFilenameFromDisposition(res.headers["content-disposition"]) || `participants_${rid}_qualified.${fmt}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setStatusMsg(`Meeting ended. ${fmt.toUpperCase()} attendance downloaded.`);
    } catch (e) {
      downloadedForRoomRef.current.delete(`${rid}:${fmt}`);
      const detail = typeof e?.response?.data?.detail === "string" ? e.response.data.detail : "";
      setStatusMsg(detail || "Could not auto-download attendance file.");
    }
  };

  const leaveMeeting = async (opts = {}) => {
    const room = String(opts.room || meetingId || "").trim();
    const shouldDownload = Boolean(opts.downloadExport);
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
    if (shouldDownload && room) {
      await downloadAttendanceExport(room, autoExportFormat);
    }
  };

  const joinMeeting = async () => {
    const room = meetingId.trim();
    if (!room) {
      setJoinError("Enter meeting ID.");
      return;
    }
    try {
      setJoinError("");
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
        configOverwrite: {
          prejoinConfig: {
            enabled: false,
          },
        },
      });

      jitsiApiRef.current = apiObj;
      apiObj.addEventListener("videoConferenceJoined", () => setJoined(true));
      apiObj.addEventListener("readyToClose", () => leaveMeeting({ room, downloadExport: true }));
      apiObj.addEventListener("videoConferenceLeft", () => leaveMeeting({ room, downloadExport: true }));
    } catch (e) {
      setJoinError(e?.message || "Failed to join meeting.");
    }
  };

  useEffect(() => {
    if (!joined) return undefined;
    const room = meetingId.trim();
    if (!room) return undefined;

    let stopped = false;
    const tick = async () => {
      try {
        const { data } = await api.get(`${API_PREFIX}/virtual-class/sessions/${encodeURIComponent(room)}`);
        if (stopped) return;
        if (data?.meeting_closed) {
          setStatusMsg("Meeting reached scheduled end. Closing room and downloading attendance…");
          await leaveMeeting({ room, downloadExport: true });
        }
      } catch (_e) {
        // Keep polling even if transient API request fails.
      }
    };

    const id = window.setInterval(tick, 10000);
    tick();
    return () => {
      stopped = true;
      window.clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [joined, meetingId, autoExportFormat]);

  useEffect(() => {
    return () => leaveMeeting({ downloadExport: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-white">Teacher meeting room</h1>
          <p className="mt-1 text-sm text-slate-400">
            This page is for faculty to start/join the room even when no students are connected yet.
          </p>
        </div>
        <Link to="/admin/virtual-class" className="text-sm text-slate-300 underline hover:text-white">
          Back to Virtual class studio
        </Link>
      </div>

      <div className="flex flex-wrap gap-2">
        <input
          className="min-w-[220px] flex-1 rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
          placeholder="Enter Jitsi meeting ID"
          value={meetingId}
          onChange={(e) => setMeetingId(e.target.value)}
        />
        {!joined ? (
          <button
            type="button"
            onClick={joinMeeting}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500"
          >
            Join meeting
          </button>
        ) : (
          <button
            type="button"
            onClick={() => leaveMeeting({ room: meetingId.trim(), downloadExport: true })}
            className="rounded-lg border border-rose-900 bg-rose-950/40 px-4 py-2 text-sm font-medium text-rose-100 hover:bg-rose-950/70"
          >
            Leave
          </button>
        )}
      </div>

      <label className="block max-w-xs text-sm text-slate-300">
        Auto-download format on meeting end
        <select
          className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
          value={autoExportFormat}
          onChange={(e) => setAutoExportFormat(e.target.value)}
        >
          <option value="xlsx">Excel (XLSX)</option>
          <option value="csv">CSV</option>
        </select>
      </label>

      {joinError ? <p className="text-sm text-red-400">{joinError}</p> : null}
      {statusMsg ? <p className="text-sm text-emerald-300">{statusMsg}</p> : null}

      <div className="relative h-[620px] overflow-hidden rounded-xl border border-slate-800 bg-black">
        <div ref={containerRef} className="h-full w-full" />
      </div>
    </div>
  );
}

