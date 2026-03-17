import ToolHeader from "@/components/ToolHeader";
import DualGlobeViewer from "@/components/DualGlobeViewer";
import StatusBar from "@/components/StatusBar";

export default function Home() {
  return (
    <div
      className="flex flex-col"
      style={{
        height: "100vh",
        width: "100vw",
        background: "var(--bg-primary)",
        overflow: "hidden",
      }}
    >
      <ToolHeader />
      <DualGlobeViewer />
      <StatusBar />
    </div>
  );
}
