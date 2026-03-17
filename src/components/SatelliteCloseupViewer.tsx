"use client";

import { useEffect, useRef } from "react";
import { twoline2satrec, propagate, gstime, eciToGeodetic, degreesLong, degreesLat } from "satellite.js";
import { SatelliteData, useSatelliteStore } from "@/stores/satelliteStore";
import { loadCesium } from "@/lib/cesium";

interface Props {
  satellite: SatelliteData;
  label: string;
  accentColor?: string;
  variant?: "A" | "B";
  satId?: string;
}

function getSatPosVel(sat: SatelliteData, time: Date): { 
  lon: number; lat: number; alt: number; 
  vx: number; vy: number; vz: number;
} | null {
  try {
    const satrec = twoline2satrec(sat.tle1, sat.tle2);
    const posVel = propagate(satrec, time);
    if (!posVel?.position || typeof posVel.position === "boolean") return null;
    if (!posVel?.velocity || typeof posVel.velocity === "boolean") return null;
    const gst = gstime(time);
    const geo = eciToGeodetic(posVel.position, gst);
    const alt = geo.height * 1000;
    if (!isFinite(alt) || alt < 0) return null;
    return { 
      lon: degreesLong(geo.longitude), 
      lat: degreesLat(geo.latitude), 
      alt,
      vx: posVel.velocity.x,
      vy: posVel.velocity.y,
      vz: posVel.velocity.z,
    };
  } catch { return null; }
}

