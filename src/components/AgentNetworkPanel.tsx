"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useSatelliteStore } from "@/stores/satelliteStore";

type AgentStatus = "monitoring" | "analyzing" | "proposing" | "accepted";

const AGENT_META = [
  { name: "AGENT-ALPHA", satId: "SAT-A-001", color: "var(--accent-cyan)",   pair: "A↔B" },
  { name: "AGENT-BETA",  satId: "SAT-B-001", color: "var(--accent-yellow)", pair: "A↔C" },
  { name: "AGENT-GAMMA", satId: "SAT-C-001", color: "var(--accent-green)",  pair: "B↔C" },
];

const STATUS_COLOR: Record<AgentStatus, string> = {
  monitoring: "var(--text-muted)",
  analyzing:  "var(--accent-yellow)",
  proposing:  "var(--accent-red)",
  accepted:   "var(--accent-green)",
};
const STATUS_LABEL: Record<AgentStatus, string> = {
  monitoring: "MONITORING",
  analyzing:  "ANALYZING",
  proposing:  "PROPOSING",
  accepted:   "ACCEPTED",
};
const STATUS_HEX: Record<string, string> = {
  analyzing: "#eab308",
  proposing:  "#ef4444",
  accepted:   "#22c55e",
};

// Rotating detail lines per stage
const DETAILS: Record<AgentStatus, string[]> = {
  monitoring: [
    "Scanning orbital catalog…",
    "Nominal operations. No alerts.",
    "Monitoring TLE updates…",
    "Conjunction screening active.",
  ],
  analyzing: [
    "High severity. Pc above 1e-4 threshold.",
    "Computing covariance matrix intersection…",
    "Evaluating conjunction geometry and TCA.",
    "Cross-referencing catalog. Lead time: 8 h.",
  ],
  proposing: [
    "Maneuver proposal sent. Awaiting response.",
    "Cross-track burn offer transmitted.",
    "Negotiating ΔV magnitude with peer.",
    "Radial maneuver: est. miss ↑ 1250 m.",
  ],
  accepted: [
    "Agreement reached. ΔV burn scheduled.",
    "Collision risk eliminated. Monitoring.",
    "Maneuver confirmed by peer satellite.",
    "Conjunction resolved. Resuming scan.",
  ],
};

interface AgentCard {
  status: AgentStatus;
  pc: number;
  missDistance: number;
  deltaV: number | null;
  detail: string;
}

const INITIAL_CARD: AgentCard = {
  status: "monitoring",
  pc: 0,
  missDistance: 0,
  deltaV: null,
  detail: DETAILS.monitoring[0],
};

// Per-agent scenario values
const SCENARIO = [
  { pc: 0.0018, miss: 180, missAfter: 1250, dv: 0.15 },
  { pc: 0.0012, miss: 220, missAfter: 1500, dv: 0.12 },
  { pc: 0.0015, miss: 195, missAfter: 1250, dv: 0.15 },
];

function pickRandomSatIds(n: number): string[] {
  const { satellites } = useSatelliteStore.getState();
  if (satellites.length < n) return satellites.map((s) => s.id).slice(0, n);
  const shuffled = [...satellites].sort(() => Math.random() - 0.5);
  return shuffled.slice(0, n).map((s) => s.id);
}

function randBetween(lo: number, hi: number) {
  return lo + Math.random() * (hi - lo);
}

function randDetail(status: AgentStatus) {
  const arr = DETAILS[status];
  return arr[Math.floor(Math.random() * arr.length)];
}

