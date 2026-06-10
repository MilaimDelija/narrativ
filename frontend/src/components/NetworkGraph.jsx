import React, { useEffect, useRef, useState } from "react";

const PALETTE = {
  bg: "#EEF1F5", surface: "#FFFFFF", ink: "#16202B", muted: "#5C6B7A",
  hairline: "#D7DEE6", origin: "#C0392B", early: "#E67E22",
  amplifier: "#2E6DA4", late: "#7F8C8D", edge: "#B0BEC5",
};

const ROLES = {
  origin: { color: PALETTE.origin, r: 14, label: "Origin" },
  early_spreader: { color: PALETTE.early, r: 11, label: "Early spreader" },
  amplifier: { color: PALETTE.amplifier, r: 9, label: "Amplifier" },
  late_adopter: { color: PALETTE.late, r: 7, label: "Late adopter" },
};

function forceLayout(nodes, edges, width, height, iterations = 120) {
  const pos = {};
  nodes.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / nodes.length;
    pos[n.id] = {
      x: width / 2 + (width * 0.35) * Math.cos(angle),
      y: height / 2 + (height * 0.35) * Math.sin(angle),
    };
  });

  const k = Math.sqrt((width * height) / Math.max(nodes.length, 1));
  for (let iter = 0; iter < iterations; iter++) {
    const t = 1 - iter / iterations;
    const disp = {};
    nodes.forEach((n) => { disp[n.id] = { x: 0, y: 0 }; });

    // repulsion
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        const dx = pos[a.id].x - pos[b.id].x;
        const dy = pos[a.id].y - pos[b.id].y;
        const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 0.01);
        const force = (k * k) / dist;
        disp[a.id].x += (dx / dist) * force;
        disp[a.id].y += (dy / dist) * force;
        disp[b.id].x -= (dx / dist) * force;
        disp[b.id].y -= (dy / dist) * force;
      }
    }

    // attraction
    edges.forEach(({ source, target }) => {
      if (!pos[source] || !pos[target]) return;
      const dx = pos[source].x - pos[target].x;
      const dy = pos[source].y - pos[target].y;
      const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 0.01);
      const force = (dist * dist) / k;
      disp[source].x -= (dx / dist) * force;
      disp[source].y -= (dy / dist) * force;
      disp[target].x += (dx / dist) * force;
      disp[target].y += (dy / dist) * force;
    });

    // apply with cooling
    nodes.forEach((n) => {
      const mag = Math.sqrt(disp[n.id].x ** 2 + disp[n.id].y ** 2);
      if (mag > 0) {
        const step = Math.min(mag, t * k * 2);
        pos[n.id].x = Math.max(30, Math.min(width - 30,
          pos[n.id].x + (disp[n.id].x / mag) * step));
        pos[n.id].y = Math.max(30, Math.min(height - 30,
          pos[n.id].y + (disp[n.id].y / mag) * step));
      }
    });
  }
  return pos;
}

export default function NetworkGraph({ nodes = [], edges = [], title = "Amplification Network" }) {
  const svgRef = useRef(null);
  const [pos, setPos] = useState({});
  const [hovered, setHovered] = useState(null);
  const W = 640, H = 420;

  useEffect(() => {
    if (nodes.length === 0) return;
    const p = forceLayout(nodes, edges, W, H);
    setPos(p);
  }, [nodes, edges]);

  if (nodes.length === 0) {
    return (
      <div style={{ background: PALETTE.surface, border: `1px solid ${PALETTE.hairline}`,
        borderRadius: 10, padding: 24, textAlign: "center", color: PALETTE.muted,
        fontFamily: "Arial", fontSize: 14 }}>
        No network data available.
      </div>
    );
  }

  return (
    <div style={{ background: PALETTE.surface, border: `1px solid ${PALETTE.hairline}`,
      borderRadius: 10, padding: "16px 20px", fontFamily: "Arial" }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: PALETTE.ink,
        marginBottom: 12, letterSpacing: "0.02em" }}>{title}</div>

      <svg ref={svgRef} width="100%" viewBox={`0 0 ${W} ${H}`}
        style={{ background: PALETTE.bg, borderRadius: 8 }}>
        <defs>
          <marker id="arrow" markerWidth="6" markerHeight="6"
            refX="5" refY="3" orient="auto">
            <path d="M0,0 L6,3 L0,6 Z" fill={PALETTE.edge} />
          </marker>
        </defs>

        {edges.map((e, i) => {
          const s = pos[e.source], t = pos[e.target];
          if (!s || !t) return null;
          return (
            <line key={i} x1={s.x} y1={s.y} x2={t.x} y2={t.y}
              stroke={PALETTE.edge} strokeWidth={1.2} opacity={0.6}
              markerEnd="url(#arrow)" />
          );
        })}

        {nodes.map((n) => {
          const p = pos[n.id];
          if (!p) return null;
          const role = ROLES[n.role] || ROLES.amplifier;
          const isHovered = hovered === n.id;
          return (
            <g key={n.id} style={{ cursor: "pointer" }}
              onMouseEnter={() => setHovered(n.id)}
              onMouseLeave={() => setHovered(null)}>
              <circle cx={p.x} cy={p.y} r={role.r + (isHovered ? 3 : 0)}
                fill={role.color} opacity={0.85}
                stroke={isHovered ? PALETTE.ink : "none"} strokeWidth={2} />
              {isHovered && (
                <text x={p.x} y={p.y - role.r - 6} textAnchor="middle"
                  fontSize={10} fill={PALETTE.ink} fontWeight={600}>
                  {n.id.length > 14 ? n.id.slice(0, 14) + "…" : n.id}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      {/* Legend */}
      <div style={{ display: "flex", gap: 16, marginTop: 10, flexWrap: "wrap" }}>
        {Object.entries(ROLES).map(([key, val]) => (
          <div key={key} style={{ display: "flex", alignItems: "center", gap: 5,
            fontSize: 11, color: PALETTE.muted }}>
            <div style={{ width: val.r * 1.5, height: val.r * 1.5,
              borderRadius: "50%", background: val.color }} />
            {val.label}
          </div>
        ))}
      </div>
    </div>
  );
}
