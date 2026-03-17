"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import {
  twoline2satrec,
  propagate,
  gstime,
  eciToGeodetic,
  degreesLong,
  degreesLat,
} from "satellite.js";
import { useSatelliteStore, SatelliteData } from "@/stores/satelliteStore";
import SatellitePanel from "./SatellitePanel";

interface GlobeViewerProps {
  onSatelliteClick?: (sat: SatelliteData) => void;
}

const CESIUM_CSS =
  "https://cesium.com/downloads/cesiumjs/releases/1.122/Build/Cesium/Widgets/widgets.css";
const CESIUM_JS =
  "https://cesium.com/downloads/cesiumjs/releases/1.122/Build/Cesium/Cesium.js";

let cesiumLoadPromise: Promise<void> | null = null;

async function loadCesium(): Promise<void> {
  if (cesiumLoadPromise) return cesiumLoadPromise;
  cesiumLoadPromise = (async () => {
    if (!document.querySelector(`link[href="${CESIUM_CSS}"]`)) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = CESIUM_CSS;
      document.head.appendChild(link);
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    if (!(window as any).Cesium) {
      await new Promise<void>((resolve, reject) => {
        const existing = document.querySelector(`script[src="${CESIUM_JS}"]`);
        if (existing) {
          const poll = setInterval(() => {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            if ((window as any).Cesium) { clearInterval(poll); resolve(); }
          }, 50);
          return;
        }
        const s = document.createElement("script");
        s.src = CESIUM_JS;
        s.onload = () => resolve();
        s.onerror = reject;
        document.head.appendChild(s);
      });
    }
  })();
  return cesiumLoadPromise;
}

function getSatellitePosition(
  satrec: ReturnType<typeof twoline2satrec>,
  time: Date
): { lon: number; lat: number; alt: number } | null {
  try {
    const posVel = propagate(satrec, time);
    if (!posVel || !posVel.position || typeof posVel.position === "boolean") return null;
    const gst = gstime(time);
    const geo = eciToGeodetic(posVel.position, gst);
    const lon = degreesLong(geo.longitude);
    const lat = degreesLat(geo.latitude);
    const alt = geo.height * 1000; // km → metres
    if (!isFinite(lon) || !isFinite(lat) || !isFinite(alt)) return null;
    return { lon, lat, alt: Math.max(0, alt) };
  } catch {
    return null;
  }
}

