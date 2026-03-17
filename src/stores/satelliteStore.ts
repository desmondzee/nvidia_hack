import { create } from "zustand";

export interface SatelliteData {
  id: string;
  name: string;
  tle1: string;
  tle2: string;
  position?: { x: number; y: number; z: number };
  lat?: number;
  lon?: number;
  alt?: number;
}

export type ViewMode = "global" | "collision";

interface SatelliteState {
  satellites: SatelliteData[];
  selectedSatellite: SatelliteData | null;
  isPlaying: boolean;
  playbackSpeed: number;
  currentTime: Date;
  isLoading: boolean;
  error: string | null;
  viewMode: ViewMode;
  highlightedSatellites: Record<string, string>; // satId → hex color
  activeCollisionPair: [string, string] | null; // [SAT-A-001, SAT-B-001] etc

  setSatellites: (sats: SatelliteData[]) => void;
  setSelectedSatellite: (sat: SatelliteData | null) => void;
  setIsPlaying: (playing: boolean) => void;
  setPlaybackSpeed: (speed: number) => void;
  setCurrentTime: (time: Date) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  togglePlay: () => void;
  setViewMode: (mode: ViewMode) => void;
  setHighlightedSatellites: (highlights: Record<string, string>) => void;
  setActiveCollisionPair: (pair: [string, string] | null) => void;
}

const getTodayMidnight = () => {
  const now = new Date();
  now.setUTCHours(0, 0, 0, 0);
  return now;
};

export const useSatelliteStore = create<SatelliteState>((set) => ({
  satellites: [],
  selectedSatellite: null,
  isPlaying: true,
  playbackSpeed: 5,
  currentTime: getTodayMidnight(),
  isLoading: true,
  error: null,
  viewMode: "global",
  highlightedSatellites: {},
  activeCollisionPair: null,

  setSatellites: (sats) => set({ satellites: sats }),
  setSelectedSatellite: (sat) => set({ selectedSatellite: sat }),
  setIsPlaying: (playing) => set({ isPlaying: playing }),
  setPlaybackSpeed: (speed) => set({ playbackSpeed: speed }),
  setCurrentTime: (time) => set({ currentTime: time }),
  setLoading: (loading) => set({ isLoading: loading }),
  setError: (error) => set({ error }),
  togglePlay: () => set((state) => ({ isPlaying: !state.isPlaying })),
  setViewMode: (mode) => set({ viewMode: mode }),
  setHighlightedSatellites: (highlights) => set({ highlightedSatellites: highlights }),
  setActiveCollisionPair: (pair) => set({ activeCollisionPair: pair }),
}));
