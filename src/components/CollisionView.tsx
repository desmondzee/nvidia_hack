"use client";

import { useEffect, useMemo } from "react";
import dynamic from "next/dynamic";
import { useSatelliteStore } from "@/stores/satelliteStore";
import AgentLogsPanel from "./AgentLogsPanel";

const SatelliteCloseupViewer = dynamic(() => import("./SatelliteCloseupViewer"), { ssr: false });

// Map satellite IDs (SAT-A-001) to accent colors
const SAT_COLORS: Record<string, string> = {
  "SAT-A-001": "#06b6d4", // cyan
  "SAT-B-001": "#f59e0b", // orange
  "SAT-C-001": "#22c55e", // green
  "SAT-D-001": "#ef4444", // red
  "SAT-E-001": "#8b5cf6", // purple
  "SAT-F-001": "#ec4899", // pink
};

// Map satellite IDs to variant (A or B for different 3D models)
const SAT_VARIANTS: Record<string, "A" | "B"> = {
  "SAT-A-001": "A",
  "SAT-B-001": "B",
  "SAT-C-001": "A",
  "SAT-D-001": "B",
  "SAT-E-001": "A",
  "SAT-F-001": "B",
};

export default function CollisionView() {
  const { satellites, activeCollisionPair } = useSatelliteStore();

  // Find satellites by ID or fall back to random selection
  const [satA, satB] = useMemo(() => {
    if (activeCollisionPair) {
      const [idA, idB] = activeCollisionPair;
      // Find matching satellites from the pool
      const foundA = satellites.find(s => {
        // Match by checking if the satellite index corresponds to the letter
        const letter = idA.split("-")[1]; // "A" from "SAT-A-001"
        return s.name.toUpperCase().includes(letter) || s.id.endsWith(letter);
      }) || satellites[0];
      const foundB = satellites.find(s => {
        const letter = idB.split("-")[1];
        return s.name.toUpperCase().includes(letter) || s.id.endsWith(letter);
      }) || satellites[Math.min(1, satellites.length - 1)];
      return [foundA, foundB] as const;
    }
    
    // Fallback: pick two different satellites
    if (satellites.length < 2) return [null, null] as const;
    return [satellites[0], satellites[Math.min(1, satellites.length - 1)]] as const;
  }, [satellites, activeCollisionPair]);

  // Get IDs, colors, and variants for the current pair
  const satAId = activeCollisionPair?.[0] || "SAT-A-001";
  const satBId = activeCollisionPair?.[1] || "SAT-B-001";
  const satAColor = SAT_COLORS[satAId] || "#06b6d4";
  const satBColor = SAT_COLORS[satBId] || "#f59e0b";
  const satAVariant = SAT_VARIANTS[satAId] || "A";
  const satBVariant = SAT_VARIANTS[satBId] || "B";

  if (!satA || !satB) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ background: "var(--bg-primary)", minHeight: 0 }}>
        <span style={{ color: "var(--text-muted)", fontSize: "10px", letterSpacing: "0.15em" }}>
          LOADING SATELLITE DATA…
        </span>
      </div>
    );
  }

  return (
    <div
      className="flex overflow-hidden"
      style={{ flex: 1, minHeight: 0 }}
    >
      {/* Agent logs */}
      <AgentLogsPanel satA={satA} satB={satB} />

      {/* Satellite A */}
      <div
        className="relative overflow-hidden"
        style={{ flex: 1, minWidth: 0, minHeight: 0, borderRight: "1px solid var(--border-default)" }}
      >
        <SatelliteCloseupViewer 
          satellite={satA} 
          label={satAId}
          accentColor={satAColor} 
          variant={satAVariant}
          satId={satAId}
        />
      </div>

      {/* Satellite B */}
      <div
        className="relative overflow-hidden"
        style={{ flex: 1, minWidth: 0, minHeight: 0 }}
      >
        <SatelliteCloseupViewer 
          satellite={satB} 
          label={satBId}
          accentColor={satBColor} 
          variant={satBVariant}
          satId={satBId}
        />
      </div>
    </div>
  );
}