export default function SatelliteCloseupViewer({ satellite, label, accentColor = "#06b6d4", variant = "A", satId }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const { highlightedSatellites } = useSatelliteStore();
  
  const statusColor = satId && highlightedSatellites[satId] 
    ? highlightedSatellites[satId] 
    : accentColor;

  useEffect(() => {
    if (!containerRef.current) return;

    let mounted = true;
    let animFrame = 0;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let viewer: any = null;
    
    const init = async () => {
      await loadCesium();
      if (!mounted || !containerRef.current) return;

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const Cesium = (window as any).Cesium;
      
      viewer = new Cesium.Viewer(containerRef.current, {
        baseLayer: false,
        baseLayerPicker: false,
        geocoder: false,
        homeButton: false,
        sceneModePicker: false,
        navigationHelpButton: false,
        animation: false,
        timeline: false,
        fullscreenButton: false,
        vrButton: false,
        skyBox: false,
        skyAtmosphere: false,
        shouldAnimate: false,
      });

      // Enable depth testing so lines behind globe are hidden
      viewer.scene.globe.depthTestAgainstTerrain = true;

      // Dark space imagery
      try {
        viewer.imageryLayers.addImageryProvider(
          new Cesium.UrlTemplateImageryProvider({
            url: "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default//GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg",
            maximumLevel: 8,
          })
        );
      } catch { /**/ }

      // Styling
      viewer.scene.backgroundColor = Cesium.Color.fromCssColorString("#050508");
      viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#0a0a1a");
      viewer.scene.globe.enableLighting = true;
      viewer.scene.globe.lightingFadeOutDistance = 100000000;
      viewer.scene.globe.lightingFadeInDistance = 100000;
      viewer.scene.globe.showGroundAtmosphere = true;
      viewer.scene.globe.atmosphereLightIntensity = 20;
      if (viewer.scene.sun) viewer.scene.sun.show = true;
      if (viewer.scene.moon) viewer.scene.moon.show = false;
      viewer.clock.shouldAnimate = false;

      const { currentTime } = useSatelliteStore.getState();
      const isVariantA = variant === "A";
      
      const meanMotion = parseFloat(satellite.tle2.substring(52, 63).trim());
      const period = meanMotion > 0 ? 1440 / meanMotion : 95;
      
      const posVel = getSatPosVel(satellite, currentTime);
      if (!posVel) return;

      const satPos = Cesium.Cartesian3.fromDegrees(posVel.lon, posVel.lat, posVel.alt);
      const accentCesium = Cesium.Color.fromCssColorString(statusColor);

      // Calculate ENU frame
      const enuMatrix = Cesium.Transforms.eastNorthUpToFixedFrame(satPos);
      const east = new Cesium.Cartesian3(
        Cesium.Matrix4.getColumn(enuMatrix, 0, new Cesium.Cartesian4()).x,
        Cesium.Matrix4.getColumn(enuMatrix, 0, new Cesium.Cartesian4()).y,
        Cesium.Matrix4.getColumn(enuMatrix, 0, new Cesium.Cartesian4()).z,
      );
      const up = new Cesium.Cartesian3(
        Cesium.Matrix4.getColumn(enuMatrix, 2, new Cesium.Cartesian4()).x,
        Cesium.Matrix4.getColumn(enuMatrix, 2, new Cesium.Cartesian4()).y,
        Cesium.Matrix4.getColumn(enuMatrix, 2, new Cesium.Cartesian4()).z,
      );

      const SCALE = 5.0;
      
      if (isVariantA) {
        const BODY_W = 3.0 * SCALE;
        const BODY_H = 0.4 * SCALE;
        const BODY_D = 0.4 * SCALE;
        const PANEL_W = 4.0 * SCALE;
        const PANEL_H = 0.1 * SCALE;
        const PANEL_D = 1.5 * SCALE;
        const GAP = 0.2 * SCALE;

        viewer.entities.add({
          position: satPos,
          box: {
            dimensions: new Cesium.Cartesian3(BODY_W, BODY_H, BODY_D),
            material: accentCesium,
            outline: true,
            outlineColor: Cesium.Color.WHITE,
            outlineWidth: 1,
          },
        });

        const panelOffsetL = BODY_W / 2 + PANEL_W / 2 + GAP;
        const offsetL = Cesium.Cartesian3.multiplyByScalar(east, panelOffsetL, new Cesium.Cartesian3());
        const panelLPos = Cesium.Cartesian3.add(satPos, offsetL, new Cesium.Cartesian3());
        viewer.entities.add({
          position: panelLPos,
          box: {
            dimensions: new Cesium.Cartesian3(PANEL_W, PANEL_H, PANEL_D),
            material: new Cesium.Color(accentCesium.red, accentCesium.green, accentCesium.blue, 0.5),
            outline: true,
            outlineColor: accentCesium,
            outlineWidth: 1,
          },
        });

        const offsetR = Cesium.Cartesian3.multiplyByScalar(east, -panelOffsetL, new Cesium.Cartesian3());
        const panelRPos = Cesium.Cartesian3.add(satPos, offsetR, new Cesium.Cartesian3());
        viewer.entities.add({
          position: panelRPos,
          box: {
            dimensions: new Cesium.Cartesian3(PANEL_W, PANEL_H, PANEL_D),
            material: new Cesium.Color(accentCesium.red, accentCesium.green, accentCesium.blue, 0.5),
            outline: true,
            outlineColor: accentCesium,
            outlineWidth: 1,
          },
        });

      } else {
        const BODY_SIZE = 1.5 * SCALE;
        const PANEL_SIZE = 3.5 * SCALE;
        const PANEL_THICK = 0.2 * SCALE;
        const GAP = 0.3 * SCALE;

        viewer.entities.add({
          position: satPos,
          box: {
            dimensions: new Cesium.Cartesian3(BODY_SIZE, BODY_SIZE, BODY_SIZE),
            material: accentCesium,
            outline: true,
            outlineColor: Cesium.Color.WHITE,
            outlineWidth: 1,
          },
        });

        const panelOffsetTop = BODY_SIZE / 2 + PANEL_THICK / 2 + GAP;
        const offsetTop = Cesium.Cartesian3.multiplyByScalar(up, panelOffsetTop, new Cesium.Cartesian3());
        const panelTopPos = Cesium.Cartesian3.add(satPos, offsetTop, new Cesium.Cartesian3());
        viewer.entities.add({
          position: panelTopPos,
          box: {
            dimensions: new Cesium.Cartesian3(PANEL_SIZE, PANEL_SIZE, PANEL_THICK),
            material: new Cesium.Color(accentCesium.red, accentCesium.green, accentCesium.blue, 0.5),
            outline: true,
            outlineColor: accentCesium,
            outlineWidth: 1,
          },
        });

        const offsetBottom = Cesium.Cartesian3.multiplyByScalar(up, -panelOffsetTop, new Cesium.Cartesian3());
        const panelBottomPos = Cesium.Cartesian3.add(satPos, offsetBottom, new Cesium.Cartesian3());
        viewer.entities.add({
          position: panelBottomPos,
          box: {
            dimensions: new Cesium.Cartesian3(PANEL_SIZE, PANEL_SIZE, PANEL_THICK),
            material: new Cesium.Color(accentCesium.red, accentCesium.green, accentCesium.blue, 0.5),
            outline: true,
            outlineColor: accentCesium,
            outlineWidth: 1,
          },
        });
      }

      // Generate ultra high-res orbit path (8640 segments = 0.04° per segment)
      const orbitPoints: unknown[] = [];
      const satrec = twoline2satrec(satellite.tle1, satellite.tle2);
      const periodMs = period * 60 * 1000;
      const SEGMENTS = 8640;
      
      for (let i = 0; i <= SEGMENTS; i++) {
        const fraction = i / SEGMENTS;
        const t = new Date(currentTime.getTime() + (fraction * periodMs));
        const pv = propagate(satrec, t);
        if (pv?.position && typeof pv.position !== "boolean") {
          const gst = gstime(t);
          const geo = eciToGeodetic(pv.position, gst);
          orbitPoints.push(Cesium.Cartesian3.fromDegrees(
            degreesLong(geo.longitude),
            degreesLat(geo.latitude),
            geo.height * 1000
          ));
        }
      }

      viewer.entities.add({
        polyline: {
          positions: orbitPoints,
          width: 2,
          material: new Cesium.PolylineGlowMaterialProperty({
            glowPower: 0.3,
            color: new Cesium.Color(accentCesium.red, accentCesium.green, accentCesium.blue, 0.6),
          }),
          // Enable depth testing so line is hidden when behind Earth
          depthFailMaterial: new Cesium.PolylineGlowMaterialProperty({
            glowPower: 0.1,
            color: new Cesium.Color(accentCesium.red, accentCesium.green, accentCesium.blue, 0.1),
          }),
        },
      });

      // Set camera with range to see full satellite
      viewer.camera.lookAt(satPos, new Cesium.HeadingPitchRange(
        Cesium.Math.toRadians(45),
        Cesium.Math.toRadians(-25),
        600  // Closer range to see satellite better
      ));

      let localSimTime = currentTime.getTime();

      const tick = () => {
        if (!mounted || viewer.isDestroyed()) return;

        localSimTime += 100;
        const simTime = new Date(localSimTime);

        const newPosVel = getSatPosVel(satellite, simTime);
        if (!newPosVel) { animFrame = requestAnimationFrame(tick); return; }

        const newSatPos = Cesium.Cartesian3.fromDegrees(newPosVel.lon, newPosVel.lat, newPosVel.alt);

        viewer.camera.lookAt(newSatPos, new Cesium.HeadingPitchRange(
          Cesium.Math.toRadians(45),
          Cesium.Math.toRadians(-25),
          600
        ));

        animFrame = requestAnimationFrame(tick);
      };

      animFrame = requestAnimationFrame(tick);
    };

    init().catch(console.error);

    return () => {
      mounted = false;
      cancelAnimationFrame(animFrame);
      if (viewer && !viewer.isDestroyed()) {
        try { 
          viewer.entities.removeAll();
          viewer.destroy(); 
        } catch { /**/ }
      }
    };
  }, [satellite.id, statusColor, variant]);

  return (
    <div className="relative w-full h-full">
      <div ref={containerRef} className="w-full h-full" />
      
      <div 
        className="absolute top-3 left-3 text-xs font-medium tracking-wider pointer-events-none"
        style={{ 
          color: statusColor,
          textShadow: "0 0 10px " + statusColor + "40"
        }}
      >
        <span className="opacity-60">●</span> {satId || label}
      </div>

      <div 
        className="absolute bottom-3 left-3 text-[10px] pointer-events-none"
        style={{ color: "var(--text-secondary)" }}
      >
        <div className="font-medium" style={{ color: "var(--text-primary)" }}>{satellite.name}</div>
        <div className="opacity-60">NORAD {satellite.id}</div>
      </div>
    </div>
  );
}
