"use client";

import { useSatelliteStore } from "@/stores/satelliteStore";

export default function StatusBar() {
  const { satellites, selectedSatellite, isPlaying, playbackSpeed, error, viewMode } =
    useSatelliteStore();

  return (
    <div
      className="flex items-center justify-between px-4 shrink-0"
      style={{
        height: "28px",
        background: "var(--bg-secondary)",
        borderTop: "1px solid var(--border-default)",
      }}
    >
      <div className="flex items-center gap-4">
        <span style={{ color: "var(--text-muted)", fontSize: "9px", letterSpacing: "0.12em" }}>
          SENTINEL COLLISION DETECTION SYSTEM
        </span>

        {error && (
          <span style={{ color: "var(--accent-red)", fontSize: "9px" }}>
            ⚠ {error}
          </span>
        )}
      </div>

      <div className="flex items-center gap-4">
        {selectedSatellite && (
          <span style={{ color: "var(--accent-cyan)", fontSize: "9px", letterSpacing: "0.1em" }}>
            TRACKING: {selectedSatellite.name.toUpperCase()}
          </span>
        )}

        <span style={{ color: "var(--text-muted)", fontSize: "9px" }}>
          {satellites.length} OBJECTS
        </span>

        {viewMode === "global" && (
          <span
            style={{
              color: isPlaying ? "var(--accent-green)" : "var(--text-muted)",
              fontSize: "9px",
              letterSpacing: "0.1em",
            }}
          >
            {isPlaying ? `▶ ${playbackSpeed}×` : "⏸ PAUSED"}
          </span>
        )}

        <span style={{ color: "var(--text-muted)", fontSize: "9px" }}>
          TLE/SGP4
        </span>
      </div>
    </div>
  );
}
