import React, { useEffect, useState } from "react";
import { apiGet, apiPost } from "../api.js";

const EMPTY_FORM = { name: "", kind: "rss", url: "", credibility: "0.5",
                     category_hint: "", link_pattern: "" };

export default function SourcesView() {
  const [sources, setSources] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [note, setNote] = useState(null);   // {kind: "ok"|"error", text}

  async function refresh() {
    try { setSources((await apiGet("/api/sources")).sources); }
    catch (e) { setNote({ kind: "error", text: String(e) }); }
  }
  useEffect(() => { refresh(); }, []);

  function set(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  async function addSource(e) {
    e.preventDefault();
    setNote(null);
    try {
      const payload = {
        name: form.name.trim(), kind: form.kind,
        url: form.kind === "search" ? null : form.url.trim(),
        topic: form.kind === "search" ? form.url.trim() : null,
        credibility: parseFloat(form.credibility) || 0.5,
        category_hint: form.category_hint.trim() || null,
        link_pattern: form.kind === "html" ? (form.link_pattern.trim() || null) : null,
      };
      const r = await apiPost("/api/sources", payload);
      setNote({ kind: "ok", text: `${r.status === "updated" ? "Updated" : "Added"} `
                                + `“${payload.name}”` });
      setForm(EMPTY_FORM);
      refresh();
    } catch (e) {
      setNote({ kind: "error",
                text: `Could not add source — ${e} (name + http(s) url, `
                      + `or a topic for web search, required)` });
    }
  }

  async function toggle(s) {
    try {
      await apiPost(`/api/sources/${s.id}/toggle`, { enabled: !s.enabled });
      refresh();
    } catch (e) { setNote({ kind: "error", text: String(e) }); }
  }

  async function remove(s) {
    if (!window.confirm(`Delete source “${s.name}”?\n\nIts articles and stories ` +
                        `built only from it are removed too. This cannot be undone.`))
      return;
    try {
      await apiPost(`/api/sources/${s.id}/delete`);
      setNote({ kind: "ok", text: `Deleted “${s.name}”` });
      refresh();
    } catch (e) { setNote({ kind: "error", text: String(e) }); }
  }

  return (
    <div className="sources">
      <form className="source-form card" onSubmit={addSource}>
        <h3 className="card-title">Add a source</h3>
        <p className="card-sub">RSS feeds work best. HTML pages are scanned for
          links matching a pattern (default: <code>press|news|article</code>).
          A <b>web search</b> source runs a keyless DuckDuckGo news search on
          your topic every cycle — add as many topics as you like.</p>
        <div className="form-grid">
          <label>
            <span>Name</span>
            <input value={form.name} onChange={(e) => set("name", e.target.value)}
                   placeholder="Mawani press releases" required />
          </label>
          <label>
            <span>Type</span>
            <select value={form.kind} onChange={(e) => set("kind", e.target.value)}>
              <option value="rss">RSS feed</option>
              <option value="html">HTML page</option>
              <option value="search">Web search (topic)</option>
            </select>
          </label>
          <label className="span-2">
            <span>{form.kind === "search" ? "Topic" : "URL"}</span>
            <input value={form.url} onChange={(e) => set("url", e.target.value)}
                   placeholder={form.kind === "search"
                     ? "“Red Sea” shipping disruptions"
                     : "https://example.com/rss"} required />
          </label>
          <label>
            <span>Credibility (0–1)</span>
            <input type="number" min="0" max="1" step="0.1"
                   value={form.credibility}
                   onChange={(e) => set("credibility", e.target.value)} />
          </label>
          <label>
            <span>Category hint <i>(optional)</i></span>
            <input value={form.category_hint}
                   onChange={(e) => set("category_hint", e.target.value)}
                   placeholder="ports-shipping" />
          </label>
          {form.kind === "html" && (
            <label className="span-2">
              <span>Link pattern (regex, HTML only)</span>
              <input value={form.link_pattern}
                     onChange={(e) => set("link_pattern", e.target.value)}
                     placeholder="press|news|article" />
            </label>
          )}
        </div>
        <div className="form-actions">
          <button className="btn accent" type="submit">Add source</button>
        </div>
      </form>

      {note && <div className={`flash ${note.kind}`}>{note.text}</div>}

      {sources !== null && !sources.length && (
        <div className="empty">No sources yet — add one above.</div>
      )}

      {sources?.map((s) => (
        <div key={s.id} className={`source-row card ${s.enabled ? "" : "off"}`}>
          <div className="source-main">
            <div className="story-head">
              <span className="badge ghost">{s.kind}</span>
              <span className={`badge ${s.healthy ? "high" : "low"}`}>
                {s.healthy ? "healthy" : "unhealthy"}
              </span>
              {!s.enabled && <span className="badge ghost">disabled</span>}
              {s.category_hint && <span className="badge ghost">{s.category_hint}</span>}
            </div>
            <h3 className="story-title">{s.name}</h3>
            <p className="source-url">{s.kind === "search"
              ? `🔍 topic — ${s.url}` : s.url}</p>
            <span className="cred">credibility {Number(s.credibility).toFixed(1)}</span>
          </div>
          <div className="source-actions">
            <button className={`btn subtle small ${s.enabled ? "" : "accent"}`}
                    onClick={() => toggle(s)}>
              {s.enabled ? "Disable" : "Enable"}
            </button>
            <button className="btn danger small" onClick={() => remove(s)}>Delete</button>
          </div>
        </div>
      ))}
    </div>
  );
}
