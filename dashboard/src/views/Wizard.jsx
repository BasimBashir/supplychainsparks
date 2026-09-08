import React, { useEffect, useState } from "react";
import { apiGet, apiPost } from "../api.js";

export default function Wizard() {
  const [status, setStatus] = useState(null);
  const [form, setForm] = useState({ api_key: "", repo_url: "", git_token: "",
                                      schedule_hours: 6 });
  const [saved, setSaved] = useState("");

  async function refresh() { setStatus(await apiGet("/api/settings-status")); }
  useEffect(() => { refresh(); }, []);
  if (!status) return <p>loading…</p>;

  async function save() {
    await apiPost("/api/settings", form);
    setSaved("saved ✓");
    refresh();
  }

  return (
    <div className="wizard">
      <h2>Setup</h2>
      <ul>
        <li>{status.has_api_key ? "✓" : "✗"} API key (writer tier)</li>
        <li>{status.has_repo ? "✓" : "✗"} Content repo connected</li>
        <li>{status.ollama ? "✓" : "—"} Ollama local model (optional)</li>
        <li>fetch every {status.schedule_hours}h</li>
      </ul>
      <label>API key
        <input type="password" value={form.api_key}
               onChange={(e) => setForm({ ...form, api_key: e.target.value })} />
      </label>
      <label>Content repo URL
        <input value={form.repo_url}
               onChange={(e) => setForm({ ...form, repo_url: e.target.value })} />
      </label>
      <label>Git token
        <input type="password" value={form.git_token}
               onChange={(e) => setForm({ ...form, git_token: e.target.value })} />
      </label>
      <label>Fetch interval (hours)
        <input type="number" min="0" value={form.schedule_hours}
               onChange={(e) => setForm({ ...form, schedule_hours: Number(e.target.value) })} />
      </label>
      <button onClick={save}>Save</button> {saved}
    </div>
  );
}
