"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { useSatelliteStore, SatelliteData } from "@/stores/satelliteStore";
import { fetchActiveSatellites } from "@/lib/tle";
import AgentNetworkPanel from "./AgentNetworkPanel";

const GlobeViewer = dynamic(() => import("./GlobeViewer"), { ssr: false });

export default function DualGlobeViewer() {
  const { setSelectedSatellite, setSatellites, setLoading, setError } =
    useSatelliteStore();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const sats = await fetchActiveSatellites();
        setSatellites(sats);
      } catch (e) {
        setError("Failed to load satellite data");
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [setSatellites, setLoading, setError]);

  const handleSatelliteClick = (sat: SatelliteData) => {
    setSelectedSatellite(sat);
  };

  if (!mounted) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ background: "var(--bg-primary)" }}>
        <div style={{ color: "var(--text-tertiary)", fontSize: "11px", letterSpacing: "0.15em" }}>
          INITIALIZING...
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex overflow-hidden">
      {/* Globe View */}
      <div className="flex-1 relative" style={{ borderRight: "1px solid var(--border-default)" }}>
        <div
          className="absolute top-3 left-3 z-10 flex items-center gap-2"
          style={{
            background: "rgba(5,5,8,0.7)",
            border: "1px solid var(--border-subtle)",
            padding: "4px 8px",
            backdropFilter: "blur(4px)",
          }}
        >
          <div className="w-1 h-1 rounded-full" style={{ background: "var(--accent-blue)" }} />
          <span style={{ color: "var(--text-tertiary)", fontSize: "9px", letterSpacing: "0.15em" }}>
            GLOBAL VIEW
          </span>
        </div>
        <GlobeViewer onSatelliteClick={handleSatelliteClick} />
      </div>

      {/* Agent Network Panel */}
      <div style={{ width: "380px", flexShrink: 0 }}>
        <AgentNetworkPanel />
      </div>
    </div>
  );
}