export default function GlobeViewer({ onSatelliteClick }: GlobeViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<unknown>(null);
  const animFrameRef = useRef<number>(0);
  const mountedRef = useRef(true);
  const satRecCacheRef = useRef<Map<string, ReturnType<typeof twoline2satrec>>>(new Map());
  const pointsCollectionRef = useRef<unknown>(null);
  // satId → PointPrimitive
  const pointMapRef = useRef<Map<string, unknown>>(new Map());
  const trailEntitiesRef = useRef<Map<string, unknown>>(new Map());
  const cameraLonRef = useRef<number>(0);
  const simTimeRef = useRef<Date | null>(null);
  const lastStateUpdateRef = useRef<number>(0);

  // Signals to React effects that Cesium is ready
  const [cesiumReady, setCesiumReady] = useState(false);

  const { satellites, setCurrentTime, setSelectedSatellite } = useSatelliteStore();

  const getSatRec = useCallback((sat: SatelliteData) => {
    if (!satRecCacheRef.current.has(sat.id)) {
      try {
        const satrec = twoline2satrec(sat.tle1, sat.tle2);
        satRecCacheRef.current.set(sat.id, satrec);
      } catch {
        return null;
      }
    }
    return satRecCacheRef.current.get(sat.id) ?? null;
  }, []);

  // ── 1. Cesium viewer init ───────────────────────────────────────────────────
  useEffect(() => {
    // Use a LOCAL cancelled flag (not mountedRef) so that each effect invocation
    // independently tracks whether IT has been cleaned up. This prevents
    // React StrictMode's double-invoke from creating two simultaneous Cesium viewers.
    let cancelled = false;
    mountedRef.current = true;

    const init = async () => {
      try {
        await loadCesium();
        if (cancelled || !containerRef.current) return;

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const Cesium = (window as any).Cesium;

        // Suppress Ion 401 errors — we use NASA GIBS tiles, not Cesium Ion services
        Cesium.Ion.defaultAccessToken = "";

        const viewer = new Cesium.Viewer(containerRef.current, {
          imageryProvider: false,
          animation: false,
          baseLayerPicker: false,
          fullscreenButton: false,
          geocoder: false,
          homeButton: false,
          infoBox: false,
          navigationHelpButton: false,
          sceneModePicker: false,
          selectionIndicator: false,
          timeline: false,
          creditContainer: document.createElement("div"),
          shouldAnimate: false,
          targetFrameRate: 60,
          terrainProvider: new Cesium.EllipsoidTerrainProvider(),
        });

        viewer.imageryLayers.removeAll();
        try {
          viewer.imageryLayers.addImageryProvider(
            new Cesium.UrlTemplateImageryProvider({
              url: "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default//GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg",
              maximumLevel: 8,
            })
          );
        } catch { /**/ }

        viewer.scene.globe.enableLighting = true;
        viewer.scene.globe.lightingFadeOutDistance = 100000000;
        viewer.scene.globe.lightingFadeInDistance = 100000;
        viewer.scene.sun.show = true;
        viewer.scene.moon.show = false;
        viewer.scene.backgroundColor = Cesium.Color.fromCssColorString("#050508");
        viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#0a0a1a");
        viewer.scene.globe.showGroundAtmosphere = true;
        viewer.scene.globe.atmosphereLightIntensity = 20;

        cameraLonRef.current = 50;
        viewer.camera.setView({
          destination: Cesium.Cartesian3.fromDegrees(50, 10, 28000000),
        });

        const points = viewer.scene.primitives.add(new Cesium.PointPrimitiveCollection());
        pointsCollectionRef.current = points;

        // Click handler
        const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
        handler.setInputAction((click: { position: unknown }) => {
          const picked = viewer.scene.pick(click.position);
          if (Cesium.defined(picked) && picked.primitive) {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const satId = (picked.primitive as any)._satId;
            if (satId) {
              const sat = useSatelliteStore.getState().satellites.find((s) => s.id === satId);
              if (sat) { setSelectedSatellite(sat); onSatelliteClick?.(sat); }
            }
          }
        }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

        viewerRef.current = viewer;
        // Signal React that we're ready — triggers the satellite-rendering effect
        setCesiumReady(true);
      } catch (e) {
        console.error("[GlobeViewer] init error:", e);
      }
    };

    init();

    return () => {
      cancelled = true;
      mountedRef.current = false;
      cancelAnimationFrame(animFrameRef.current);
      setCesiumReady(false);
      if (viewerRef.current) {
        try { (viewerRef.current as { destroy(): void }).destroy(); } catch { /**/ }
        viewerRef.current = null;
        pointsCollectionRef.current = null;
      }
      pointMapRef.current.clear();
      trailEntitiesRef.current.clear();
      satRecCacheRef.current.clear();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── 2. Satellite dot rendering (runs whenever satellites or cesiumReady changes) ──
  // This effect owns adding/removing PointPrimitives.
  // The tick loop only updates their positions each frame.
  useEffect(() => {
    if (!cesiumReady || !pointsCollectionRef.current) return;

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const Cesium = (window as any).Cesium;
    if (!Cesium) return;

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const points = pointsCollectionRef.current as any;
    const colorNormal = Cesium.Color.fromBytes(150, 150, 150, 220);
    const colorSelected = Cesium.Color.fromBytes(255, 200, 0, 255);
    const { selectedSatellite } = useSatelliteStore.getState();

    const simTime = simTimeRef.current || new Date();
    const newIds = new Set(satellites.map((s) => s.id));

    // Remove points for satellites that left the list
    for (const [satId, pt] of Array.from(pointMapRef.current.entries())) {
      if (!newIds.has(satId)) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        points.remove(pt as any);
        pointMapRef.current.delete(satId);
      }
    }

    // Add new satellite dots
    let added = 0;
    for (const sat of satellites) {
      if (pointMapRef.current.has(sat.id)) continue;

      const satrec = getSatRec(sat);
      if (!satrec) continue;

      const pos = getSatellitePosition(satrec, simTime);
      if (!pos) continue;

      const isSelected = selectedSatellite?.id === sat.id;
      const pt = points.add({
        position: Cesium.Cartesian3.fromDegrees(pos.lon, pos.lat, pos.alt),
        color: isSelected ? colorSelected : colorNormal,
        pixelSize: isSelected ? 10 : 4,
      });
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (pt as any)._satId = sat.id;
      pointMapRef.current.set(sat.id, pt);
      added++;
    }

    console.log(`[GlobeViewer] Rendered ${added} new satellite dots, total: ${pointMapRef.current.size}`);
  }, [satellites, cesiumReady, getSatRec]);

  // ── 3. Animation tick — only updates positions & camera, no add/remove ──────
  useEffect(() => {
    let lastTime = performance.now();

    const tick = () => {
      if (!mountedRef.current) return;

      const now = performance.now();
      const delta = Math.min(now - lastTime, 100);
      lastTime = now;

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const viewer = viewerRef.current as any;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const Cesium = (window as any).Cesium;

      if (!viewer || !Cesium) {
        animFrameRef.current = requestAnimationFrame(tick);
        return;
      }

      try {
        if (viewer.isDestroyed()) {
          animFrameRef.current = requestAnimationFrame(tick);
          return;
        }
      } catch {
        animFrameRef.current = requestAnimationFrame(tick);
        return;
      }

      const { isPlaying, playbackSpeed, currentTime, satellites: sats, selectedSatellite, highlightedSatellites } =
        useSatelliteStore.getState();

      // Init simTime
      if (sats.length > 0 && !simTimeRef.current) {
        simTimeRef.current = new Date(currentTime.getTime());
      }
      if (!simTimeRef.current) {
        animFrameRef.current = requestAnimationFrame(tick);
        return;
      }

      let simTime = simTimeRef.current;
      if (isPlaying) {
        simTime = new Date(simTime.getTime() + delta * playbackSpeed);
        simTimeRef.current = simTime;
        if (now - lastStateUpdateRef.current > 500) {
          setCurrentTime(simTime);
          lastStateUpdateRef.current = now;
        }
      } else {
        simTime = new Date(currentTime.getTime());
        simTimeRef.current = simTime;
      }

      viewer.clock.currentTime = Cesium.JulianDate.fromDate(simTime);

      if (isPlaying) {
        cameraLonRef.current -= (15 / 3600000) * delta * playbackSpeed;
        viewer.camera.setView({
          destination: Cesium.Cartesian3.fromDegrees(cameraLonRef.current, 10, 28000000),
        });
      }

      // Update existing point positions
      const colorNormal = Cesium.Color.fromBytes(150, 150, 150, 220);
      const colorSelected = Cesium.Color.fromBytes(255, 200, 0, 255);

      for (const sat of sats) {
        const pt = pointMapRef.current.get(sat.id);
        if (!pt) continue;

        const satrec = getSatRec(sat);
        if (!satrec) continue;

        const pos = getSatellitePosition(satrec, simTime);
        if (!pos) continue;

        const isSelected = selectedSatellite?.id === sat.id;
        const highlightHex = highlightedSatellites[sat.id];
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const p = pt as any;
        p.position = Cesium.Cartesian3.fromDegrees(pos.lon, pos.lat, pos.alt);
        if (isSelected) {
          p.color = colorSelected;
          p.pixelSize = 10;
        } else if (highlightHex) {
          p.color = Cesium.Color.fromCssColorString(highlightHex);
          p.pixelSize = 6;
        } else {
          p.color = colorNormal;
          p.pixelSize = 4;
        }
      }

      // Cleanup trail entities
      for (const [satId, entity] of Array.from(trailEntitiesRef.current.entries())) {
        if (!sats.find((s) => s.id === satId) || selectedSatellite?.id !== satId) {
          viewer.entities.remove(entity);
          trailEntitiesRef.current.delete(satId);
        }
      }

      animFrameRef.current = requestAnimationFrame(tick);
    };

    animFrameRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animFrameRef.current);
  }, [setCurrentTime, getSatRec]);

  return (
    <div className="w-full h-full relative">
      <div ref={containerRef} className="w-full h-full" style={{ background: "#050508" }} />
      <SatellitePanel />
    </div>
  );
}
