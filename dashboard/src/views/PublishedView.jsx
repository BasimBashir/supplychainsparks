import React, { useEffect, useState } from "react";
import { apiGet } from "../api.js";

export default function PublishedView() {
  const [pubs, setPubs] = useState(null);
  useEffect(() => { apiGet("/api/publications").then((d) => setPubs(d.publications)); }, []);
  if (!pubs) return <p>loading…</p>;
  return (
    <div>
      <h2>Published</h2>
      {!pubs.length && <p className="empty">Nothing published yet.</p>}
      <table>
        <thead>
          <tr><th>when</th><th>title</th><th>destination</th><th>url</th></tr>
        </thead>
        <tbody>{pubs.map((p) => (
          <tr key={p.id}>
            <td>{p.published_at?.replace("T", " ").slice(0, 16)}</td>
            <td>{p.title}</td>
            <td>{p.destination}{p.detail ? ` (${p.detail})` : ""}</td>
            <td>{p.url
              ? <a href={p.url} target="_blank" rel="noreferrer">{p.url}</a>
              : "—"}</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}
