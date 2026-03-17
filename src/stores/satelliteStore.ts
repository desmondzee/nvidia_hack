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

interface SatelliteState {
  satellites: SatelliteData[];
  selectedSatellite: SatelliteData | null;
  isPlaying: boolean;
  playbackSpeed: number;
  currentTime: Date;
  isLoading: boolean;
  error: string | null;

  setSatellites: (sats: SatelliteData[]) => void;
  setSelectedSatellite: (sat: SatelliteData | null) => void;
  setIsPlaying: (playing: boolean) => void;
  setPlaybackSpeed: (speed: number) => void;
  setCurrentTime: (time: Date) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  togglePlay: () => void;
}

export const useSatelliteStore = create<SatelliteState>((set) => ({
  satellites: [],
  selectedSatellite: null,
  isPlaying: false,
  playbackSpeed: 60,
  currentTime: new Date(),
  isLoading: true,
  error: null,

  setSatellites: (sats) => set({ satellites: sats }),
  setSelectedSatellite: (sat) => set({ selectedSatellite: sat }),
  setIsPlaying: (playing) => set({ isPlaying: playing }),
  setPlaybackSpeed: (speed) => set({ playbackSpeed: speed }),
  setCurrentTime: (time) => set({ currentTime: time }),
  setLoading: (loading) => set({ isLoading: loading }),
  setError: (error) => set({ error }),
  togglePlay: () => set((state) => ({ isPlaying: !state.isPlaying })),
}));
