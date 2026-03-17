import { SatelliteData } from "@/stores/satelliteStore";

export async function fetchActiveSatellites(): Promise<SatelliteData[]> {
  try {
    const response = await fetch("/api/tle", {
      signal: AbortSignal.timeout(10000),
    });
    if (response.ok) {
      const text = await response.text();
      const parsed = parseTLEText(text);
      if (parsed.length > 0) return parsed;
    }
  } catch (e) {
    console.error("TLE fetch failed:", e);
  }
  return [];
}

export function parseTLEText(text: string): SatelliteData[] {
  const lines = text
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.length > 0);

  const satellites: SatelliteData[] = [];

  for (let i = 0; i < lines.length - 2; i++) {
    const name = lines[i];
    const tle1 = lines[i + 1];
    const tle2 = lines[i + 2];

    if (
      tle1.startsWith("1 ") &&
      tle2.startsWith("2 ") &&
      tle1.length >= 69 &&
      tle2.length >= 69
    ) {
      const noradId = tle1.substring(2, 7).trim();
      satellites.push({
        id: noradId,
        name: name.replace(/^\d+\s*/, "").trim() || `SAT-${noradId}`,
        tle1,
        tle2,
      });
      i += 2;
    }
  }

  return satellites;
}
