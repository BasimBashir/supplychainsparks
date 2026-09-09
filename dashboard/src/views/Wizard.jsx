import React, { useEffect, useState } from "react";
import { apiGet, apiPost } from "../api.js";

export default function Wizard({ onSaved }) {
  const [status, setStatus] = useState(null);
  const [form, setForm] = useState({
    default_tier: "api", api_key: "", api_model: "glm-4-flash",
    local_model: "qwen2.5:3b", repo_url: "", git_token: "", schedule_hours: 6,
  });
  const [saved, setSaved] = useState("");
  const [saving, setSaving] = useState(false);

  async function refresh() {
    try {
      const s = await apiGet("/api/settings-status");
      setStatus(s);
      setForm((f) => ({
        ...f,
        default_tier: s.default_tier || "api",
        api_model: s.api_model || f.api_model,
        local_model: s.local_model || f.local_model,
        schedule_hours: s.schedule_hours ?? f.schedule_hours,
      }));
    } catch { /* server away */ }
  }
  useEffect(() => { refresh(); }, []);
  if (!status) return <p className="empty">loading…</p>;

  async function save() {
    setSaving(true);
    setSaved("");
    try {
      await apiPost("/api/settings", form);
      setSaved("saved ✓");
      await refresh();
      onSaved?.();
    } catch (e) {
      setSaved(`could not save: ${e}`);
    } finally { setSaving(false); }
  }

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  return (
    <div className="setup">
      <section className="setup-section">
        <h3>Engine</h3>
        <p className="hint">
          Choose where the AI work happens — scoring every story, writing
          articles and posts, and fact-checking.
        </p>
        <div className="tier-cards">
          <button type="button"
                  className={`tier-card ${form.default_tier === "api" ? "selected" : ""}`}
                  onClick={() => setForm({ ...form, default_tier: "api" })}>
            <div className="t-name">☁️ Cloud API</div>
            <div className="t-desc">
              Best quality and speed. Uses your API key; typically a few cents
              per day.
            </div>
          </button>
          <button type="button"
                  className={`tier-card ${form.default_tier === "local" ? "selected" : ""}`}
                  onClick={() => setForm({ ...form, default_tier: "local" })}>
            <div className="t-name">🖥️ Local only · Ollama</div>
            <div className="t-desc">
              Everything runs on this PC through Ollama — no API key, no cloud,
              fully offline. Quality is lower and generation is slower.
            </div>
          </button>
        </div>

        {form.default_tier === "api" ? (
          <div className="field">
            <label>Cloud API key</label>
            <input type="password" value={form.api_key} onChange={set("api_key")}
                   placeholder={status.has_api_key ? "•••••• (saved)" : "paste your key"} />
          </div>
        ) : (
          <div className="field">
            <label>Ollama status</label>
            <div>
              {status.ollama
                ? <span className="setup-ok">✓ Ollama detected — local mode ready</span>
                : <span className="hint">Ollama is not running. Install it from
                  ollama.com, run <code>ollama pull {form.local_model}</code>, then
                  start it with <code>ollama serve</code>.</span>}
            </div>
          </div>
        )}
      </section>

      <section className="setup-section">
        <h3>Models</h3>
        <p className="hint">
          Model names are sent with every request. Change them to use a
          stronger or cheaper model.
        </p>
        <div className="field">
          <label>Cloud model (any OpenAI-compatible endpoint)</label>
          <input value={form.api_model} onChange={set("api_model")}
                 placeholder="glm-4-flash" />
        </div>
        <div className="field">
          <label>Ollama model (must be pulled locally)</label>
          <input value={form.local_model} onChange={set("local_model")}
                 placeholder="qwen2.5:3b" />
        </div>
      </section>

      <section className="setup-section">
        <h3>Website publishing</h3>
        <p className="hint">
          <b>What is the content repo?</b> It is a plain GitHub repository that
          stores your published articles as files — one folder per story
          (<code>content/posts/&lt;slug&gt;</code> with English, Arabic and
          metadata). The website (supplychainsparks.com) is built directly from
          this repository: every time the app publishes, it commits the new
          article and the site rebuilds itself in about a minute. The repo is
          the bridge between this app and the website — your PC can be off and
          the site stays up.
        </p>
        <div className="field">
          <label>Repository URL</label>
          <input value={form.repo_url} onChange={set("repo_url")}
                 placeholder={status.has_repo ? "(saved)" : "https://github.com/you/sparks-content.git"} />
        </div>
        <div className="field">
          <label>GitHub token (fine-grained, Contents: Read and write)</label>
          <input type="password" value={form.git_token} onChange={set("git_token")}
                 placeholder="github_pat_…" />
        </div>
      </section>

      <section className="setup-section">
        <h3>Schedule</h3>
        <p className="hint">
          How often to fetch and rank new stories automatically. 0 disables
          scheduling — you fetch manually.
        </p>
        <div className="field">
          <label>Fetch interval (hours)</label>
          <input type="number" min="0" step="1" value={form.schedule_hours}
                 onChange={(e) => setForm({ ...form, schedule_hours: Number(e.target.value) })} />
        </div>
      </section>

      <div className="card-actions">
        <button className="btn accent" onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save settings"}
        </button>
        {saved && <span className="setup-ok">{saved}</span>}
      </div>
    </div>
  );
}
