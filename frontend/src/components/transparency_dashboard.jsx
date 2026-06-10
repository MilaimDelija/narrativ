"use client";

import React, { useState, useMemo } from "react";
import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";

/*
  Amplification Transparency Dashboard — data-driven edition
  ----------------------------------------------------------
  Now consumes the CIB engine's output. Pass the JSON produced by
  dashboard_export.export_for_dashboard(...) as the `data` prop:

      <TransparencyDashboard data={reportJson} />

  In a deployed app, fetch dashboard_data.json (or call your API) and hand the
  result to this component. The DEFAULT_DATA below is a real engine run on the
  demo dataset, so this renders end-to-end with no wiring.

  It never says "fake" and never hides a post. It shows what each source
  contributed and lets the reader subtract any of them. The reader judges.
*/

const DEFAULT_DATA = {"topic": "#protesta", "generated_at": "2026-06-09T22:21:09.720696+00:00", "reach_unit": "activity-weighted estimate (1 + log followers)", "timeline": [{"label": "18:10", "minute": 0, "organic": 50.8, "coordinated": 0.0, "paid": 0.0}, {"label": "18:20", "minute": 10, "organic": 18.0, "coordinated": 0.0, "paid": 0.0}, {"label": "18:30", "minute": 20, "organic": 75.0, "coordinated": 0.0, "paid": 0.0}, {"label": "18:40", "minute": 30, "organic": 50.2, "coordinated": 145.9, "paid": 0.0}, {"label": "18:50", "minute": 40, "organic": 59.1, "coordinated": 0.0, "paid": 0.0}, {"label": "19:00", "minute": 50, "organic": 8.4, "coordinated": 0.0, "paid": 0.0}, {"label": "19:10", "minute": 60, "organic": 17.7, "coordinated": 0.0, "paid": 22.0}, {"label": "19:20", "minute": 70, "organic": 42.6, "coordinated": 0.0, "paid": 0.0}, {"label": "19:30", "minute": 80, "organic": 42.3, "coordinated": 145.9, "paid": 11.7}, {"label": "19:40", "minute": 90, "organic": 49.1, "coordinated": 0.0, "paid": 11.7}, {"label": "19:50", "minute": 100, "organic": 7.6, "coordinated": 0.0, "paid": 12.2}, {"label": "20:00", "minute": 110, "organic": 34.3, "coordinated": 0.0, "paid": 0.0}, {"label": "20:10", "minute": 120, "organic": 40.2, "coordinated": 0.0, "paid": 10.4}, {"label": "20:20", "minute": 130, "organic": 17.7, "coordinated": 0.0, "paid": 11.7}, {"label": "20:30", "minute": 140, "organic": 32.0, "coordinated": 145.9, "paid": 11.1}, {"label": "20:40", "minute": 150, "organic": 25.5, "coordinated": 0.0, "paid": 33.2}, {"label": "20:50", "minute": 160, "organic": 26.2, "coordinated": 0.0, "paid": 0.0}, {"label": "21:00", "minute": 170, "organic": 50.4, "coordinated": 0.0, "paid": 11.7}, {"label": "21:10", "minute": 180, "organic": 64.4, "coordinated": 0.0, "paid": 0.0}, {"label": "21:20", "minute": 190, "organic": 57.1, "coordinated": 0.0, "paid": 0.0}, {"label": "21:30", "minute": 200, "organic": 53.1, "coordinated": 0.0, "paid": 23.9}, {"label": "21:40", "minute": 210, "organic": 66.4, "coordinated": 0.0, "paid": 12.2}, {"label": "21:50", "minute": 220, "organic": 41.9, "coordinated": 0.0, "paid": 22.2}], "totals": {"organic": 930.1, "coordinated": 437.7, "paid": 194.0, "all": 1561.8}, "coordinated_markers": ["18:40", "19:30", "20:30"], "evidence": ["12 accounts flagged across multiple independent signals.", "A pod of 12 accounts with reciprocity 1.0 (closed mutual-amplification ring).", "6168 cross-account near-duplicate post pairs (shared copy)."], "clusters": [{"size": 12, "reciprocity": 1.0, "density": 0.182}], "flagged_count": 12, "tlp": "TLP:AMBER"};

const PALETTE = {
  bg: "#EEF1F5", surface: "#FFFFFF", ink: "#16202B", muted: "#5C6B7A",
  hairline: "#D7DEE6", organic: "#1F8A70", coordinated: "#C77800",
  paid: "#6B4FBB", accent: "#16202B",
};

const FONTS = `
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&family=Inter:wght@400;450;500&display=swap');
`;

