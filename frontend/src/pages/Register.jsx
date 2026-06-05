import { useState } from "react";
import { api, API_PREFIX } from "../services/api.js";

export default function Register() {
  const [email, setEmail] = useState("");
  const [studentId, setStudentId] = useState("");
  const [classChoice, setClassChoice] = useState("A");
  const [customClass, setCustomClass] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [file, setFile] = useState(null);
  const [msg, setMsg] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!file) {
      setMsg("Choose a clear frontal photo.");
      return;
    }
    const resolvedClass =
      classChoice === "CUSTOM" ? customClass.trim().toUpperCase() : classChoice.trim().toUpperCase();
    if (!resolvedClass) {
      setMsg(classChoice === "CUSTOM" ? "Enter a custom class name." : "Select a class.");
      return;
    }
    setLoading(true);
    setMsg("");
    try {
      const fd = new FormData();
      fd.append("email", email);
      fd.append("student_external_id", studentId.trim());
      fd.append("student_class", resolvedClass);
      fd.append("full_name", fullName);
      if (password) fd.append("password", password);
      fd.append("file", file);
      const { data } = await api.post(`${API_PREFIX}/face/register-face`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setMsg(data.message + (data.user_id ? ` (user #${data.user_id})` : ""));
    } catch (err) {
      const d = err.response?.data;
      setMsg(typeof d?.detail === "string" ? d.detail : err.message || "Request failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-white">Register face</h1>
        <p className="mt-2 text-sm text-slate-400">
          Enrollment happens on the server using ArcFace embeddings. Use a well-lit frontal image.
        </p>
      </div>
      <form onSubmit={submit} className="space-y-4 rounded-xl border border-slate-800 bg-slate-900/50 p-6">
        <label className="block text-sm">
          <span className="text-slate-300">Official ID</span>
          <input
            className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 uppercase text-white"
            value={studentId}
            onChange={(e) => setStudentId(e.target.value.toUpperCase())}
            placeholder="Roll / employee number"
            required
          />
        </label>
        <label className="block text-sm">
          <span className="text-slate-300">Class / cohort</span>
          <select
            className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
            value={classChoice}
            onChange={(e) => setClassChoice(e.target.value)}
          >
            <option value="A">A</option>
            <option value="B">B</option>
            <option value="FACULTY">Faculty</option>
            <option value="CSE-A">CSE-A</option>
            <option value="IT-A">IT-A</option>
            <option value="CUSTOM">Custom…</option>
          </select>
        </label>
        {classChoice === "CUSTOM" && (
          <label className="block text-sm">
            <span className="text-slate-300">Custom class label</span>
            <input
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 uppercase text-white"
              value={customClass}
              onChange={(e) => setCustomClass(e.target.value)}
              placeholder="e.g. MECH-B"
            />
          </label>
        )}
        <label className="block text-sm">
          <span className="text-slate-300">Email</span>
          <input
            className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>
        <label className="block text-sm">
          <span className="text-slate-300">Full name</span>
          <input
            className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            required
          />
        </label>
        <label className="block text-sm">
          <span className="text-slate-300">Password (optional)</span>
          <input
            className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={8}
          />
        </label>
        <label className="block text-sm">
          <span className="text-slate-300">Face image</span>
          <input
            className="mt-1 w-full text-sm text-slate-300"
            type="file"
            accept="image/*"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            required
          />
        </label>
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-emerald-600 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
        >
          {loading ? "Uploading…" : "Register"}
        </button>
        {msg && <p className="text-sm text-slate-300">{msg}</p>}
      </form>
    </div>
  );
}
