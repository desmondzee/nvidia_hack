# Sentinel Agent

Multi-agent satellite collision avoidance system with an LLM-driven negotiation protocol. Satellites (initiator and responder) negotiate maneuver proposals to avoid collisions using structured reasoning and multi-round dialogue. Supports 2-satellite and 3-satellite scenarios with full communication logging.

## Overview

- **Initiator**: Detects a collision alert, analyzes severity, proposes maneuvers, and drives the negotiation loop.
- **Responder**: Receives proposals, evaluates them, and accepts or counters with alternatives.
- **Communication display**: All negotiation messages between agents are shown (proposals, responses, reasoning).
- **LLM providers**: NVIDIA NIM (cloud), Google Gemini (cloud), or **Ollama** (local, falls back to Google if Ollama fails).

## Requirements

- Python 3.11+
- For local models: [Ollama](https://ollama.com/) installed and running

## Installation

```bash
cd sentinel_agent
pip install -e .
```

## Configuration

Copy `.env.example` to `.env` and configure your API keys and model choices:

```bash
cp .env.example .env
```

| Variable | Description |
|----------|-------------|
| `NVIDIA_API_KEY` | Required for `nvidia` provider (NVIDIA NIM) |
| `GOOGLE_API_KEY` | Required for `google` provider (Gemini) |
| `OLLAMA_MODEL` | Model name for `ollama` provider (default: `llama3.2`) |
| `OLLAMA_BASE_URL` | Ollama API URL (default: `http://localhost:11434`) |

### Using Ollama (Local)

1. Install [Ollama](https://ollama.com/) and start the server.
2. Pull a model, e.g.:
   ```bash
   ollama pull llama3.2
   # or for NVIDIA Nemotron 30B parity:
   ollama pull nemotron-3-nano:30b
   ```
3. Set `OLLAMA_MODEL` in `.env` (optional; defaults to `llama3.2`).
4. Run with `llm_provider="ollama"`.

Set `GOOGLE_API_KEY` for automatic fallback to Gemini when Ollama fails or the model is not found. If the model is missing and no key is set, you'll get a clear error.

## Running the Simulation

```bash
python -m src.simulation.runner
```

By default this runs the `three_way` scenario (3 satellites) with Ollama. To change:

```python
# In runner.py main(), or call programmatically:
await run_simulation(scenario="three_way", llm_provider="ollama")  # 3 sats
await run_simulation(scenario="head_on", llm_provider="ollama")    # 2 sats
```

Or run from Python:

```python
import asyncio
from src.simulation.runner import run_simulation

asyncio.run(run_simulation(scenario="three_way", llm_provider="ollama"))
```

### Scenarios

| Scenario | Satellites | Description |
|----------|------------|-------------|
| `head_on` | 2 | High-severity head-on collision between two active satellites |
| `debris` | 2 | Medium-severity conjunction with debris (only our satellite can maneuver) |
| `low_probability` | 2 | Low-probability conjunction — likely no maneuver needed |
| `three_way` | 3 | Three satellites (A, B, C) in close formation; A↔B, A↔C, B↔C negotiate in parallel |

The output shows **negotiation communications** (proposals, responses, reasoning) for each pair, followed by the final results.

## Project Structure

```
sentinel_agent/
├── src/
│   ├── agents/
│   │   ├── llm.py           # LLM provider abstraction (NVIDIA, Google, Ollama)
│   │   └── negotiation_agent.py  # LangGraph initiator/responder graphs
│   ├── models/              # Pydantic models (physics, negotiation, maneuver)
│   ├── physics_interface/   # Mock collision alerts
│   ├── protocol/            # In-memory negotiation channel
│   └── simulation/
│       └── runner.py        # End-to-end simulation entry point
├── tests/
├── pyproject.toml
└── .env.example
```

## Testing

```bash
pytest
```

## License

Part of the NVIDIA Hack project.
