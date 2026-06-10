"use client";

import { useEffect, useState } from "react";
import TransparencyDashboard from "../components/transparency_dashboard";
import NarrativeTracker from "../components/NarrativeTracker";
import PrebunkingPanel from "../components/PrebunkingPanel";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const PALETTE = {
  bg: "#EEF1F5", surface: "#FFFFFF", ink: "#16202B", muted: "#5C6B7A",
  hairline: "#D7DEE6", accent: "#1A3A5C", accent2: "#2E6DA4",
  green: "#1F6B50", amber: "#7A4A00",
};

const TABS = [
  { id: "dashboard", label: "Transparency Dashboard" },
  { id: "narratives", label: "Narrative Tracker" },
  { id: "prebunking", label: "Prebunking" },
  { id: "anchor",    label: "Audit Anchor" },
];

function AnchorView({ proof }: { proof: any }) {
  if (!proof) return null;
  return (
    <div style={{ fontFamily: "Arial", color: PALETTE.ink }}>
      <div style={{ fontSize: 15, fontWeight: 700, color: PALETTE.accent,
        marginBottom: 16 }}>Blockchain Audit Anchor</div>
      {[
        ["Report ID",    proof.report_id],
        ["Hash (keccak256)", proof.report_hash],
        ["Anchored at",  proof.anchored_at],
        ["On-chain",     proof.on_chain ? "✓ Yes" : "⚠ Pending"],
        ["Network",      proof.network],
        ["TX Hash",      proof.tx_hash || "—"],
        ["Block",        proof.block_number?.toString() || "—"],
        ["Contract",     proof.contract_address],
      ].map(([k, v]) => (
        <div key={k as string} style={{ display: "flex", gap: 12, marginBottom: 10,
          padding: "8px 12px", background: PALETTE.surface,
          border: `1px solid ${PALETTE.hairline}`, borderRadius: 6,
          fontSize: 13 }}>
          <span style={{ color: PALETTE.muted, minWidth: 140, flexShrink: 0,
            fontWeight: 600 }}>{k as string}</span>
          <span style={{ fontFamily: typeof v === "string" && v.startsWith("0x")
            ? "monospace" : "inherit",
            wordBreak: "break-all", color: PALETTE.ink }}>{v as string}</span>
        </div>
      ))}
      {proof.pending_reason && (
        <div style={{ fontSize: 12, color: PALETTE.amber, marginTop: 8,
          padding: "8px 12px", background: "#FFF8E1",
          borderRadius: 6, border: "1px solid #FFE0B2" }}>
          ⚠ {proof.pending_reason}
        </div>
      )}
    </div>
  );
}

export default function Home() {
  const [tab, setTab] = useState("dashboard");
  const [loading, setLoading] = useState(true);
  const [fullData, setFullData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // First try /demo for the dashboard data, then build the rest from it
    fetch(`${API_URL}/demo`)
      .then((r) => r.json())
      .then((d) => {
        // demo endpoint returns dashboard data; wrap in a full-data structure
        setFullData({ dashboard: d, narratives: null, prebunking: null, anchor: null });
        setLoading(false);
      })
      .catch(() => {
        setError("API unreachable — showing embedded demo data");
        setLoading(false);
      });
  }, []);

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center",
      minHeight: "100vh", fontFamily: "Arial", color: PALETTE.accent, fontSize: 18,
      background: PALETTE.bg }}>
      Loading NARRATIV…
    </div>
  );

  return (
    <div style={{ minHeight: "100vh", background: PALETTE.bg,
      fontFamily: "Arial" }}>
      {/* Top bar */}
      <div style={{ background: PALETTE.accent, color: "#fff",
        padding: "0 24px", display: "flex", alignItems: "center",
        justifyContent: "space-between", height: 52 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontWeight: 800, fontSize: 18, letterSpacing: "0.04em" }}>
            NARRATIV
          </span>
          <span style={{ opacity: 0.5, fontSize: 12 }}>
            Influence Operation Transparency
          </span>
        </div>
        <div style={{ fontSize: 11, opacity: 0.6 }}>
          Neuronium Engineers
        </div>
      </div>

      {/* Tabs */}
      <div style={{ background: PALETTE.surface,
        borderBottom: `1px solid ${PALETTE.hairline}`,
        padding: "0 24px", display: "flex", gap: 0 }}>
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{
            background: "none", border: "none", cursor: "pointer",
            padding: "14px 18px",
            borderBottom: tab === t.id
              ? `2px solid ${PALETTE.accent2}` : "2px solid transparent",
            color: tab === t.id ? PALETTE.accent2 : PALETTE.muted,
            fontWeight: tab === t.id ? 600 : 400,
            fontSize: 13, fontFamily: "Arial",
          }}>{t.label}</button>
        ))}
        {error && (
          <span style={{ marginLeft: "auto", alignSelf: "center",
            fontSize: 11, color: PALETTE.amber }}>{error}</span>
        )}
      </div>

      {/* Content */}
      <div style={{ padding: "24px", maxWidth: 1100, margin: "0 auto" }}>
        {tab === "dashboard" && (
          <TransparencyDashboard data={fullData?.dashboard ?? undefined} />
        )}
        {tab === "narratives" && (
          <NarrativeTracker data={fullData?.narratives} />
        )}
        {tab === "prebunking" && (
          <PrebunkingPanel data={fullData?.prebunking} />
        )}
        {tab === "anchor" && (
          <AnchorView proof={fullData?.anchor} />
        )}
      </div>
    </div>
  );
}
