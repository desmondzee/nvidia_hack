"use client";

import { useSatelliteStore } from "@/stores/satelliteStore";

export default function SatellitePanel() {
  const { selectedSatellite, satellites, currentTime } = useSatelliteStore();

  const formatAlt = (alt?: number) => {
    if (alt === undefined) return "—";
    return `${(alt / 1000).toFixed(0)} km`;
  };

  if (!selectedSatellite) {
    return (
      <div
        className="absolute bottom-4 left-4 z-10"
        style={{
          background: "rgba(5, 5, 8, 0.85)",
          border: "1px solid var(--border-default)",
          backdropFilter: "blur(8px)",
          padding: "10px 12px",
          minWidth: "180px",
        }}
      >
        <div
          style={{
            color: "var(--text-tertiary)",
            fontSize: "9px",
            letterSpacing: "0.15em",
            marginBottom: "6px",
          }}
        >
          CLUSTER VIEW
        </div>
        <div style={{ color: "var(--text-muted)", fontSize: "10px" }}>
          Select a satellite to focus
        </div>
      </div>
    );
  }

  return (
    <div
      className="absolute bottom-4 left-4 z-10"
      style={{
        background: "rgba(5, 5, 8, 0.9)",
        border: "1px solid var(--border-default)",
        borderLeft: "2px solid var(--accent-cyan)",
        backdropFilter: "blur(8px)",
        padding: "10px 12px",
        minWidth: "220px",
      }}
    >
      <div
        style={{
          color: "var(--accent-cyan)",
          fontSize: "9px",
          letterSpacing: "0.15em",
          marginBottom: "8px",
          display: "flex",
          alignItems: "center",
          gap: "6px",
        }}
      >
        <div
          className="w-1.5 h-1.5 rounded-full"
          style={{ background: "var(--accent-cyan)", boxShadow: "0 0 4px var(--accent-cyan)" }}
        />
        SELECTED OBJECT
      </div>

      <div
        style={{
          color: "var(--text-primary)",
          fontSize: "11px",
          marginBottom: "8px",
          letterSpacing: "0.05em",
        }}
      >
        {selectedSatellite.name}
      </div>

      <div className="space-y-1">
        <div className="flex justify-between">
          <span style={{ color: "var(--text-tertiary)", fontSize: "9px" }}>NORAD ID</span>
          <span style={{ color: "var(--text-secondary)", fontSize: "9px", fontFamily: "monospace" }}>
            {selectedSatellite.id}
          </span>
        </div>
        <div className="flex justify-between">
          <span style={{ color: "var(--text-tertiary)", fontSize: "9px" }}>EPOCH</span>
          <span style={{ color: "var(--text-secondary)", fontSize: "9px", fontFamily: "monospace" }}>
            {currentTime.toISOString().substring(0, 10)}
          </span>
        </div>
      </div>

      <div
        style={{
          marginTop: "8px",
          paddingTop: "8px",
          borderTop: "1px solid var(--border-subtle)",
          color: "var(--text-muted)",
          fontSize: "9px",
          letterSpacing: "0.1em",
        }}
      >
        {satellites.length} OBJECTS IN CATALOG
      </div>
    </div>
  );
}