const SOURCES = [
  { key: "organic", label: "Organic", color: PALETTE.organic,
    blurb: "Individual accounts acting independently. Irregular timing, varied wording." },
  { key: "coordinated", label: "Flagged for review", color: PALETTE.coordinated,
    blurb: "A cluster showing coordination signals. Flagged for a human to examine — not a verdict." },
  { key: "paid", label: "Disclosed paid", color: PALETTE.paid,
    blurb: "Reach from transparently sponsored posts." },
];

function Stat({ label, value, sub, color }) {
  return (
    <div style={{
      background: PALETTE.surface, border: `1px solid ${PALETTE.hairline}`,
      borderRadius: 10, padding: "14px 16px", flex: 1, minWidth: 150,
    }}>
      <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 11,
        letterSpacing: "0.08em", textTransform: "uppercase", color: PALETTE.muted }}>{label}</div>
      <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 28, fontWeight: 600,
        color: color || PALETTE.ink, marginTop: 4, lineHeight: 1.1 }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: PALETTE.muted, marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

export default function TransparencyDashboard({ data = DEFAULT_DATA }) {
  const [active, setActive] = useState({ organic: true, coordinated: true, paid: true });
  const T = data.totals || { organic: 0, coordinated: 0, paid: 0, all: 0 };
  const pct = (x) => (T.all ? Math.round((x / T.all) * 100) : 0);

  const series = useMemo(() => (data.timeline || []).map((d) => ({
    ...d,
    total:
      (active.organic ? d.organic : 0) +
      (active.coordinated ? d.coordinated : 0) +
      (active.paid ? d.paid : 0),
  })), [active, data]);

  const shownTotal = useMemo(
    () => series.reduce((a, d) => a + d.total, 0), [series]);

  const toggle = (k) => setActive((s) => ({ ...s, [k]: !s[k] }));
  const fmt = (n) => Math.round(n).toLocaleString();

  return (
    <div style={{ fontFamily: "'Inter', sans-serif", background: PALETTE.bg,
      color: PALETTE.ink, padding: 20, minHeight: "100%" }}>
      <style>{FONTS}{`
        .src-toggle:focus-visible { outline: 2px solid ${PALETTE.accent}; outline-offset: 2px; }
        @media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
      `}</style>

      <div style={{ maxWidth: 920, margin: "0 auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
          fontFamily: "'IBM Plex Mono', monospace", fontSize: 12,
          letterSpacing: "0.12em", textTransform: "uppercase", color: PALETTE.muted }}>
          <span>Amplification transparency</span>
          <span style={{ border: `1px solid ${PALETTE.hairline}`, borderRadius: 20,
            padding: "2px 10px", letterSpacing: "0.06em" }}>{data.tlp || "TLP:AMBER"} · from CIB engine</span>
        </div>
        <h1 style={{ fontFamily: "'Space Grotesk', sans-serif", fontSize: 34, fontWeight: 700,
          margin: "6px 0 6px", letterSpacing: "-0.02em" }}>
          How <span style={{ color: PALETTE.organic }}>{data.topic}</span> spread
        </h1>
        <p style={{ fontSize: 15, color: PALETTE.muted, maxWidth: 640, margin: 0, lineHeight: 1.5 }}>
          This shows what each source contributed to the topic's reach. Toggle any
          source to see the shape without it. Nothing here is hidden or removed —
          you decide what it means.
        </p>

        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", margin: "20px 0" }}>
          <Stat label="Total reach" value={fmt(T.all)} sub={data.reach_unit} />
          <Stat label="Organic" value={`${pct(T.organic)}%`} color={PALETTE.organic} sub={fmt(T.organic)} />
          <Stat label="Flagged" value={`${pct(T.coordinated)}%`} color={PALETTE.coordinated} sub={`${fmt(T.coordinated)} · for review`} />
          <Stat label="Paid" value={`${pct(T.paid)}%`} color={PALETTE.paid} sub={fmt(T.paid)} />
        </div>

        <div style={{ background: PALETTE.surface, border: `1px solid ${PALETTE.hairline}`,
          borderRadius: 12, padding: "18px 14px 8px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline",
            padding: "0 6px 10px" }}>
            <span style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600, fontSize: 15 }}>
              Reach over time
            </span>
            <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 12, color: PALETTE.muted }}>
              showing {fmt(shownTotal)} of {fmt(T.all)}
            </span>
          </div>
          <ResponsiveContainer width="100%" height={300}>
            <ComposedChart data={series} margin={{ top: 6, right: 10, left: -10, bottom: 0 }}>
              <defs>
                {SOURCES.map((s) => (
                  <linearGradient key={s.key} id={`g-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={s.color} stopOpacity={0.45} />
                    <stop offset="100%" stopColor={s.color} stopOpacity={0.04} />
                  </linearGradient>
                ))}
              </defs>
              <CartesianGrid stroke={PALETTE.hairline} strokeDasharray="2 4" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11, fontFamily: "'IBM Plex Mono', monospace", fill: PALETTE.muted }}
                interval={3} axisLine={{ stroke: PALETTE.hairline }} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fontFamily: "'IBM Plex Mono', monospace", fill: PALETTE.muted }}
                axisLine={false} tickLine={false} width={48} />
              <Tooltip contentStyle={{ background: PALETTE.surface, border: `1px solid ${PALETTE.hairline}`,
                borderRadius: 8, fontFamily: "'IBM Plex Mono', monospace", fontSize: 12 }}
                labelStyle={{ color: PALETTE.ink, fontWeight: 600 }} />
              {active.organic && (
                <Area type="monotone" dataKey="organic" stackId="1" stroke={PALETTE.organic}
                  strokeWidth={1.5} fill="url(#g-organic)" name="Organic" />
              )}
              {active.paid && (
                <Area type="monotone" dataKey="paid" stackId="1" stroke={PALETTE.paid}
                  strokeWidth={1.5} fill="url(#g-paid)" name="Disclosed paid" />
              )}
              {active.coordinated && (
                <Area type="monotone" dataKey="coordinated" stackId="1" stroke={PALETTE.coordinated}
                  strokeWidth={1.5} fill="url(#g-coordinated)" name="Flagged for review" />
              )}
              <Line type="monotone" dataKey="total" stroke={PALETTE.ink} strokeWidth={2}
                dot={false} name="Total shown" />
              {(data.coordinated_markers || []).map((m) => (
                <ReferenceLine key={m} x={m} stroke={PALETTE.coordinated}
                  strokeDasharray="3 3" strokeOpacity={0.5} />
              ))}
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 14 }}>
          {SOURCES.map((s) => {
            const on = active[s.key];
            return (
              <button key={s.key} className="src-toggle" onClick={() => toggle(s.key)} aria-pressed={on}
                style={{ flex: 1, minWidth: 220, textAlign: "left", cursor: "pointer",
                  background: on ? PALETTE.surface : "#E4E9EF",
                  border: `1px solid ${on ? s.color : PALETTE.hairline}`,
                  borderLeft: `4px solid ${on ? s.color : PALETTE.hairline}`,
                  borderRadius: 10, padding: "12px 14px",
                  opacity: on ? 1 : 0.62, transition: "all 0.18s ease" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600, fontSize: 14, color: s.color }}>
                    {s.label}
                  </span>
                  <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 11,
                    color: PALETTE.muted, border: `1px solid ${PALETTE.hairline}`,
                    borderRadius: 20, padding: "1px 8px" }}>{on ? "shown" : "hidden"}</span>
                </div>
                <div style={{ fontSize: 12.5, color: PALETTE.muted, marginTop: 5, lineHeight: 1.45 }}>
                  {s.blurb}
                </div>
              </button>
            );
          })}
        </div>

        <div style={{ background: PALETTE.surface, border: `1px solid ${PALETTE.hairline}`,
          borderLeft: `4px solid ${PALETTE.coordinated}`, borderRadius: 10,
          padding: "16px 18px", marginTop: 16 }}>
          <div style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600, fontSize: 15, marginBottom: 8 }}>
            Why was part of this flagged for review?
          </div>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13.5, color: PALETTE.ink, lineHeight: 1.6 }}>
            {(data.evidence || []).map((e, i) => <li key={i}>{e}</li>)}
          </ul>
          <div style={{ marginTop: 12, fontSize: 12.5, color: PALETTE.muted, fontStyle: "italic",
            borderTop: `1px solid ${PALETTE.hairline}`, paddingTop: 10, lineHeight: 1.5 }}>
            These are signals, not a verdict. Authentic movements coordinate too. This
            is surfaced so a person can examine the evidence and decide — it is never
            used to remove or hide anyone.
          </div>
        </div>

        <div style={{ textAlign: "center", fontFamily: "'IBM Plex Mono', monospace",
          fontSize: 11, color: PALETTE.muted, marginTop: 18, letterSpacing: "0.04em" }}>
          {data.flagged_count || 0} accounts flagged · Neuronium Engineers · transparency, not suppression
        </div>
      </div>
    </div>
  );
}
