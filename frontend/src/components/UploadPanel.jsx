"use client";

import React, { useState, useRef } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const PALETTE = {
  surface: "#FFFFFF", ink: "#16202B", muted: "#5C6B7A",
  hairline: "#D7DEE6", accent: "#1A3A5C", accent2: "#2E6DA4",
  green: "#1F6B50", greenBg: "#E8F5F0", error: "#C0392B",
};

export default function UploadPanel({ onResult }) {
  const [mode, setMode]         = useState("upload");  // upload | twitter | telegram
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState(null);
  const [success, setSuccess]   = useState(null);
  const [topic, setTopic]       = useState("");
  const [query, setQuery]       = useState("");
  const [limit, setLimit]       = useState(200);
  const fileRef                 = useRef(null);

  const MODES = [
    { id: "upload",   label: "📁 CSV / JSON" },
    { id: "twitter",  label: "𝕏 Twitter/X" },
    { id: "telegram", label: "✈️ Telegram" },
  ];

  async function run() {
    setLoading(true); setError(null); setSuccess(null);
    try {
      let res;
      if (mode === "upload") {
        const file = fileRef.current?.files?.[0];
        if (!file) throw new Error("No file selected");
        const form = new FormData();
        form.append("file", file);
        form.append("topic", topic || file.name);
        form.append("tlp", "TLP:AMBER");
        res = await fetch(`${API_URL}/ingest/upload`, { method: "POST", body: form });
      } else if (mode === "twitter") {
        res = await fetch(`${API_URL}/ingest/twitter`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query, limit, topic: topic || query }),
        });
      } else {
        res = await fetch(`${API_URL}/ingest/telegram`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ channels: query, limit, topic: topic || query }),
        });
      }
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail?.message || d.detail || res.statusText);
      }
      const data = await res.json();
      setSuccess(`${data.total_fetched} posts analyzed — ${data.cib?.summary?.flagged_for_review ?? 0} flagged`);
      onResult?.(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ background: PALETTE.surface,
      border: `1px solid ${PALETTE.hairline}`, borderRadius: 10,
      padding: "20px 24px", fontFamily: "Arial", color: PALETTE.ink,
      maxWidth: 560 }}>

      <div style={{ fontSize: 15, fontWeight: 700, color: PALETTE.accent,
        marginBottom: 16 }}>New Analysis</div>

      {/* Mode selector */}
      <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
        {MODES.map(m => (
          <button key={m.id} onClick={() => setMode(m.id)} style={{
            padding: "6px 14px", borderRadius: 6, cursor: "pointer",
            fontSize: 13, fontFamily: "Arial",
            background: mode === m.id ? PALETTE.accent2 : "#F0F4F8",
            color: mode === m.id ? "#fff" : PALETTE.muted,
            border: "none", fontWeight: mode === m.id ? 600 : 400,
          }}>{m.label}</button>
        ))}
      </div>

      {/* Inputs */}
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {mode === "upload" ? (
          <div>
            <div style={{ fontSize: 12, color: PALETTE.muted, marginBottom: 6 }}>
              CSV or JSON file (see docs for format)
            </div>
            <input ref={fileRef} type="file" accept=".csv,.json"
              style={{ fontSize: 13, width: "100%" }} />
          </div>
        ) : (
          <div>
            <div style={{ fontSize: 12, color: PALETTE.muted, marginBottom: 6 }}>
              {mode === "twitter"
                ? "Query or hashtag (e.g. #protesta)"
                : "Channel usernames, comma-separated (e.g. gazetamapo,panorama_al)"}
            </div>
            <input value={query} onChange={e => setQuery(e.target.value)}
              placeholder={mode === "twitter" ? "#protesta" : "gazetamapo,panorama_al"}
              style={{ width: "100%", padding: "8px 10px", borderRadius: 6,
                border: `1px solid ${PALETTE.hairline}`, fontSize: 13,
                fontFamily: "Arial" }} />
          </div>
        )}

        <div style={{ display: "flex", gap: 10 }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 12, color: PALETTE.muted, marginBottom: 4 }}>
              Topic label
            </div>
            <input value={topic} onChange={e => setTopic(e.target.value)}
              placeholder="#topic"
              style={{ width: "100%", padding: "8px 10px", borderRadius: 6,
                border: `1px solid ${PALETTE.hairline}`, fontSize: 13,
                fontFamily: "Arial" }} />
          </div>
          {mode !== "upload" && (
            <div>
              <div style={{ fontSize: 12, color: PALETTE.muted, marginBottom: 4 }}>
                Limit
              </div>
              <input type="number" value={limit}
                onChange={e => setLimit(Number(e.target.value))}
                style={{ width: 80, padding: "8px 10px", borderRadius: 6,
                  border: `1px solid ${PALETTE.hairline}`, fontSize: 13,
                  fontFamily: "Arial" }} />
            </div>
          )}
        </div>
      </div>

      <button onClick={run} disabled={loading} style={{
        marginTop: 16, width: "100%", padding: "10px 0",
        background: loading ? "#B0BEC5" : PALETTE.accent,
        color: "#fff", border: "none", borderRadius: 6,
        fontSize: 14, fontWeight: 600, cursor: loading ? "default" : "pointer",
        fontFamily: "Arial",
      }}>
        {loading ? "Analyzing…" : "Run Analysis"}
      </button>

      {error && (
        <div style={{ marginTop: 12, padding: "8px 12px", borderRadius: 6,
          background: "#FEE", border: `1px solid ${PALETTE.error}`,
          fontSize: 13, color: PALETTE.error }}>⚠ {error}</div>
      )}
      {success && (
        <div style={{ marginTop: 12, padding: "8px 12px", borderRadius: 6,
          background: PALETTE.greenBg, border: `1px solid ${PALETTE.green}`,
          fontSize: 13, color: PALETTE.green }}>✓ {success}</div>
      )}
    </div>
  );
}
