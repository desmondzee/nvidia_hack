"""FastAPI server with streaming endpoints for negotiation and LLM outputs."""

from __future__ import annotations

import asyncio
import json
import logging
from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse

from src.agents.llm import get_llm
from src.simulation.runner import run_simulation

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Sentinel Agent API",
    description="Streaming API for satellite collision avoidance negotiation",
    version="1.0.0",
)


async def _event_generator(
    scenario: str,
    llm_provider: str,
    event_types: set[str] | None,
):
    """Async generator that runs simulation and yields SSE events."""
    queue: asyncio.Queue[dict] = asyncio.Queue()
    sim_task: asyncio.Task | None = None

    async def run_sim():
        try:
            await run_simulation(
                scenario=scenario,
                llm_provider=llm_provider,
                stream_queue=queue,
            )
        except Exception as e:
            logger.exception("Simulation failed: %s", e)
            await queue.put({"type": "error", "data": {"message": str(e)}})
        finally:
            await queue.put(None)  # Sentinel to signal completion

    sim_task = asyncio.create_task(run_sim())

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=300.0)
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type': 'timeout', 'data': {}})}\n\n"
                break

            if event is None:
                break

            if event_types and event.get("type") not in event_types:
                continue

            yield f"data: {json.dumps(event)}\n\n"
    finally:
        if sim_task and not sim_task.done():
            sim_task.cancel()
            try:
                await sim_task
            except asyncio.CancelledError:
                pass


@app.get("/v1/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/v1/simulation/stream")
async def stream_simulation(
    scenario: str = Query(
        default="three_way",
        description="Scenario: head_on, debris, low_probability, or three_way",
    ),
    llm_provider: str = Query(
        default="ollama",
        description="LLM provider: nvidia, google, or ollama",
    ),
    event_types: str | None = Query(
        default=None,
        description="Comma-separated event types to include. Omit for all. "
        "Options: negotiation_message, llm_output, decision, simulation_start, simulation_end",
    ),
):
    """Stream negotiation data and LLM outputs as Server-Sent Events (SSE).

    Events are emitted in real time as the simulation runs. Each event has:
    - type: negotiation_message | llm_output | decision | simulation_start | simulation_end
    - pair_label: e.g. A↔B (null for simulation-level events)
    - timestamp: ISO 8601
    - data: event-specific payload
    """
    types_set: set[str] | None = None
    if event_types:
        types_set = {t.strip() for t in event_types.split(",") if t.strip()}

    return StreamingResponse(
        _event_generator(scenario, llm_provider, types_set),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/v1/simulation/stream/negotiation")
async def stream_negotiation(
    scenario: str = Query(default="three_way"),
    llm_provider: str = Query(default="ollama"),
):
    """Stream only negotiation messages (proposals and responses) as SSE."""
    return StreamingResponse(
        _event_generator(
            scenario,
            llm_provider,
            event_types={"negotiation_message", "decision", "simulation_start", "simulation_end"},
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/v1/simulation/stream/llm")
async def stream_llm_outputs(
    scenario: str = Query(default="three_way"),
    llm_provider: str = Query(default="ollama"),
):
    """Stream only LLM structured outputs (analysis, proposals, evaluations, decisions) as SSE."""
    return StreamingResponse(
        _event_generator(
            scenario,
            llm_provider,
            event_types={"llm_output", "decision", "simulation_start", "simulation_end"},
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
