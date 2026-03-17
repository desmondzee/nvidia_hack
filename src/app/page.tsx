"use client";

import dynamic from "next/dynamic";
import ToolHeader from "@/components/ToolHeader";
import StatusBar from "@/components/StatusBar";
import { useSatelliteStore } from "@/stores/satelliteStore";

const DualGlobeViewer = dynamic(() => import("@/components/DualGlobeViewer"), { ssr: false });
const CollisionView = dynamic(() => import("@/components/CollisionView"), { ssr: false });

export default function Home() {
  const { viewMode } = useSatelliteStore();

  return (
    <div
      className="flex flex-col"
      style={{ height: "100vh", width: "100vw", background: "var(--bg-primary)", overflow: "hidden" }}
    >
      <ToolHeader />
      {viewMode === "global" ? <DualGlobeViewer /> : <CollisionView />}
      <StatusBar />
    </div>
  );
}
