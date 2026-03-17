export const CESIUM_CSS =
  "https://cesium.com/downloads/cesiumjs/releases/1.122/Build/Cesium/Widgets/widgets.css";
export const CESIUM_JS =
  "https://cesium.com/downloads/cesiumjs/releases/1.122/Build/Cesium/Cesium.js";
// No token needed - using NASA GIBS imagery, not Cesium Ion services

let cesiumLoadPromise: Promise<void> | null = null;

export async function loadCesium(): Promise<void> {
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
