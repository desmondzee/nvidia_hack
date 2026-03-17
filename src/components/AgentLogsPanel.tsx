"use client";

import { useState, useEffect, useRef } from "react";
import { SatelliteData, useSatelliteStore } from "@/stores/satelliteStore";

interface LogEntry {
  id: number;
  time: string;
  agent: string;
  level: "info" | "warn" | "critical" | "success";
  message: string;
  details?: string;
}

interface Props {
  satA: SatelliteData | null;
  satB: SatelliteData | null;
}

interface SimulationEvent {
  type: string;
  pair_label?: string;
  timestamp: string;
  data: {
    scenario?: string;
    pair?: string;
    stage?: string;
    output?: {
      severity_assessment?: string;
      who_should_maneuver?: string;
      sharing_strategy?: string;
      recommended_proposal_type?: string;
      shared_data?: {
        alert_id?: string;
        time_of_closest_approach?: string;
        miss_distance_m?: number;
        probability_of_collision?: number;
        threat_level?: string;
        our_object_id?: string;
        our_planned_position?: { x: number; y: number; z: number };
        relative_velocity_magnitude?: number;
      };
      proposal_type?: string;
      proposed_maneuver?: {
        delta_v?: { x: number; y: number; z: number };
        burn_start_time?: string;
        burn_duration_seconds?: number;
        expected_miss_distance_after_m?: number;
        fuel_cost_estimate?: number;
      };
      reasoning?: string;
      accept?: boolean;
      counter_maneuver?: unknown;
      agreed?: boolean;
      our_maneuver?: unknown;
      peer_maneuver?: unknown;
      summary?: string;
    };
    // negotiation_message fields
    message_id?: string;
    session_id?: string;
    round_number?: number;
    phase?: string;
    sender_satellite_id?: string;
    receiver_satellite_id?: string;
    collision_data?: {
      alert_id?: string;
      time_of_closest_approach?: string;
      miss_distance_m?: number;
      probability_of_collision?: number;
      threat_level?: string;
    };
    proposal_type?: string;
    proposed_maneuver?: unknown;
    reasoning?: string;
    accepted?: boolean;
    counter_proposal?: unknown;
    // decision fields
    alert_id?: string;
    our_satellite_id?: string;
    peer_satellite_id?: string;
    our_maneuver?: unknown;
    peer_maneuver?: unknown;
    negotiation_summary?: string;
    rounds_taken?: number;
    decided_at?: string;
    agreed?: boolean;
  };
}

let logIdCounter = 0;

const LEVEL_COLOR: Record<LogEntry["level"], string> = {
  info: "var(--text-secondary)",
  warn: "var(--accent-yellow)",
  critical: "var(--accent-red)",
  success: "var(--accent-green)",
};

const LEVEL_TAG: Record<LogEntry["level"], string> = {
  info: "INFO",
  warn: "WARN",
  critical: "CRIT",
  success: "OK",
};

