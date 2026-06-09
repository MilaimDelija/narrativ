"use client";

import { useEffect, useState } from "react";
import TransparencyDashboard from "../components/transparency_dashboard";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_URL}/demo`)
      .then((r) => r.json())
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => {
        setError("API unreachable — showing embedded demo data");
        setLoading(false);
      });
  }, []);

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center",
      minHeight: "100vh", fontFamily: "Arial", color: "#1A3A5C", fontSize: 18 }}>
      Loading NARRATIV…
    </div>
  );

  return <TransparencyDashboard data={data ?? undefined} />;
}
