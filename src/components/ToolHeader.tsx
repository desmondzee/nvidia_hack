"use client";

import { useState, useEffect } from "react";
import { useSatelliteStore } from "@/stores/satelliteStore";


export default function ToolHeader() {
  const {
    currentTime,
    satellites,
    isLoading,
    viewMode,
    setViewMode,
  } = useSatelliteStore();

  // Avoid hydration mismatch — only render time after client mount
  const [mounted, setMounted] = useState(false);
  useEffect(() => { setMounted(true); }, []);

  const formatTime = (d: Date) => {
    return d.toISOString().replace("T", " ").substring(0, 19) + " UTC";
  };

  return (
    <header
      className="flex items-center justify-between px-4 shrink-0"
      style={{
        height: "56px",
        background: "var(--bg-secondary)",
        borderBottom: "1px solid var(--border-default)",
      }}
    >
      {/* Left: Identity + View Tabs */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <circle cx="9" cy="9" r="7" stroke="#06b6d4" strokeWidth="1.5" />
            <circle cx="9" cy="9" r="2" fill="#06b6d4" />
            <line x1="9" y1="2" x2="9" y2="0" stroke="#06b6d4" strokeWidth="1.5" />
            <line x1="14" y1="4" x2="16" y2="2" stroke="#06b6d4" strokeWidth="1.5" />
          </svg>
          <span
            className="font-mono tracking-widest uppercase"
            style={{ color: "var(--text-primary)", fontSize: "11px", letterSpacing: "0.15em" }}
          >
            SENTINEL
          </span>
          <span
            style={{
              color: "var(--accent-cyan)",
              fontSize: "9px",
              letterSpacing: "0.2em",
              opacity: 0.7,
            }}
          >
            v0.1.0
          </span>
        </div>

        <div
          className="h-4 w-px"
          style={{ background: "var(--border-default)" }}
        />

        <div className="flex items-center gap-2">
          <div
            className="w-1.5 h-1.5 rounded-full"
            style={{
              background: isLoading ? "var(--accent-yellow)" : "var(--accent-green)",
              boxShadow: isLoading
                ? "0 0 6px var(--accent-yellow)"
                : "0 0 6px var(--accent-green)",
            }}
          />
          <span style={{ color: "var(--text-tertiary)", fontSize: "10px" }}>
            {isLoading ? "LOADING TLE DATA..." : `${satellites.length} OBJECTS TRACKED`}
          </span>
        </div>

        <div className="h-4 w-px" style={{ background: "var(--border-default)" }} />

        {/* View mode tabs */}
        <div className="flex items-center gap-1">
          {(["global", "collision"] as const).map((mode) => {
            const isActive = viewMode === mode;
            const isCollision = mode === "collision";
            return (
              <button
                key={mode}
                onClick={() => setViewMode(mode)}
                className="flex items-center gap-1.5 px-3 py-1 transition-all"
                style={{
                  fontSize: "9px",
                  letterSpacing: "0.12em",
                  background: isActive
                    ? isCollision ? "rgba(239,68,68,0.15)" : "rgba(6,182,212,0.12)"
                    : "transparent",
                  color: isActive
                    ? isCollision ? "var(--accent-red)" : "var(--accent-cyan)"
                    : "var(--text-muted)",
                  border: "1px solid",
                  borderColor: isActive
                    ? isCollision ? "rgba(239,68,68,0.6)" : "rgba(6,182,212,0.5)"
                    : "var(--border-subtle)",
                  borderRadius: "2px",
                  cursor: "pointer",
                }}
              >
                {isCollision && (
                  <div
                    className="w-1 h-1 rounded-full"
                    style={{
                      background: isActive ? "var(--accent-red)" : "var(--text-muted)",
                      boxShadow: isActive ? "0 0 4px var(--accent-red)" : "none",
                    }}
                  />
                )}
                {mode === "global" ? "GLOBAL VIEW" : "COLLISION"}
              </button>
            );
          })}
        </div>
      </div>

      {/* Center: Time display */}
      <div className="flex items-center gap-4">
        <div className="text-center">
          <div
            style={{
              color: "var(--text-secondary)",
              fontSize: "9px",
              letterSpacing: "0.1em",
              marginBottom: "1px",
            }}
          >
            EPOCH
          </div>
          <div
            style={{
              color: "var(--accent-cyan)",
              fontSize: "11px",
              fontFamily: "SF Mono, Fira Code, monospace",
              letterSpacing: "0.05em",
            }}
          >
            {mounted ? formatTime(currentTime) : "—"}
          </div>
        </div>
      </div>

      {/* Right: LIVE indicator */}
      <div className="flex items-center gap-3">
        <div
          className="flex items-center gap-2 px-3 py-1.5"
          style={{
            fontSize: "10px",
            letterSpacing: "0.1em",
            color: "var(--accent-green)",
            border: "1px solid rgba(34, 197, 94, 0.4)",
            borderRadius: "2px",
            background: "rgba(34, 197, 94, 0.1)",
          }}
        >
          <span
            className="w-1.5 h-1.5 rounded-full animate-pulse"
            style={{
              background: "var(--accent-green)",
              boxShadow: "0 0 6px var(--accent-green)",
            }}
          />
          LIVE
        </div>
      </div>
    </header>
  );
}
