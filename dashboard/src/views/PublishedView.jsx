import React, { useEffect, useState } from "react";
import { apiGet } from "../api.js";

export default function PublishedView() {
  const [pubs, setPubs] = useState(null);
  useEffect(() => { apiGet("/api/publications").then((d) => setPubs(d.publications)); }, []);
  if (!pubs) return <p className="empty">loading…</p>;
  return (
    <div>
      {!pubs.length && (
        <div className="empty">
          <span className="big">✓</span>
          Nothing published yet. Approved stories appear here with their live
          links and timestamps.
        </div>
      )}
      {!!pubs.length && (
        <table>
          <thead>
            <tr><th>Published</th><th>Story</th><th>Destination</th><th>Link</th></tr>
          </thead>
          <tbody>{pubs.map((p) => (
            <tr key={p.id}>
              <td className="mono">{p.published_at?.replace("T", " ").slice(0, 16)}</td>
              <td>{p.title}</td>
              <td>{p.destination}{p.detail ? ` (${p.detail})` : ""}</td>
              <td>{p.url
                ? <a href={p.url} target="_blank" rel="noreferrer">{p.url}</a>
                : <span className="hint">copied to LinkedIn</span>}</td>
            </tr>
          ))}</tbody>
        </table>
      )}
    </div>
  );
}
