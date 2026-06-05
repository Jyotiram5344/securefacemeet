import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, API_PREFIX } from "../services/api.js";

const TEACHER_KEY_HEADER = () => ({
  "X-Teacher-Key": import.meta.env.VITE_TEACHER_API_KEY || "teacher-dev-key",
});

function approximateMinutesRemaining(meeting) {
  const endTs = Number(meeting?.end_time || 0);
  if (!endTs) return null;
  return (endTs - Date.now() / 1000) / 60.0;
}

/**
 * @param {{ mode?: 'full' | 'admin-teacher' | 'student' }} props
 */
export default function VirtualClass({ mode = "full" }) {
  const teacherLocked = mode === "admin-teacher";
  const studentOnly = mode === "student";

  const [role, setRole] = useState(studentOnly ? "Student" : "Teacher");

  const [students, setStudents] = useState([]);
  const [meetings, setMeetings] = useState([]);
  const [loadingRoster, setLoadingRoster] = useState(false);
  const [loadingMeetings, setLoadingMeetings] = useState(false);

  const [subject, setSubject] = useState("");
  const [classFilter, setClassFilter] = useState("A");
  const [duration, setDuration] = useState(60);
  const [selectedStudentIds, setSelectedStudentIds] = useState(() => new Set());
  const [teacherError, setTeacherError] = useState("");
  const [teacherSuccess, setTeacherSuccess] = useState("");

  const [editingMeeting, setEditingMeeting] = useState(null);
  const [editSelections, setEditSelections] = useState(() => new Set());

  /** Filter roster picker by enrolled class label (stored at registration). */
  const [rosterClassFilter, setRosterClassFilter] = useState("ALL");

  const [studentRoom, setStudentRoom] = useState("");
  const [sessionInfo, setSessionInfo] = useState(null);
  const [studentError, setStudentError] = useState("");
  const [studentLoading, setStudentLoading] = useState(false);

  const rosterLookup = useMemo(() => {
    const map = new Map();
    students.forEach((s) => map.set(Number(s.id), s));
    return map;
  }, [students]);

  const distinctStudentClasses = useMemo(() => {
    const vals = new Set();
    students.forEach((s) => {
      const c = String(s.student_class || "").trim().toUpperCase();
      if (c) vals.add(c);
    });
    return Array.from(vals).sort();
  }, [students]);

  const visibleStudents = useMemo(() => {
    if (rosterClassFilter === "ALL") return students;
    const want = rosterClassFilter.toUpperCase();
    return students.filter((s) => String(s.student_class || "").toUpperCase() === want);
  }, [students, rosterClassFilter]);

  const allVisibleSelected =
    visibleStudents.length > 0 && visibleStudents.every((s) => selectedStudentIds.has(Number(s.id)));

  const toggleSelectAllVisible = () => {
    setSelectedStudentIds((prev) => {
      const next = new Set(prev);
      if (allVisibleSelected) {
        visibleStudents.forEach((s) => next.delete(Number(s.id)));
      } else {
        visibleStudents.forEach((s) => next.add(Number(s.id)));
      }
      return next;
    });
  };

  const refreshTeacherData = async () => {
    setLoadingRoster(true);
    try {
      const { data } = await api.get(`${API_PREFIX}/virtual-class/teacher/students`, {
        headers: TEACHER_KEY_HEADER(),
      });
      setStudents(Array.isArray(data) ? data : []);
    } catch (err) {
      const detail =
        typeof err.response?.data?.detail === "string" ? err.response.data.detail : err.message || "Roster unavailable.";
      setTeacherError(detail);
    } finally {
      setLoadingRoster(false);
    }

    setLoadingMeetings(true);
    try {
      const { data } = await api.get(`${API_PREFIX}/virtual-class/teacher/meetings`, {
        headers: TEACHER_KEY_HEADER(),
      });
      setMeetings(Array.isArray(data) ? data : []);
    } catch (err) {
      const detail =
        typeof err.response?.data?.detail === "string" ? err.response.data.detail : err.message || "Meetings unavailable.";
      setTeacherError(detail);
    } finally {
      setLoadingMeetings(false);
    }
  };

  useEffect(() => {
    if (teacherLocked || role === "Teacher") {
      refreshTeacherData();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role, teacherLocked]);

  useEffect(() => {
    if (teacherLocked) setRole("Teacher");
    if (studentOnly) setRole("Student");
  }, [teacherLocked, studentOnly]);

  const toggleStudentSelection = (id, currentSet, setter) => {
    const next = new Set(currentSet);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setter(next);
  };

  const startMeeting = async () => {
    setTeacherError("");
    setTeacherSuccess("");
    if (!subject.trim()) {
      setTeacherError("Enter a subject.");
      return;
    }
    const rosterIds = [...selectedStudentIds];
    if (rosterIds.length === 0) {
      setTeacherError("Pick at least one allowed student.");
      return;
    }
    try {
      const { data } = await api.post(
        `${API_PREFIX}/virtual-class/sessions`,
        {
          subject: subject.trim(),
          class_filter: classFilter,
          duration_minutes: duration,
          allowed_student_ids: rosterIds,
        },
        { headers: TEACHER_KEY_HEADER() }
      );
      setTeacherSuccess(`Room ${data.room_id} armed with roster size ${data.allowed_student_ids.length}.`);
      setSubject("");
      setSelectedStudentIds(new Set());
      await refreshTeacherData();
    } catch (e) {
      const d = e?.response?.data;
      setTeacherError(typeof d?.detail === "string" ? d.detail : e.message || "Could not publish session.");
    }
  };

  const beginEditMeeting = (meeting) => {
    setEditingMeeting(meeting);
    setEditSelections(new Set((meeting.allowed_student_ids || []).map(Number)));
  };

  const saveEditedMeeting = async () => {
    if (!editingMeeting) return;
    setTeacherError("");
    setTeacherSuccess("");
    const rosterIds = [...editSelections];
    if (rosterIds.length === 0) {
      setTeacherError("Roster requires at least one student.");
      return;
    }
    try {
      await api.patch(
        `${API_PREFIX}/virtual-class/teacher/meetings/${encodeURIComponent(editingMeeting.room_id)}`,
        { allowed_student_ids: rosterIds },
        { headers: TEACHER_KEY_HEADER() }
      );
      setTeacherSuccess("Roster refreshed.");
      setEditingMeeting(null);
      await refreshTeacherData();
    } catch (e) {
      const d = e?.response?.data;
      setTeacherError(typeof d?.detail === "string" ? d.detail : e.message || "Update failed.");
    }
  };

  const deleteMeeting = async (roomId) => {
    if (!window.confirm(`Delete rostered room ${roomId}?`)) return;
    try {
      await api.delete(`${API_PREFIX}/virtual-class/teacher/meetings/${encodeURIComponent(roomId)}`, {
        headers: TEACHER_KEY_HEADER(),
      });
      await refreshTeacherData();
      setTeacherSuccess("Meeting blueprint removed.");
    } catch (e) {
      const d = e?.response?.data;
      setTeacherError(typeof d?.detail === "string" ? d.detail : e.message || "Delete failed.");
    }
  };

  const lookupRoom = async () => {
    setStudentError("");
    const rid = studentRoom.trim();
    if (!rid) {
      setStudentError("Enter the meeting ID supplied by faculty.");
      return;
    }
    setStudentLoading(true);
    try {
      const { data } = await api.get(`${API_PREFIX}/virtual-class/sessions/${encodeURIComponent(rid)}`);
      setSessionInfo(data);
      if (!data.found) {
        setStudentError("Room ID not recognised. Reach out to the host.");
      }
    } catch (e) {
      const d = e?.response?.data;
      setSessionInfo(null);
      setStudentError(typeof d?.detail === "string" ? d.detail : e.message || "Lookup failed.");
    } finally {
      setStudentLoading(false);
    }
  };

  const encodedRoom = studentRoom.trim() ? encodeURIComponent(studentRoom.trim()) : "";

  return (
    <div className="space-y-8">
      {!teacherLocked && (
        <>
          <h1 className="text-2xl font-semibold text-white">Virtual class</h1>
          <p className="text-sm text-slate-400">
            Faculty issue Jitsi room IDs paired with biometric gatekeeping. Rosters persist server-side ({`meeting → allowed_student_ids`}
            ).
          </p>
          <p className="text-xs text-slate-500">
            Teacher console uses the shared <span className="font-mono">X-Teacher-Key</span> header configured via{" "}
            <span className="font-mono">VITE_TEACHER_API_KEY</span> — default mirrors backend{" "}
            <span className="font-mono">teacher-dev-key</span>.
          </p>
        </>
      )}

      {!studentOnly && !teacherLocked && (
        <label className="block text-sm text-slate-300">
          Role
          <select
            className="mt-1 w-full max-w-xs rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
            value={role}
            onChange={(e) => setRole(e.target.value)}
          >
            <option value="Teacher">Teacher</option>
            <option value="Student">Student</option>
          </select>
        </label>
      )}

      {(teacherLocked || role === "Teacher") && (
        <div className="space-y-6">
          {(teacherError || teacherSuccess) && (
            <div className={`text-sm ${teacherError ? "text-red-400" : "text-emerald-300"}`}>{teacherError || teacherSuccess}</div>
          )}

          <section className="rounded-xl border border-slate-800 bg-slate-900/40 p-6 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-lg font-medium text-white">Create curated meeting</h2>
              <button
                type="button"
                onClick={() => refreshTeacherData()}
                className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-200 hover:border-emerald-500"
              >
                Refresh data
              </button>
            </div>
            {loadingRoster && <p className="text-xs text-slate-500">Hydrating roster…</p>}

            <label className="block text-sm text-slate-300">
              Filter roster by class
              <select
                className="mt-1 w-full max-w-xs rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                value={rosterClassFilter}
                onChange={(e) => setRosterClassFilter(e.target.value)}
              >
                <option value="ALL">All classes</option>
                {distinctStudentClasses.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
              <span className="mt-1 block text-xs text-slate-500">Uses the class captured at registration ({visibleStudents.length} visible).</span>
            </label>

            <label className="block text-sm text-slate-300">
              Subject
              <input
                className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
              />
            </label>
            <label className="block text-sm text-slate-300">
              Audience tag
              <select
                className="mt-1 w-full max-w-xs rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                value={classFilter}
                onChange={(e) => setClassFilter(e.target.value)}
              >
                <option value="A">A</option>
                <option value="B">B</option>
                <option value="Faculty">Faculty</option>
              </select>
            </label>
            <label className="block text-sm text-slate-300">
              Duration (minutes)
              <input
                type="number"
                min={1}
                max={240}
                step={0.5}
                className="mt-1 w-full max-w-xs rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                value={duration}
                onChange={(e) => setDuration(Number(e.target.value))}
              />
            </label>

            <div className="space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-medium text-white">Approved students ({selectedStudentIds.size} selected)</p>
                <label className="flex items-center gap-2 text-xs text-slate-300">
                  <input
                    type="checkbox"
                    className="h-4 w-4 accent-emerald-400"
                    checked={allVisibleSelected && visibleStudents.length > 0}
                    disabled={visibleStudents.length === 0}
                    onChange={toggleSelectAllVisible}
                  />
                  Select all visible
                </label>
              </div>
              <div className="max-h-52 space-y-2 overflow-y-auto rounded-lg border border-slate-800 bg-slate-950/60 p-3 text-sm text-slate-200">
                {students.length === 0 && <p className="text-xs text-slate-500">No seated students discovered.</p>}
                {students.length > 0 && visibleStudents.length === 0 && (
                  <p className="text-xs text-amber-300">No students match this class filter.</p>
                )}
                {visibleStudents.map((row) => {
                  const numericId = Number(row.id);
                  return (
                    <label key={numericId} className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        className="h-4 w-4 accent-emerald-500"
                        checked={selectedStudentIds.has(numericId)}
                        onChange={() => toggleStudentSelection(numericId, selectedStudentIds, setSelectedStudentIds)}
                      />
                      <span className="flex-1">
                        <span className="text-white">{row.full_name}</span>{" "}
                        <span className="font-mono text-xs text-emerald-200">#{numericId}</span>
                        <span className="ml-2 rounded bg-slate-800 px-2 py-[1px] text-[10px] uppercase text-slate-300">
                          {row.student_class || "—"}
                        </span>
                        <span className="block text-xs text-slate-500">{row.student_external_id || row.email}</span>
                      </span>
                    </label>
                  );
                })}
              </div>
            </div>

            <button
              type="button"
              onClick={startMeeting}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500"
            >
              Save meeting blueprint
            </button>
          </section>

          <section className="rounded-xl border border-slate-800 bg-slate-900/40 p-6 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-medium text-white">Existing meetings</h2>
              {loadingMeetings && <span className="text-xs text-slate-500">Refreshing…</span>}
            </div>
            <div className="space-y-3 text-sm text-slate-300">
              {meetings.map((meet) => (
                <div key={meet.room_id} className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="font-semibold text-white">{meet.subject}</p>
                      <p className="font-mono text-xs text-emerald-200">{meet.room_id}</p>
                      <p className="text-xs text-slate-500">
                        Cohort {meet.class_filter} · Ends in ~
                        {(() => {
                          const minsLeft = approximateMinutesRemaining(meet);
                          return minsLeft === null ? "?" : `${minsLeft.toFixed(1)}`;
                        })()}{" "}
                        min
                      </p>
                      <p className="mt-2 text-[11px] uppercase tracking-wide text-slate-400">
                        Roster:{" "}
                        {(meet.allowed_student_ids || [])
                          .map((id) => rosterLookup.get(Number(id))?.full_name || id)
                          .join(", ") || "(empty)"}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {teacherLocked && (
                        <Link
                          to={`/admin/meeting?room=${encodeURIComponent(meet.room_id)}`}
                          className="rounded-lg bg-emerald-600 px-3 py-1 text-xs font-medium text-white hover:bg-emerald-500"
                        >
                          Join meeting
                        </Link>
                      )}
                      <button
                        type="button"
                        className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-white hover:border-emerald-500"
                        onClick={() => beginEditMeeting(meet)}
                      >
                        Edit roster
                      </button>
                      <button
                        type="button"
                        className="rounded-lg border border-rose-900 px-3 py-1 text-xs text-rose-200 hover:bg-rose-950/40"
                        onClick={() => deleteMeeting(meet.room_id)}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                </div>
              ))}
              {meetings.length === 0 && <p className="text-xs text-slate-500">No meetings yet.</p>}
            </div>
          </section>

          {editingMeeting && (
            <section className="rounded-xl border border-amber-800/60 bg-amber-950/20 p-5 text-sm text-amber-50">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-xs uppercase text-amber-200">Editing roster for</p>
                  <p className="font-mono text-white">{editingMeeting.room_id}</p>
                </div>
                <button type="button" className="text-xs text-slate-300 underline" onClick={() => setEditingMeeting(null)}>
                  Close
                </button>
              </div>
              <div className="mt-4 max-h-48 space-y-2 overflow-y-auto rounded-lg border border-amber-900/40 bg-slate-950/40 p-3">
                {students.map((row) => {
                  const numericId = Number(row.id);
                  return (
                    <label key={numericId} className="flex items-center gap-2 text-xs text-white">
                      <input
                        type="checkbox"
                        className="h-4 w-4 accent-amber-500"
                        checked={editSelections.has(numericId)}
                        onChange={() => toggleStudentSelection(numericId, editSelections, setEditSelections)}
                      />
                      <span>
                        {row.full_name}{" "}
                        <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] uppercase text-slate-300">
                          {row.student_class || "—"}
                        </span>
                      </span>
                    </label>
                  );
                })}
              </div>
              <button
                type="button"
                className="mt-3 rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-slate-900"
                onClick={saveEditedMeeting}
              >
                Persist roster updates
              </button>
            </section>
          )}
        </div>
      )}

      {(studentOnly || role === "Student") && (
        <section className="rounded-xl border border-slate-800 bg-slate-900/40 p-6 space-y-4">
          {studentOnly && <h1 className="text-2xl font-semibold text-white">Join a class</h1>}
          <h2 className={`text-lg font-medium text-white ${studentOnly ? "mt-2" : ""}`}>Join curated class</h2>
          <label className="block text-sm text-slate-300">
            Faculty meeting ID
            <input
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm text-white"
              value={studentRoom}
              onChange={(e) => setStudentRoom(e.target.value)}
            />
          </label>
          {studentError && <p className="text-sm text-red-400">{studentError}</p>}
          <button
            type="button"
            disabled={studentLoading}
            onClick={lookupRoom}
            className="rounded-lg bg-slate-700 px-4 py-2 text-sm font-medium text-white hover:bg-slate-600 disabled:opacity-50"
          >
            {studentLoading ? "Checking…" : "Validate meeting"}
          </button>

          {sessionInfo?.found && (
            <div className="space-y-2 rounded-lg border border-slate-700 bg-slate-950/80 p-4 text-sm text-slate-300">
              <p>
                Subject: <span className="text-white">{sessionInfo.subject}</span> — Audience:{" "}
                <span className="text-white">{sessionInfo.class_filter}</span>
              </p>
              <p>
                Time remaining: <span className="text-white">{sessionInfo.minutes_left?.toFixed?.(1) ?? "?"} min</span>
              </p>
              {sessionInfo.meeting_closed && <p className="text-amber-400">This meeting window expired.</p>}
              {!sessionInfo.meeting_closed && (
                <p className="text-slate-400">
                  You must verify on the Verify page — the JWT must include this room hash or the API will deny access.
                </p>
              )}
            </div>
          )}

          {encodedRoom && sessionInfo?.found && !sessionInfo.meeting_closed && (
            <div className="flex flex-wrap gap-2 pt-2">
              <Link
                to={`/verify?room=${encodedRoom}`}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
              >
                Face verify + meeting token
              </Link>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
