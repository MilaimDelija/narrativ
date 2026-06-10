import React, { useState } from "react";
import NetworkGraph from "./NetworkGraph";

const PALETTE = {
  bg: "#EEF1F5", surface: "#FFFFFF", ink: "#16202B", muted: "#5C6B7A",
  hairline: "#D7DEE6", origin: "#C0392B", early: "#E67E22",
  amplifier: "#2E6DA4", accent: "#1A3A5C",
};

const ROLE_COLORS = {
  origin: "#C0392B", early_spreader: "#E67E22",
  amplifier: "#2E6DA4", late_adopter: "#7F8C8D",
};

function RoleBadge({ role }) {
  const labels = {
    origin: "Origin", early_spreader: "Early spreader",
    amplifier: "Amplifier", late_adopter: "Late adopter",
  };
  return (
    <span style={{ background: ROLE_COLORS[role] || "#999",
      color: "#fff", borderRadius: 4, padding: "2px 7px",
      fontSize: 10, fontWeight: 600, letterSpacing: "0.05em" }}>
      {labels[role] || role}
    </span>
  );
}

function NarrativeCard({ narrative, index, isSelected, onClick }) {
  const s = narrative.spread;
  return (
    <div onClick={onClick} style={{
      background: isSelected ? "#EAF2FB" : PALETTE.surface,
      border: `1px solid ${isSelected ? "#2E6DA4" : PALETTE.hairline}`,
      borderRadius: 8, padding: "12px 16px", cursor: "pointer",
      marginBottom: 8, transition: "all 0.15s",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between",
        alignItems: "flex-start", marginBottom: 6 }}>
        <span style={{ fontSize: 11, color: PALETTE.muted,
          fontFamily: "monospace" }}>#{index + 1}</span>
        <span style={{ fontSize: 11, background: "#1A3A5C", color: "#fff",
          borderRadius: 4, padding: "2px 7px" }}>
          reach ~{Math.round(s.reach_estimate)}
        </span>
      </div>
      <div style={{ fontSize: 13, color: PALETTE.ink, marginBottom: 8,
        lineHeight: 1.4, fontStyle: "italic" }}>
        "{narrative.origin.text.slice(0, 100)}{narrative.origin.text.length > 100 ? "…" : ""}"
      </div>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", fontSize: 12,
        color: PALETTE.muted }}>
        <span>👤 {s.total_accounts} accounts</span>
        <span>📝 {s.total_posts} posts</span>
        <span>⏱ {s.duration_minutes} min</span>
        <span>🔁 {s.mutation_count} mutations</span>
        {s.velocity_accounts_per_hour > 0 && (
          <span style={{ color: s.velocity_accounts_per_hour > 20 ? "#C0392B" : PALETTE.muted }}>
            ⚡ {s.velocity_accounts_per_hour} acc/hr
          </span>
        )}
      </div>
    </div>
  );
}

function ProvenanceTimeline({ nodes }) {
  const sorted = [...nodes].sort((a, b) => a.minute_offset - b.minute_offset);
  return (
    <div style={{ maxHeight: 320, overflowY: "auto", paddingRight: 4 }}>
      {sorted.map((n, i) => (
        <div key={i} style={{ display: "flex", gap: 10, marginBottom: 10,
          fontSize: 12, color: PALETTE.ink }}>
          <div style={{ width: 44, flexShrink: 0, textAlign: "right",
            color: PALETTE.muted, fontFamily: "monospace", paddingTop: 2 }}>
            +{n.minute_offset}m
          </div>
          <div style={{ width: 2, background: PALETTE.hairline,
            borderRadius: 2, flexShrink: 0 }} />
          <div>
            <div style={{ display: "flex", alignItems: "center",
              gap: 6, marginBottom: 3 }}>
              <RoleBadge role={n.role} />
              <span style={{ fontWeight: 600 }}>{n.account_id}</span>
            </div>
            <div style={{ color: PALETTE.muted, fontStyle: "italic", lineHeight: 1.4 }}>
              "{n.text_snippet.slice(0, 90)}{n.text_snippet.length > 90 ? "…" : ""}"
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function NarrativeTracker({ data }) {
  const [selected, setSelected] = useState(0);

  if (!data || !data.narratives || data.narratives.length === 0) {
    return (
      <div style={{ background: PALETTE.surface,
        border: `1px solid ${PALETTE.hairline}`,
        borderRadius: 10, padding: 24, textAlign: "center",
        color: PALETTE.muted, fontFamily: "Arial", fontSize: 14 }}>
        No narrative atoms detected in this dataset.
      </div>
    );
  }

  const narratives = data.narratives;
  const active = narratives[selected];

  return (
    <div style={{ fontFamily: "Arial", color: PALETTE.ink }}>
      {/* Header */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 15, fontWeight: 700, color: PALETTE.accent,
          marginBottom: 4 }}>Narrative Tracker</div>
        <div style={{ fontSize: 12, color: PALETTE.muted }}>
          {data.narrative_atoms_detected} narrative atom{data.narrative_atoms_detected !== 1 ? "s" : ""} detected
          across {data.total_posts_analyzed} posts
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1.4fr",
        gap: 16, alignItems: "start" }}>
        {/* Left: narrative list */}
        <div>
          {narratives.map((n, i) => (
            <NarrativeCard key={n.atom_id} narrative={n} index={i}
              isSelected={i === selected}
              onClick={() => setSelected(i)} />
          ))}
        </div>

        {/* Right: detail */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Network graph */}
          <NetworkGraph
            nodes={active.graph.nodes}
            edges={active.graph.edges}
            title={`Spread graph — atom #${selected + 1}`}
          />

          {/* Provenance timeline */}
          <div style={{ background: PALETTE.surface,
            border: `1px solid ${PALETTE.hairline}`,
            borderRadius: 10, padding: "14px 16px" }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: PALETTE.accent,
              marginBottom: 12 }}>Provenance Timeline</div>
            <ProvenanceTimeline nodes={active.provenance_chain} />
          </div>
        </div>
      </div>
    </div>
  );
}