export default function AgentLogsPanel({ satA, satB }: Props) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<SimulationEvent | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const retryTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const { setHighlightedSatellites, setActiveCollisionPair } = useSatelliteStore();

  // Connect to SSE endpoint
  useEffect(() => {
    const connect = () => {
      // Close existing connection
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }

      // Use local proxy to avoid CORS issues
      const endpoint = "/api/simulation/stream";
      console.log("[AgentLogsPanel] Connecting to SSE endpoint (attempt", retryCount + 1 + "):", endpoint);
      
      try {
        const es = new EventSource(endpoint);
        eventSourceRef.current = es;

        es.onopen = () => {
          console.log("[AgentLogsPanel] SSE connected");
          setIsConnected(true);
          setRetryCount(0);
        };

        es.onmessage = (event) => {
          try {
            console.log("[AgentLogsPanel] SSE message received:", event.data.substring(0, 200));
            const data: SimulationEvent = JSON.parse(event.data);
            console.log("[AgentLogsPanel] Parsed event type:", data.type);
            setLastEvent(data);
        
        const timestamp = new Date(data.timestamp);
        const timeStr = timestamp.toISOString().substring(11, 19) + " UTC";
        
        let newLog: LogEntry | null = null;

        switch (data.type) {
          case "simulation_start":
            newLog = {
              id: logIdCounter++,
              time: timeStr,
              agent: "SYSTEM",
              level: "info",
              message: `Simulation started: ${data.data.scenario || "three_way"}`,
            };
            break;

          case "llm_output":
            if (data.data.stage === "analyze") {
              const output = data.data.output;
              newLog = {
                id: logIdCounter++,
                time: timeStr,
                agent: data.pair_label || "AGENT",
                level: "warn",
                message: `Analysis complete`,
                details: output?.severity_assessment?.substring(0, 100) + "...",
              };
            } else if (data.data.stage === "proposal") {
              const output = data.data.output;
              const shared = output?.shared_data;
              newLog = {
                id: logIdCounter++,
                time: timeStr,
                agent: data.pair_label || "AGENT",
                level: "critical",
                message: `Maneuver proposal: ${output?.proposal_type}`,
                details: `Miss: ${shared?.miss_distance_m}m | Pc: ${shared?.probability_of_collision} | ${output?.reasoning?.substring(0, 80)}...`,
              };
            } else if (data.data.stage === "evaluate_proposal") {
              const output = data.data.output;
              newLog = {
                id: logIdCounter++,
                time: timeStr,
                agent: data.pair_label || "AGENT",
                level: output?.accept ? "success" : "warn",
                message: output?.accept ? "Proposal ACCEPTED" : "Proposal REJECTED",
                details: output?.reasoning?.substring(0, 100) + "...",
              };
            } else if (data.data.stage === "decision") {
              const output = data.data.output;
              newLog = {
                id: logIdCounter++,
                time: timeStr,
                agent: data.pair_label || "AGENT",
                level: output?.agreed ? "success" : "critical",
                message: output?.agreed ? "Agreement reached" : "No agreement",
                details: output?.summary?.substring(0, 100) + "...",
              };
            }
            break;

          case "negotiation_message":
            const msg = data.data;
            newLog = {
              id: logIdCounter++,
              time: timeStr,
              agent: `${msg.sender_satellite_id} → ${msg.receiver_satellite_id}`,
              level: msg.accepted ? "success" : "info",
              message: `${msg.phase?.toUpperCase()}: ${msg.proposal_type || "message"}`,
              details: msg.reasoning?.substring(0, 100) + "...",
            };
            break;

          case "decision":
            const decision = data.data;
            newLog = {
              id: logIdCounter++,
              time: timeStr,
              agent: decision.our_satellite_id || "SYSTEM",
              level: decision.agreed ? "success" : "critical",
              message: decision.agreed ? "Maneuver confirmed" : "Negotiation failed",
              details: decision.negotiation_summary?.substring(0, 100) + "...",
            };
            break;

          case "simulation_end":
            newLog = {
              id: logIdCounter++,
              time: timeStr,
              agent: "SYSTEM",
              level: "info",
              message: "Simulation ended",
            };
            break;
        }

        if (newLog) {
          setLogs((prev) => [...prev.slice(-50), newLog!]);
        }

        // Extract satellite IDs from events and update active pair
        let satA: string | null = null;
        let satB: string | null = null;
        
        // Try to get satellite IDs from various event types
        if (data.data?.our_satellite_id && data.data?.peer_satellite_id) {
          satA = data.data.our_satellite_id;
          satB = data.data.peer_satellite_id;
        } else if (data.data?.sender_satellite_id && data.data?.receiver_satellite_id) {
          satA = data.data.sender_satellite_id;
          satB = data.data.receiver_satellite_id;
        } else if (data.data?.output?.shared_data?.our_object_id) {
          // Extract from shared_data, derive other sat from pair_label
          satA = data.data.output.shared_data.our_object_id;
          const pair = data.pair_label; // e.g., "A↔B"
          if (pair) {
            const parts = pair.split(/[↔]/);
            if (parts.length === 2) {
              satB = `SAT-${parts[1].trim()}-001`;
            }
          }
        } else if (data.data?.pair) {
          // From simulation_start events
          const pair = data.data.pair; // e.g., "A↔B"
          const parts = pair.split(/[↔]/);
          if (parts.length === 2) {
            satA = `SAT-${parts[0].trim()}-001`;
            satB = `SAT-${parts[1].trim()}-001`;
          }
        }
        
        // Update active collision pair if we found valid satellites
        if (satA && satB) {
          setActiveCollisionPair([satA, satB]);
        }
        
        // Update satellite status colors based on events
        const highlights: Record<string, string> = {};
        
        if (data.type === "llm_output" && data.data.stage === "analyze") {
          // Warning state during analysis
          if (satA) highlights[satA] = "#f59e0b"; // yellow warning
          if (satB) highlights[satB] = "#f59e0b";
        } else if (data.type === "llm_output" && data.data.stage === "proposal") {
          // Critical state during proposal
          if (satA) highlights[satA] = "#ef4444"; // red critical
          if (satB) highlights[satB] = "#ef4444";
        } else if (data.type === "decision") {
          // Green for agreement, red for failure
          const agreed = data.data.agreed;
          const color = agreed ? "#22c55e" : "#ef4444"; // green or red
          if (satA) highlights[satA] = color;
          if (satB) highlights[satB] = color;
        }
        
        if (Object.keys(highlights).length > 0) {
          setHighlightedSatellites(highlights);
        }
      } catch (e) {
        console.error("[AgentLogsPanel] Failed to parse event:", e);
      }
    };

        es.onerror = (err) => {
          console.error("[AgentLogsPanel] SSE error:", err);
          console.error("[AgentLogsPanel] SSE readyState:", es.readyState);
          setIsConnected(false);
          es.close();
          
          // Add log entry for connection error
          const timeStr = new Date().toISOString().substring(11, 19) + " UTC";
          const errorMsg = es.readyState === 2 
            ? "Backend unreachable (10.1.96.155:8001) - is the server running?"
            : "Connection failed";
          
          setLogs((prev) => {
            // Don't add duplicate error messages
            if (prev.length > 0 && prev[prev.length - 1].message.includes("Backend unreachable")) {
              return prev;
            }
            return [...prev.slice(-50), {
              id: logIdCounter++,
              time: timeStr,
              agent: "SYSTEM",
              level: "critical",
              message: errorMsg,
            }];
          });
          
          // Retry with exponential backoff
          if (retryCount < 5) {
            const delay = Math.min(1000 * Math.pow(2, retryCount), 10000);
            console.log(`[AgentLogsPanel] Retrying in ${delay}ms...`);
            retryTimeoutRef.current = setTimeout(() => {
              setRetryCount((c) => c + 1);
            }, delay);
          }
        };
      } catch (e) {
        console.error("[AgentLogsPanel] Failed to create EventSource:", e);
        setIsConnected(false);
      }
    };

    connect();

    return () => {
      console.log("[AgentLogsPanel] Closing SSE connection");
      if (retryTimeoutRef.current) clearTimeout(retryTimeoutRef.current);
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
    };
  }, [retryCount]);

  // Auto-scroll to bottom
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  // Get conjunction data from last event if available
  const conjunctionData = lastEvent?.data?.output?.shared_data || lastEvent?.data?.collision_data;

  return (
    <div
      className="flex flex-col h-full"
      style={{
        width: "340px",
        flexShrink: 0,
        background: "var(--bg-secondary)",
        borderRight: "1px solid var(--border-default)",
      }}
    >
      {/* Header */}
      <div
        className="flex items-center gap-2 px-3 shrink-0"
        style={{ height: "40px", borderBottom: "1px solid var(--border-default)" }}
      >
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
          <circle cx="5" cy="5" r="4" stroke={isConnected ? "var(--accent-green)" : "var(--accent-red)"} strokeWidth="1" />
          <circle cx="5" cy="5" r="1.5" fill={isConnected ? "var(--accent-green)" : "var(--accent-red)"} />
        </svg>
        <span style={{ color: "var(--text-tertiary)", fontSize: "9px", letterSpacing: "0.15em" }}>
          AGENT NETWORK LOG
        </span>
        {!isConnected && (
          <button
            onClick={() => setRetryCount((c) => c + 1)}
            className="ml-2 px-2 py-0.5"
            style={{
              fontSize: "8px",
              letterSpacing: "0.1em",
              color: "var(--accent-cyan)",
              border: "1px solid var(--accent-cyan)",
              background: "rgba(6,182,212,0.1)",
              cursor: "pointer",
            }}
          >
            RECONNECT
          </button>
        )}
        <div
          className="ml-auto px-1.5 py-0.5"
          style={{
            fontSize: "8px",
            letterSpacing: "0.1em",
            color: isConnected ? "var(--accent-green)" : "var(--accent-red)",
            border: `1px solid ${isConnected ? "var(--accent-green)" : "var(--accent-red)"}`,
            background: isConnected ? "rgba(34,197,94,0.1)" : "rgba(239,68,68,0.1)",
          }}
        >
          {isConnected ? "LIVE" : "OFFLINE"}
        </div>
      </div>

      {/* Conjunction summary */}
      {conjunctionData && (
        <div
          className="mx-3 my-2 p-2 shrink-0"
          style={{
            border: "1px solid rgba(239,68,68,0.3)",
            background: "rgba(239,68,68,0.06)",
            borderLeft: "2px solid var(--accent-red)",
          }}
        >
          <div style={{ color: "var(--accent-red)", fontSize: "9px", letterSpacing: "0.12em", marginBottom: "4px" }}>
            CONJUNCTION EVENT
          </div>
          {(conjunctionData as { alert_id?: string }).alert_id && (
            <div style={{ color: "var(--text-muted)", fontSize: "8px", marginBottom: "4px" }}>
              Alert: {(conjunctionData as { alert_id?: string }).alert_id}
            </div>
          )}
          {(conjunctionData as { miss_distance_m?: number }).miss_distance_m !== undefined && (
            <div style={{ color: "var(--text-tertiary)", fontSize: "9px", marginBottom: "2px" }}>
              ↕ miss distance: <span style={{ color: "var(--accent-yellow)" }}>
                {(conjunctionData as { miss_distance_m?: number }).miss_distance_m}m
              </span>
            </div>
          )}
          {(conjunctionData as { probability_of_collision?: number }).probability_of_collision !== undefined && (
            <div style={{ color: "var(--text-tertiary)", fontSize: "9px", marginBottom: "2px" }}>
              Pc: <span style={{ color: "var(--accent-yellow)" }}>
                {(conjunctionData as { probability_of_collision?: number }).probability_of_collision}
              </span>
            </div>
          )}
          {(conjunctionData as { time_of_closest_approach?: string }).time_of_closest_approach && (
            <div style={{ color: "var(--text-tertiary)", fontSize: "9px" }}>
              TCA: <span style={{ color: "var(--accent-yellow)" }}>
                {(conjunctionData as { time_of_closest_approach?: string }).time_of_closest_approach?.substring(11, 19)}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Log stream */}
      <div className="flex-1 overflow-y-auto px-3 py-2" style={{ scrollbarWidth: "thin" }}>
        {!isConnected && logs.length === 0 && (
          <div style={{ color: "var(--text-muted)", fontSize: "9px", textAlign: "center", padding: "20px 0" }}>
            <div>Waiting for simulation data...</div>
            <div style={{ marginTop: "8px", fontSize: "8px", opacity: 0.7 }}>
              Backend: 10.1.96.155:8001<br/>
              <span style={{ color: "var(--accent-red)" }}>Not connected - check if server is running</span>
            </div>
          </div>
        )}
        {logs.map((log) => (
          <div key={log.id} className="mb-3">
            <div className="flex items-center gap-1.5 mb-0.5">
              <span style={{ color: LEVEL_COLOR[log.level], fontSize: "8px", letterSpacing: "0.1em" }}>
                [{LEVEL_TAG[log.level]}]
              </span>
              <span style={{ color: "var(--text-muted)", fontSize: "8px" }}>{log.time}</span>
              <span
                style={{
                  color: "var(--accent-cyan)",
                  fontSize: "8px",
                  letterSpacing: "0.08em",
                  marginLeft: "auto",
                }}
              >
                {log.agent}
              </span>
            </div>
            <div style={{ color: LEVEL_COLOR[log.level], fontSize: "9px", lineHeight: "1.4", opacity: 0.95 }}>
              {log.message}
            </div>
            {log.details && (
              <div style={{ color: "var(--text-muted)", fontSize: "8px", lineHeight: "1.4", marginTop: "2px", paddingLeft: "8px", borderLeft: "1px solid var(--border-subtle)" }}>
                {log.details}
              </div>
            )}
          </div>
        ))}
        <div ref={logsEndRef} />
      </div>
    </div>
  );
}
