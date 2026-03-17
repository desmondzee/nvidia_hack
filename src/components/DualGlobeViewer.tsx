"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { useSatelliteStore, SatelliteData } from "@/stores/satelliteStore";
import { fetchActiveSatellites } from "@/lib/tle";

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
        <GlobeViewer mode="global" onSatelliteClick={handleSatelliteClick} />
      </div>

      {/* Agent Panel — placeholder */}
      <div
        className="flex flex-col"
        style={{
          width: "380px",
          flexShrink: 0,
          background: "var(--bg-secondary)",
        }}
      >
        {/* Panel header */}
        <div
          className="flex items-center gap-2 px-4 shrink-0"
          style={{
            height: "40px",
            borderBottom: "1px solid var(--border-default)",
          }}
        >
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <circle cx="6" cy="6" r="5" stroke="var(--text-muted)" strokeWidth="1" />
            <circle cx="6" cy="6" r="2" fill="var(--text-muted)" />
          </svg>
          <span style={{ color: "var(--text-tertiary)", fontSize: "9px", letterSpacing: "0.15em" }}>
            AGENT NETWORK
          </span>
          <div
            className="ml-auto px-2 py-0.5"
            style={{
              fontSize: "8px",
              letterSpacing: "0.1em",
              color: "var(--text-muted)",
              border: "1px solid var(--border-subtle)",
            }}
          >
            OFFLINE
          </div>
        </div>

        {/* Placeholder body */}
        <div className="flex-1 flex flex-col items-center justify-center gap-4 px-6">
          {/* Icon */}
          <div style={{ opacity: 0.15 }}>
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
              <circle cx="24" cy="24" r="20" stroke="var(--text-secondary)" strokeWidth="1.5" strokeDasharray="4 3" />
              <circle cx="24" cy="24" r="4" fill="var(--text-secondary)" />
              <line x1="24" y1="4" x2="24" y2="14" stroke="var(--text-secondary)" strokeWidth="1.5" />
              <line x1="24" y1="34" x2="24" y2="44" stroke="var(--text-secondary)" strokeWidth="1.5" />
              <line x1="4" y1="24" x2="14" y2="24" stroke="var(--text-secondary)" strokeWidth="1.5" />
              <line x1="34" y1="24" x2="44" y2="24" stroke="var(--text-secondary)" strokeWidth="1.5" />
            </svg>
          </div>

          <div className="text-center" style={{ maxWidth: "240px" }}>
            <div
              style={{
                color: "var(--text-tertiary)",
                fontSize: "10px",
                letterSpacing: "0.15em",
                marginBottom: "8px",
              }}
            >
              DECENTRALISED AGENTS
            </div>
            <div style={{ color: "var(--text-muted)", fontSize: "10px", lineHeight: "1.6" }}>
              Autonomous collision detection agents will coordinate here. Each agent monitors a satellite cluster and broadcasts risk assessments across the network.
            </div>
          </div>

          {/* Placeholder nodes */}
          <div className="flex flex-col gap-2 w-full" style={{ maxWidth: "280px" }}>
            {["AGENT-ALPHA", "AGENT-BETA", "AGENT-GAMMA"].map((name) => (
              <div
                key={name}
                className="flex items-center gap-3 px-3 py-2"
                style={{
                  border: "1px solid var(--border-subtle)",
                  background: "var(--bg-tertiary)",
                }}
              >
                <div
                  className="w-1.5 h-1.5 rounded-full"
                  style={{ background: "var(--text-muted)", flexShrink: 0 }}
                />
                <span style={{ color: "var(--text-muted)", fontSize: "9px", letterSpacing: "0.1em", flex: 1 }}>
                  {name}
                </span>
                <span style={{ color: "var(--text-muted)", fontSize: "9px" }}>—</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