export default function AgentNetworkPanel() {
  const [cards, setCards] = useState<AgentCard[]>([
    { ...INITIAL_CARD },
    { ...INITIAL_CARD, detail: DETAILS.monitoring[1] },
    { ...INITIAL_CARD, detail: DETAILS.monitoring[2] },
  ]);
  const [blink, setBlink] = useState(true);
  const { setHighlightedSatellites } = useSatelliteStore();

  // Mutable highlights map — updated frequently by async loops, pushed to store on interval
  const highlightsRef = useRef<Record<string, string>>({});

  // Push ref to store every 120ms (decoupled from loop logic)
  useEffect(() => {
    const t = setInterval(() => {
      setHighlightedSatellites({ ...highlightsRef.current });
    }, 120);
    return () => clearInterval(t);
  }, [setHighlightedSatellites]);

  const updateCard = useCallback((i: number, patch: Partial<AgentCard>) => {
    setCards((prev) => prev.map((c, idx) => (idx === i ? { ...c, ...patch } : c)));
  }, []);

  // Independent async cycle for each agent
  useEffect(() => {
    const delay = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
    let cancelled = false;

    const runAgent = async (i: number, startOffset: number) => {
      await delay(startOffset);

      while (!cancelled) {
        const sc = SCENARIO[i];
        const satCount = 4 + Math.floor(Math.random() * 3); // 4–6 sats per cycle
        const sats = pickRandomSatIds(satCount);

        // ── ANALYZING ────────────────────────────────────────────────
        updateCard(i, {
          status: "analyzing",
          pc: sc.pc,
          missDistance: sc.miss,
          deltaV: null,
          detail: randDetail("analyzing"),
        });
        for (const id of sats) {
          if (cancelled) return;
          highlightsRef.current[id] = STATUS_HEX.analyzing;
          await delay(randBetween(120, 400));
        }
        if (cancelled) return;
        await delay(randBetween(2000, 3500));

        // ── PROPOSING ─────────────────────────────────────────────────
        updateCard(i, {
          status: "proposing",
          deltaV: sc.dv,
          detail: randDetail("proposing"),
        });
        for (const id of sats) {
          if (cancelled) return;
          highlightsRef.current[id] = STATUS_HEX.proposing;
          await delay(randBetween(180, 500));
        }
        if (cancelled) return;
        await delay(randBetween(2000, 4000));

        // ── ACCEPTED ──────────────────────────────────────────────────
        updateCard(i, {
          status: "accepted",
          missDistance: sc.missAfter,
          detail: randDetail("accepted"),
        });
        for (const id of sats) {
          if (cancelled) return;
          highlightsRef.current[id] = STATUS_HEX.accepted;
          await delay(randBetween(100, 300));
        }
        if (cancelled) return;
        await delay(randBetween(1500, 2500));

        // ── FADE OUT — clear highlights one by one ────────────────────
        for (const id of sats) {
          if (cancelled) return;
          delete highlightsRef.current[id];
          await delay(randBetween(80, 250));
        }

        // ── MONITORING ────────────────────────────────────────────────
        updateCard(i, {
          status: "monitoring",
          pc: 0,
          missDistance: 0,
          deltaV: null,
          detail: randDetail("monitoring"),
        });
        await delay(randBetween(1500, 4000));
      }
    };

    // Stagger agent start times so they're never in lock-step
    runAgent(0, 0);
    runAgent(1, randBetween(1800, 3200));
    runAgent(2, randBetween(3500, 6000));

    return () => {
      cancelled = true;
      highlightsRef.current = {};
      setHighlightedSatellites({});
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const t = setInterval(() => setBlink((b) => !b), 800);
    return () => clearInterval(t);
  }, []);

  const activeCount = cards.filter((c) => c.status !== "monitoring").length;

  return (
    <div className="flex flex-col h-full" style={{ background: "var(--bg-secondary)" }}>
      {/* Header */}
      <div
        className="flex items-center gap-2 px-4 shrink-0"
        style={{ height: "40px", borderBottom: "1px solid var(--border-default)" }}
      >
        <div
          className="w-1.5 h-1.5 rounded-full"
          style={{
            background: "var(--accent-green)",
            opacity: blink ? 1 : 0.3,
            transition: "opacity 0.4s",
          }}
        />
        <span style={{ color: "var(--text-tertiary)", fontSize: "9px", letterSpacing: "0.15em" }}>
          AGENT NETWORK
        </span>
        <div
          className="ml-auto px-2 py-0.5"
          style={{
            fontSize: "8px",
            letterSpacing: "0.1em",
            color: activeCount > 0 ? "var(--accent-yellow)" : "var(--accent-green)",
            border: `1px solid ${activeCount > 0 ? "var(--accent-yellow)" : "var(--accent-green)"}`,
            background: activeCount > 0 ? "rgba(234,179,8,0.08)" : "rgba(34,197,94,0.08)",
          }}
        >
          {activeCount > 0 ? `${activeCount} ACTIVE` : "NOMINAL"}
        </div>
      </div>

      {/* Agent cards */}
      <div className="flex-1 overflow-y-auto px-3 py-3 flex flex-col gap-3" style={{ scrollbarWidth: "thin" }}>
        {AGENT_META.map((agent, i) => {
          const card = cards[i];
          const statusColor = STATUS_COLOR[card.status];
          const isActive = card.status !== "monitoring";

          return (
            <div
              key={agent.name}
              className="p-3"
              style={{
                border: `1px solid ${isActive ? statusColor + "55" : "var(--border-subtle)"}`,
                background: isActive ? `${statusColor}0a` : "var(--bg-tertiary)",
                transition: "border-color 0.8s ease, background 0.8s ease",
              }}
            >
              {/* Name + status badge */}
              <div className="flex items-center gap-2 mb-1.5">
                <div className="w-1.5 h-1.5 rounded-full" style={{ background: agent.color, flexShrink: 0 }} />
                <span style={{ color: agent.color, fontSize: "9px", letterSpacing: "0.12em", flex: 1 }}>
                  {agent.name}
                </span>
                <span
                  className="px-1.5 py-0.5"
                  style={{
                    fontSize: "7px",
                    letterSpacing: "0.1em",
                    color: statusColor,
                    border: `1px solid ${statusColor}66`,
                    background: `${statusColor}11`,
                    transition: "all 0.8s ease",
                  }}
                >
                  {STATUS_LABEL[card.status]}
                </span>
              </div>

              {/* Sat ID + pair */}
              <div className="flex items-center gap-2 mb-2">
                <span style={{ color: "var(--text-muted)", fontSize: "8px" }}>{agent.satId}</span>
                <span style={{ color: "var(--accent-cyan)", fontSize: "8px", letterSpacing: "0.08em" }}>
                  {agent.pair}
                </span>
              </div>

              {/* Metrics */}
              {isActive && card.pc > 0 && (
                <div className="flex gap-4 mb-2">
                  <div>
                    <div style={{ color: "var(--text-muted)", fontSize: "7px", letterSpacing: "0.1em", marginBottom: "1px" }}>Pc</div>
                    <div style={{ color: "var(--accent-yellow)", fontSize: "9px" }}>{card.pc}</div>
                  </div>
                  <div>
                    <div style={{ color: "var(--text-muted)", fontSize: "7px", letterSpacing: "0.1em", marginBottom: "1px" }}>MISS</div>
                    <div style={{
                      color: card.status === "accepted" ? "var(--accent-green)" : "var(--accent-yellow)",
                      fontSize: "9px",
                      transition: "color 0.6s ease",
                    }}>
                      {card.missDistance} m
                    </div>
                  </div>
                  {card.deltaV !== null && (
                    <div>
                      <div style={{ color: "var(--text-muted)", fontSize: "7px", letterSpacing: "0.1em", marginBottom: "1px" }}>ΔV</div>
                      <div style={{ color: "var(--text-secondary)", fontSize: "9px" }}>{card.deltaV} m/s</div>
                    </div>
                  )}
                </div>
              )}

              {/* Detail */}
              <div style={{ color: "var(--text-muted)", fontSize: "8px", lineHeight: "1.55" }}>
                {card.detail}
              </div>
            </div>
          );
        })}

        {/* Network footer */}
        <div className="p-2 mt-auto" style={{ border: "1px solid var(--border-subtle)", background: "var(--bg-primary)" }}>
          <div style={{ color: "var(--text-muted)", fontSize: "7px", letterSpacing: "0.12em", marginBottom: "6px" }}>
            NETWORK STATUS
          </div>
          <div className="flex gap-5">
            <div>
              <div style={{ color: "var(--text-muted)", fontSize: "7px" }}>AGENTS</div>
              <div style={{ color: "var(--text-secondary)", fontSize: "9px" }}>3 / 3</div>
            </div>
            <div>
              <div style={{ color: "var(--text-muted)", fontSize: "7px" }}>PAIRS</div>
              <div style={{ color: "var(--text-secondary)", fontSize: "9px" }}>3</div>
            </div>
            <div>
              <div style={{ color: "var(--text-muted)", fontSize: "7px" }}>SCENARIO</div>
              <div style={{ color: "var(--accent-cyan)", fontSize: "9px" }}>THREE_WAY</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
