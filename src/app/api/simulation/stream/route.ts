import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  // Use the six_satellite scenario with google provider
  const backendUrl = "http://10.1.96.155:8001/v1/simulation/stream/six_satellite?llm_provider=google";
  
  try {
    const response = await fetch(backendUrl, {
      headers: {
        Accept: "text/event-stream",
      },
    });

    if (!response.ok) {
      return new NextResponse(`Backend error: ${response.status}`, { status: 502 });
    }

    // Stream the response back to the client
    const stream = new ReadableStream({
      async start(controller) {
        const reader = response.body?.getReader();
        if (!reader) {
          controller.close();
          return;
        }

        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            controller.enqueue(value);
          }
        } finally {
          reader.releaseLock();
          controller.close();
        }
      },
    });

    return new NextResponse(stream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  } catch (error) {
    console.error("[API] Failed to connect to backend:", error);
    return new NextResponse("Failed to connect to simulation backend", { status: 502 });
  }
}
