"use client";

import { useEffect, useRef, useCallback } from "react";
import * as satellite from "satellite.js";
import { useSatelliteStore, SatelliteData } from "@/stores/satelliteStore";

interface GlobeViewerProps {
  mode: "global" | "cluster";
  onSatelliteClick?: (sat: SatelliteData) => void;
}

const CESIUM_CSS =
  "https://cesium.com/downloads/cesiumjs/releases/1.122/Build/Cesium/Widgets/widgets.css";
const CESIUM_JS =
  "https://cesium.com/downloads/cesiumjs/releases/1.122/Build/Cesium/Cesium.js";
const CESIUM_TOKEN =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiJlYWE1OWUxNy1mMWZiLTQzYjYtYTQ0OS1kMWFjYmFkNjc5YzciLCJpZCI6NTc3MzMsImlhdCI6MTYyMjY0NjI2MH0.XcKpgANiY19MC4bdFUXMVEBToBmqS8kuYpUlxJHYZxk";

// Shared Cesium load promise — prevents race between two viewer instances
let cesiumLoadPromise: Promise<void> | null = null;

async function loadCesium(): Promise<void> {
  if (cesiumLoadPromise) return cesiumLoadPromise;
  cesiumLoadPromise = (async () => {
    // CSS
    if (!document.querySelector(`link[href="${CESIUM_CSS}"]`)) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = CESIUM_CSS;
      document.head.appendChild(link);
    }
    // JS — only inject once, then poll until window.Cesium is defined
    if (!(window as unknown as Record<string, unknown>).Cesium) {
      await new Promise<void>((resolve, reject) => {
        const existing = document.querySelector(`script[src="${CESIUM_JS}"]`);
        if (existing) {
          // Another instance already injected it — just poll
          const poll = setInterval(() => {
            if ((window as unknown as Record<string, unknown>).Cesium) {
              clearInterval(poll);
              resolve();
            }
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

function propagateSat(sat: SatelliteData, time: Date): [number, number, number] | null {
  try {
    const satrec = satellite.twoline2satrec(sat.tle1, sat.tle2);
    if (satrec.error !== 0) return null;

    const posVel = satellite.propagate(satrec, time);
    if (!posVel) return null;
    const pos = posVel.position;
    if (!pos || typeof pos === "boolean") return null;

    const gmst = satellite.gstime(time);
    const geo = satellite.eciToGeodetic(pos, gmst);

    const lon = satellite.degreesLong(geo.longitude);
    const lat = satellite.degreesLat(geo.latitude);
    const alt = geo.height * 1000; // km → m

    if (!isFinite(lon) || !isFinite(lat) || !isFinite(alt) || alt < 0) return null;
    return [lon, lat, alt];
  } catch {
    return null;
  }
}

export default function GlobeViewer({ mode, onSatelliteClick }: GlobeViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<unknown>(null);
  const entitiesRef = useRef<Map<string, unknown>>(new Map());
  const animFrameRef = useRef<number>(0);
  const mountedRef = useRef(true);

  const { setSelectedSatellite, setCurrentTime } = useSatelliteStore();

  useEffect(() => {
    mountedRef.current = true;

    const init = async () => {
      await loadCesium();
      if (!mountedRef.current || !containerRef.current) return;

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const Cesium = (window as any).Cesium;
      Cesium.Ion.defaultAccessToken = CESIUM_TOKEN;

      const viewer = new Cesium.Viewer(containerRef.current, {
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
      });

      // NASA GIBS Blue Marble — reliable, free, no Ion token needed
      viewer.imageryLayers.removeAll();
      viewer.imageryLayers.addImageryProvider(
        new Cesium.UrlTemplateImageryProvider({
          url: "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default//GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg",
          maximumLevel: 8,
        })
      );

      viewer.scene.backgroundColor = Cesium.Color.fromCssColorString("#050508");
      viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#1a3a5c");
      viewer.scene.globe.enableLighting = true;
      viewer.scene.globe.lightingFadeOutDistance = 100000000;
      viewer.scene.globe.lightingFadeInDistance = 10000000;
      viewer.scene.globe.dynamicAtmosphereLighting = true;
      viewer.scene.globe.dynamicAtmosphereLightingFromSun = true;
      viewer.scene.globe.atmosphereLightIntensity = 20;
      viewer.scene.globe.showGroundAtmosphere = false;
      viewer.scene.fog.enabled = false;
      viewer.scene.sun.show = true;
      viewer.scene.moon.show = false;
      viewer.scene.skyAtmosphere.show = true;
      viewer.scene.skyBox.show = true;

      viewer.camera.setView({
        destination: Cesium.Cartesian3.fromDegrees(0, 20, 25000000),
      });

      // Click to select satellite
      const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
      handler.setInputAction((click: { position: unknown }) => {
        const picked = viewer.scene.pick(click.position);
        if (Cesium.defined(picked) && picked.id) {
          const satId = picked.id.id;
          const sat = useSatelliteStore.getState().satellites.find((s) => s.id === satId);
          if (sat) {
            setSelectedSatellite(sat);
            onSatelliteClick?.(sat);
          }
        }
      }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

      viewerRef.current = viewer;
    };

    init().catch(console.error);

    return () => {
      mountedRef.current = false;
      cancelAnimationFrame(animFrameRef.current);
      if (viewerRef.current) {
        try { (viewerRef.current as { destroy(): void }).destroy(); } catch { /* ignore */ }
        viewerRef.current = null;
      }
      entitiesRef.current.clear();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  const drawTrail = useCallback((selected: SatelliteData | null, time: Date) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const viewer = viewerRef.current as any;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const Cesium = (window as any).Cesium;
    if (!viewer || viewer.isDestroyed() || !Cesium || !selected) return;

    // Remove old trail entity
    const existingTrail = viewer.entities.getById("__trail__");
    if (existingTrail) viewer.entities.remove(existingTrail);

    const orbitalPeriod = 92 * 60 * 1000; // ~92 min in ms
    const steps = 180;
    const positions: unknown[] = [];

    for (let i = 0; i <= steps; i++) {
      const t = new Date(time.getTime() - orbitalPeriod / 2 + (i * orbitalPeriod) / steps);
      const pos = propagateSat(selected, t);
      if (pos) {
        positions.push(Cesium.Cartesian3.fromDegrees(pos[0], pos[1], pos[2]));
      }
    }

    if (positions.length < 2) return;

    viewer.entities.add({
      id: "__trail__",
      polyline: {
        positions,
        width: 1.5,
        material: new Cesium.ColorMaterialProperty(
          Cesium.Color.fromCssColorString("#06b6d4").withAlpha(0.4)
        ),
        arcType: Cesium.ArcType.NONE,
        clampToGround: false,
      },
    });
  }, []);

  useEffect(() => {
    let lastTime = performance.now();
    let trailTimer = 0;
    let lastSelectedId: string | null = null;

    const tick = () => {
      if (!mountedRef.current) return;

      const now = performance.now();
      const delta = Math.min(now - lastTime, 100); // cap at 100ms to avoid jumps
      lastTime = now;

      const { isPlaying, playbackSpeed, currentTime, satellites, selectedSatellite } =
        useSatelliteStore.getState();

      let simTime = currentTime;
      if (isPlaying) {
        simTime = new Date(currentTime.getTime() + delta * playbackSpeed);
        setCurrentTime(simTime);
      }

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const viewer = viewerRef.current as any;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const Cesium = (window as any).Cesium;

      if (!viewer || viewer.isDestroyed() || !Cesium) {
        animFrameRef.current = requestAnimationFrame(tick);
        return;
      }

      const activeIds = new Set<string>();

      for (const sat of satellites) {
        const pos = propagateSat(sat, simTime);
        if (!pos) continue;

        const [lon, lat, alt] = pos;
        activeIds.add(sat.id);

        const isSelected = selectedSatellite?.id === sat.id;
        const cartPos = Cesium.Cartesian3.fromDegrees(lon, lat, alt);
        const color = isSelected
          ? Cesium.Color.fromCssColorString("#06b6d4")
          : Cesium.Color.fromCssColorString("#3b82f6").withAlpha(0.85);
        const pixelSize = isSelected ? 9 : 3;

        if (entitiesRef.current.has(sat.id)) {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const entity = entitiesRef.current.get(sat.id) as any;
          try {
            entity.position = new Cesium.ConstantPositionProperty(cartPos);
            entity.point.color = new Cesium.ConstantProperty(color);
            entity.point.pixelSize = new Cesium.ConstantProperty(pixelSize);
            entity.point.outlineWidth = new Cesium.ConstantProperty(isSelected ? 2 : 0);
          } catch { /* entity may have been removed */ }
        } else {
          try {
            const entity = viewer.entities.add({
              id: sat.id,
              name: sat.name,
              position: cartPos,
              point: {
                pixelSize,
                color,
                outlineWidth: isSelected ? 2 : 0,
                outlineColor: Cesium.Color.fromCssColorString("#06b6d4"),
                heightReference: Cesium.HeightReference.NONE,
                disableDepthTestDistance: Number.POSITIVE_INFINITY,
              },
            });
            entitiesRef.current.set(sat.id, entity);
          } catch { /* skip */ }
        }
      }

      // Remove entities no longer in the active set
      for (const [id, entity] of entitiesRef.current.entries()) {
        if (!activeIds.has(id)) {
          try { viewer.entities.remove(entity); } catch { /* ignore */ }
          entitiesRef.current.delete(id);
        }
      }

      // Redraw trail when selection changes or every 15s
      trailTimer += delta;
      const selId = selectedSatellite?.id ?? null;
      if (selId !== lastSelectedId || trailTimer > 15000) {
        lastSelectedId = selId;
        trailTimer = 0;
        drawTrail(selectedSatellite, simTime);
      }

      animFrameRef.current = requestAnimationFrame(tick);
    };

    animFrameRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animFrameRef.current);
  }, [drawTrail, setCurrentTime]);

  return (
    <div ref={containerRef} className="w-full h-full" style={{ background: "#050508" }} />
  );
}
