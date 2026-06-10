import React, { useState } from "react";

const PALETTE = {
  surface: "#FFFFFF", ink: "#16202B", muted: "#5C6B7A",
  hairline: "#D7DEE6", accent: "#1A3A5C", warn: "#7A4A00",
  warnBg: "#FFF8E1",
};

const LANG_FLAGS = { sq: "🇦🇱", de: "🇩🇪", en: "🇬🇧" };
const LANG_NAMES = { sq: "Shqip", de: "Deutsch", en: "English" };

const TECHNIQUE_LABELS = {
  coordinated_amplification: "Coordinated Amplification",
  copy_paste_campaign: "Copy-Paste Campaign",
  astroturfing: "Astroturfing",
  velocity_manipulation: "Velocity Manipulation",
  source_transparency: "Source Transparency",
};

function PrebunkCard({ card }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div style={{ background: PALETTE.surface,
      border: `1px solid ${PALETTE.hairline}`,
      borderRadius: 8, overflow: "hidden", marginBottom: 8 }}>
      {/* Header */}
      <div onClick={() => setExpanded(!expanded)} style={{
        background: PALETTE.warnBg,
        borderBottom: expanded ? `1px solid ${PALETTE.hairline}` : "none",
        padding: "10px 14px", cursor: "pointer",
        display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <div>
          <span style={{ fontSize: 13, marginRight: 8 }}>
            {LANG_FLAGS[card.language] || "🌐"}
          </span>
          <span style={{ fontSize: 13, fontWeight: 600, color: PALETTE.warn }}>
            {card.headline}
          </span>
        </div>
        <span style={{ fontSize: 12, color: PALETTE.muted }}>
          {expanded ? "▲" : "▼"}
        </span>
      </div>

      {expanded && (
        <div style={{ padding: "12px 14px" }}>
          <p style={{ fontSize: 13, color: PALETTE.ink, lineHeight: 1.6,
            marginBottom: 12 }}>{card.explanation}</p>

          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: PALETTE.muted,
              letterSpacing: "0.08em", textTransform: "uppercase",
              marginBottom: 6 }}>Warning Signs</div>
            {card.warning_signs.map((s, i) => (
              <div key={i} style={{ display: "flex", gap: 8, marginBottom: 4,
                fontSize: 12, color: PALETTE.ink }}>
                <span style={{ color: PALETTE.warn, flexShrink: 0 }}>⚠</span>
                <span>{s}</span>
              </div>
            ))}
          </div>

          <div>
            <div style={{ fontSize: 11, fontWeight: 700, color: PALETTE.muted,
              letterSpacing: "0.08em", textTransform: "uppercase",
              marginBottom: 6 }}>Verification Guide</div>
            <p style={{ fontSize: 12, color: PALETTE.ink, lineHeight: 1.6,
              margin: 0 }}>{card.verification_guide}</p>
          </div>
        </div>
      )}
    </div>
  );
}

export default function PrebunkingPanel({ data }) {
  const [langFilter, setLangFilter] = useState("all");
  const [techFilter, setTechFilter] = useState("all");

  if (!data || !data.cards || data.cards.length === 0) {
    return (
      <div style={{ background: PALETTE.surface,
        border: `1px solid ${PALETTE.hairline}`,
        borderRadius: 10, padding: 24, textAlign: "center",
        color: PALETTE.muted, fontFamily: "Arial", fontSize: 14 }}>
        No prebunking cards generated.
      </div>
    );
  }

  const techniques = [...new Set(data.cards.map(c => c.technique))];
  const languages  = [...new Set(data.cards.map(c => c.language))];

  const filtered = data.cards.filter(c =>
    (langFilter === "all" || c.language === langFilter) &&
    (techFilter === "all" || c.technique === techFilter)
  );

  return (
    <div style={{ fontFamily: "Arial", color: PALETTE.ink }}>
      {/* Header */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 15, fontWeight: 700, color: PALETTE.accent,
          marginBottom: 4 }}>Prebunking Cards</div>
        <div style={{ fontSize: 12, color: PALETTE.muted }}>
          {data.techniques_detected.length} technique{data.techniques_detected.length !== 1 ? "s" : ""} detected
          · {data.total_cards} cards generated
        </div>
        <div style={{ fontSize: 11, color: PALETTE.muted, marginTop: 4,
          fontStyle: "italic" }}>{data.methodology_note}</div>
      </div>

      {/* Filters */}
      <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
        <select value={langFilter} onChange={e => setLangFilter(e.target.value)}
          style={{ fontSize: 12, padding: "4px 8px", borderRadius: 6,
            border: `1px solid ${PALETTE.hairline}`, cursor: "pointer" }}>
          <option value="all">All languages</option>
          {languages.map(l => (
            <option key={l} value={l}>{LANG_FLAGS[l]} {LANG_NAMES[l] || l}</option>
          ))}
        </select>

        <select value={techFilter} onChange={e => setTechFilter(e.target.value)}
          style={{ fontSize: 12, padding: "4px 8px", borderRadius: 6,
            border: `1px solid ${PALETTE.hairline}`, cursor: "pointer" }}>
          <option value="all">All techniques</option>
          {techniques.map(t => (
            <option key={t} value={t}>{TECHNIQUE_LABELS[t] || t}</option>
          ))}
        </select>
      </div>

      {/* Cards */}
      {filtered.map((card, i) => <PrebunkCard key={i} card={card} />)}
    </div>
  );
}
