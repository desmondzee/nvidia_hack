"use client";

import { useState, useEffect } from "react";
import { useSatelliteStore } from "@/stores/satelliteStore";

const SPEED_OPTIONS = [
  { label: "1×", value: 1 },
  { label: "10×", value: 10 },
  { label: "60×", value: 60 },
  { label: "300×", value: 300 },
  { label: "1000×", value: 1000 },
];

export default function ToolHeader() {
  const {
    isPlaying,
    playbackSpeed,
    currentTime,
    satellites,
    isLoading,
    togglePlay,
    setPlaybackSpeed,
    setCurrentTime,
  } = useSatelliteStore();

  // Avoid hydration mismatch — only render time after client mount
  const [mounted, setMounted] = useState(false);
  useEffect(() => { setMounted(true); }, []);

  const formatTime = (d: Date) => {
    return d.toISOString().replace("T", " ").substring(0, 19) + " UTC";
  };

  const handleReset = () => {
    setCurrentTime(new Date());
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
      {/* Left: Identity */}
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

      {/* Right: Playback controls */}
      <div className="flex items-center gap-3">
        {/* Speed selector */}
        <div className="flex items-center gap-1">
          {SPEED_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setPlaybackSpeed(opt.value)}
              className="px-2 py-1 transition-colors"
              style={{
                fontSize: "10px",
                letterSpacing: "0.05em",
                background:
                  playbackSpeed === opt.value
                    ? "rgba(6, 182, 212, 0.15)"
                    : "transparent",
                color:
                  playbackSpeed === opt.value
                    ? "var(--accent-cyan)"
                    : "var(--text-tertiary)",
                border: "1px solid",
                borderColor:
                  playbackSpeed === opt.value
                    ? "var(--accent-cyan)"
                    : "var(--border-subtle)",
                borderRadius: "2px",
                cursor: "pointer",
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>

        <div
          className="h-4 w-px"
          style={{ background: "var(--border-default)" }}
        />

        {/* Reset button */}
        <button
          onClick={handleReset}
          className="flex items-center gap-1.5 px-3 py-1.5 transition-colors"
          style={{
            fontSize: "10px",
            letterSpacing: "0.08em",
            background: "transparent",
            color: "var(--text-tertiary)",
            border: "1px solid var(--border-subtle)",
            borderRadius: "2px",
            cursor: "pointer",
          }}
        >
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
            <path
              d="M5 1.5A3.5 3.5 0 1 0 8.5 5"
              stroke="currentColor"
              strokeWidth="1.2"
              strokeLinecap="round"
            />
            <path d="M8.5 1.5v3H5.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          NOW
        </button>

        {/* Play/Pause */}
        <button
          onClick={togglePlay}
          className="flex items-center gap-2 px-4 py-1.5 transition-all"
          style={{
            fontSize: "10px",
            letterSpacing: "0.1em",
            background: isPlaying
              ? "rgba(6, 182, 212, 0.2)"
              : "rgba(6, 182, 212, 0.1)",
            color: "var(--accent-cyan)",
            border: "1px solid",
            borderColor: isPlaying
              ? "rgba(6, 182, 212, 0.8)"
              : "rgba(6, 182, 212, 0.4)",
            borderRadius: "2px",
            cursor: "pointer",
            boxShadow: isPlaying ? "0 0 12px rgba(6, 182, 212, 0.3)" : "none",
          }}
        >
          {isPlaying ? (
            <>
              <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor">
                <rect x="1.5" y="1.5" width="2.5" height="7" />
                <rect x="6" y="1.5" width="2.5" height="7" />
              </svg>
              PAUSE
            </>
          ) : (
            <>
              <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor">
                <polygon points="1.5,1 9,5 1.5,9" />
              </svg>
              PLAY
            </>
          )}
        </button>
      </div>
    </header>
  );
}
