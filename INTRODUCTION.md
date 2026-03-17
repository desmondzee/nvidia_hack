# Autonomous Satellite Traffic Negotiation: An Agentic Approach

## The Problem: A Crowded Sky on a Collision Course

Space is filling up faster than the systems governing it can keep pace.

As of early 2025, there are over **14,000 satellites in orbit**, of which approximately **10,400 are actively functioning** — and the pace of deployment is accelerating sharply. SpaceX's Starlink constellation alone operates more than **9,400 satellites**, representing nearly half of all active spacecraft in orbit. The FCC approved an additional 15,000 Starlink satellites in January 2026, with SpaceX seeking authorization for up to **29,988** across multiple orbital shells. Amazon Kuiper, OneWeb, and dozens of national programs are adding thousands more on overlapping timelines.

Alongside those active satellites are an estimated **40,000+ tracked artificial objects** in orbit, including rocket bodies, defunct satellites, and debris fragments larger than 10 cm — the threshold at which a collision becomes catastrophic. Below that threshold are hundreds of millions of smaller fragments too small to track but large enough to destroy a spacecraft on impact.

The systems managing this traffic were built for a different era. The U.S. Space Force's 18th Space Control Squadron generates **Conjunction Data Messages (CDMs)** and publishes them to operators via Space-Track.org. Operators must manually assess risk, plan maneuvers, and coordinate with counterparts — a process that takes **hours to days**, depends on individual expertise, and cannot plausibly scale to a future with 30,000+ satellites in the same orbital shells.

The FCC recognized this in October 2025, adopting a *Space Modernization for the 21st Century* rulemaking requiring operators to file real-time ephemeris data — a step toward machine-readable situational awareness. But data availability alone does not solve the coordination problem. **We need agents that can act on that data autonomously.**

---

## Kessler Syndrome: The Worst-Case Scenario

In 1978, NASA scientists Donald J. Kessler and Burton G. Cour-Palais published *"Collision Frequency of Artificial Satellites: The Creation of a Debris Belt"* — a paper describing a scenario now known as **Kessler Syndrome**.

The concept is simple and catastrophic. As debris density in low Earth orbit (LEO) increases, the probability of collisions increases. Each collision generates thousands of new debris fragments. Those fragments collide with other objects, generating more debris. At some density threshold, the cascade becomes **self-sustaining** — a runaway chain reaction that renders entire orbital shells permanently unusable, on timescales of decades to centuries.

This is not a theoretical concern. The warning signs have already arrived:

- **February 2009**: Iridium 33 and Cosmos 2251 collided at **11.7 km/s**, generating over 2,000 catalogued debris fragments. As of 2024 — fifteen years later — more than 1,100 of those pieces remain in orbit.
- **November 2021**: Russia's ASAT test against Cosmos 1408 created approximately **1,500 trackable debris pieces** plus hundreds of thousands of smaller fragments, forcing ISS crew to shelter in escape capsules and triggering an emergency evasive maneuver the following year.
- **2022**: ISS executed a debris avoidance maneuver with less than 12 hours of warning — well within the current process's margin of safety, but only barely.

The most commercially valuable orbital shells — LEO between 500–1,200 km, where Earth observation, broadband, and weather satellites operate — are also the most congested. A major debris cascade in this zone would simultaneously degrade GPS, weather forecasting, maritime and air traffic management, and scientific Earth observation. The economic disruption would be measured in the trillions of dollars; the environmental and humanitarian effects from losing weather satellite coverage alone would be significant.

**The window to prevent Kessler Syndrome is closing.** The number of active satellites has roughly doubled in the last three years. The current human-in-the-loop coordination process cannot scale to match.

---

## The Agentic Approach: Decentralized, Autonomous Negotiation

This project proposes a fundamentally different model: **each satellite is represented by an autonomous AI agent** that continuously monitors collision risk, evaluates options, and negotiates maneuvers with peer satellite agents — without requiring centralized human dispatch for every routine decision.

The system has three layers:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Satellite Agent Loop                              │
│                                                                           │
│  ┌───────────────────┐   ┌────────────────────┐   ┌──────────────────┐  │
│  │  1. DATA LAYER    │──▶│  2. AGENT LAYER    │──▶│  3. MEMORY LAYER │  │
│  │                   │   │                    │   │                  │  │
│  │  satellite_       │   │  sentinel_agent    │   │  negotiation_    │  │
│  │  traffic_api      │   │                    │   │  memory          │  │
│  │                   │   │  LangGraph FSM     │   │                  │  │
│  │  Real-time TLE    │   │  LLM reasoning     │   │  NVIDIA NIM      │  │
│  │  Conjunctions     │   │  A2A negotiation   │   │  embeddings      │  │
│  │  Space weather    │   │  Maneuver commit   │   │  Milvus vector   │  │
│  │  Atmosphere       │   │  (up to 3 rounds)  │   │  RAG retrieval   │  │
│  │  Ground contacts  │   │                    │   │                  │  │
│  └───────────────────┘   └────────────────────┘   └──────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### Layer 1: Unified Situational Awareness (satellite_traffic_api)

The data layer aggregates six real-time sources into a single `SatelliteContext` payload, assembled in one API call:

| Source | Data | Update frequency |
|---|---|---|
| CelesTrak | Two-Line Element (TLE) orbital parameters | 1 hour |
| Space-Track.org | Conjunction Data Messages (CDMs) | 30 minutes |
| NOAA SWPC | Kp index, F10.7 solar flux, Ap daily | 5 minutes |
| NRLMSISE-00 | Atmospheric density at current altitude | 1 hour |
| Skyfield/SGP4 | Propagated state vectors, 24h trajectory | 1 minute |
| Ground stations | Upcoming uplink/downlink windows | 30 minutes |

Every satellite agent queries one endpoint and receives the complete picture: where the satellite is now, what is threatening it, what the space environment looks like, when it can communicate with ground, and what risk level the system has assessed. The `SatelliteContext` is the agent's single source of truth.

Risk classification runs two paths simultaneously — a deterministic rules engine (miss distance and collision probability thresholds) and an **XGBoost classifier** trained to recognize compound risks that rules miss (fast-closing geometry + debris type + imminent TCA). The system takes the more conservative of the two assessments.

### Layer 2: Autonomous Negotiation (sentinel_agent)

When risk exceeds HIGH threshold, the sentinel agent activates. It receives an `EnrichedCollisionAlert` containing:

- Full ECI state vectors for both objects at the predicted Time of Closest Approach (TCA), propagated by SGP4
- Space weather parameters and atmospheric drag corrections
- Dual risk scores (rule-based + ML)
- Ground contact windows relevant to maneuver uplink timing

The agent is built on **LangGraph** — an open-source directed-graph orchestration framework from LangChain — as a finite state machine with two roles:

**Initiator graph** (we detected the collision first):
```
analyze_collision → generate_proposal → await_response → evaluate_response
        ↑                                                        │
        └──────────────── (rejected, next round) ───────────────┘
                                                        │
                                               make_final_decision
```

**Responder graph** (peer contacted us):
```
receive_proposal → evaluate_proposal → generate_response
```

Each node calls **Nemotron-Nano-30B** with structured output schemas. The LLM does not just generate free text — it produces typed Pydantic objects: `AnalysisOutput` (who should maneuver, what to share), `ProposalOutput` (delta-V vector in RTN frame, burn timing, expected miss distance after maneuver), `EvaluationOutput` (accept/reject with reasoning), `DecisionOutput` (final agreed maneuver for both parties).

The negotiation runs up to **three rounds**. If agreement is reached, the output is a `ManeuverDecision` — a machine-readable burn command that can be uplinked to the satellite. If not, the agent escalates to human review.

### Layer 3: Memory-Augmented Agents (negotiation_memory)

Each completed negotiation is stored in a **Milvus vector database**, embedded using **NVIDIA NIM embedding models**. Before proposing a maneuver, an agent can query its memory:

*"What did we do the last time we had a CRITICAL conjunction with a Starlink satellite at this relative velocity and altitude?"*

The memory service retrieves semantically similar past negotiations — including the proposals made, whether they were accepted, and the resulting miss distance. This allows agents to learn from experience across the fleet, converging toward maneuver strategies that are efficient (low delta-V) and consistently accepted by peer operators.

The memory service also stores documents — space law, operator policies, maneuver guides, historical incident reports — enabling agents to ground their proposals in established practice.

---

## Why Decentralized Agents Beat Centralized Control

Centralized traffic management has fundamental scaling limits:

| Property | Centralized (today) | Agentic (this system) |
|---|---|---|
| Decision latency | Hours (human review) | Seconds (autonomous) |
| Scale | ~10K satellites | Scales to 100K+ |
| Fault tolerance | Single point of failure | No central authority |
| Operator expertise needed | High | Low |
| Handles novel scenarios | Slowly, needs expert | LLM generalizes |
| Audit trail | Manual reports | Machine-readable per-round log |
| Learns from history | Institutional knowledge | RAG over vector memory |

When a conjunction has a TCA under 12 hours, today's process — CDM generated → operator notified → risk assessed → maneuver planned → command uplinked → maneuver executed — frequently cannot complete in time. With objects closing at 11+ km/s, 12 hours of lead time translates to approximately **475,000 km** of approach path. The window to act narrows fast.

An agentic system compresses this from hours to minutes. The agent reads the same CDM data, reasons over it, proposes a maneuver, and reaches bilateral agreement with the peer satellite's agent — all before a human operator has finished their first cup of coffee.

---

## NVIDIA Technology Stack

This system runs on NVIDIA infrastructure at every layer.

### DGX Spark: Sovereign AI at the Edge

The agent reasoning backbone runs on an **NVIDIA DGX Spark** — a compact, desktop-form-factor AI computer delivering 1 PFLOP of AI compute via the GB10 Grace Blackwell Superchip with 128 GB of unified memory.

Why DGX Spark specifically?

**Latency and sovereignty**: Satellite operations are safety-critical. Sending conjunction data and maneuver decisions to a cloud provider introduces network latency, creates a dependency on internet availability, and raises data sovereignty concerns for defense and government operators. DGX Spark runs the full inference stack **on-premise, air-gapped if required**, with sub-second response times.

**Model scale that fits**: 128 GB unified memory is sufficient to run **Nemotron-Nano-30B** in full precision. Smaller models lack the multi-step reasoning capability needed to evaluate orbital geometry, compare maneuver trade-offs across three negotiation rounds, and produce valid structured outputs. Larger models require multi-node clusters. 30B at this memory bandwidth is the practical sweet spot for edge deployment.

**Operational economics**: A DGX Spark is a capital purchase that runs for years. For a system that must be available 24/7 with no dependency on external API availability or per-token pricing, owned hardware is the correct model — especially for an application where a missed maneuver has irreversible consequences.

**Hackathon-to-production path**: The same model weights, inference server (llama.cpp at port 8080), and OpenAI-compatible API surface used in this demo deploy directly on a DGX SuperPOD for production-scale multi-satellite operations with no code changes.

### Nemotron-Nano-30B: Structured Reasoning for Safety-Critical Decisions

The negotiation engine uses **NVIDIA Nemotron-Nano-30B**, a model designed for structured reasoning tasks. It produces an explicit `reasoning_content` chain of thought before committing to a structured output.

This architecture is intentional for satellite negotiation:

- The model explicitly **works through orbital geometry** — relative velocity, miss distance at current trajectory, expected miss distance after proposed burn — before proposing a delta-V
- It **evaluates strategic trade-offs**: who burns fuel (the satellite with more reserves), what to share with the peer (miss distance yes, full covariance no), whether a counter-proposal is acceptable
- The `reasoning_content` is an **audit trail** — operators and regulators can inspect why the agent chose a specific maneuver, which is a prerequisite for autonomous operation under any emerging regulatory framework
- Structured Pydantic output ensures the maneuver proposal is **machine-parseable**, not just human-readable prose

Served via **llama.cpp** on the DGX Spark using the OpenAI-compatible `/v1/chat/completions` endpoint.

### NVIDIA NIM Embeddings: Memory That Learns

Past negotiations are embedded using **NVIDIA NIM embedding models** and stored in **Milvus**, enabling semantic retrieval. When an agent faces a novel conjunction, it retrieves the most relevant historical negotiations — same object type, similar geometry, comparable space weather conditions — and uses those as context for its current proposal.

This is the flywheel: the more negotiations the fleet runs, the better each agent's proposals become. Over time, the system converges toward an informal corpus of orbital negotiation best practice, grounded in real outcomes rather than theoretical models.

---

## Open Source: Why It Must Be This Way

Space safety is a **global commons problem**. No single company, government, or standards body can solve it unilaterally. Making this framework open source is not a philosophical preference — it is a practical requirement for adoption at the scale the problem demands.

### Trust requires auditability

Satellite operators — especially government and defense operators — must trust the maneuver recommendations their agents make. That trust is only possible when the decision-making logic is fully inspectable. A proprietary black-box system asking operators to approve AI-generated burn commands will face regulatory and liability barriers that cannot be cleared quickly. An open source system with reviewable negotiation logic, published classifier training methodology, and transparent prompt templates can be independently verified.

### Interoperability is non-negotiable

Satellite traffic negotiation requires **bilateral agreement** — both satellites must commit to their respective maneuvers or agree that neither will maneuver. If Operator A uses one proprietary agent framework and Operator B uses another, they cannot negotiate directly. An open protocol and open source reference implementation enables any operator to implement a compatible agent — the same dynamic that made HTTPS enable e-commerce by giving every party the same protocol.

### Regulatory alignment

The FCC's October 2025 *Space Modernization* rulemaking and the ITU's evolving coordination requirements are converging on demands for **automated conjunction response** and **maneuver coordination reporting**. Open source implementations can be submitted as evidence in regulatory proceedings, modified to meet jurisdiction-specific requirements, and independently audited — none of which is possible with proprietary code.

### Scientific reproducibility

The collision risk classifiers, negotiation heuristics, and atmospheric correction models embedded in this system should be **peer-reviewable**. The field has benefited enormously from open standards over the past 40 years — the SGP4 propagator, NRLMSISE-00 atmospheric model, and the CCSDS CDM format are all open. This project continues that tradition.

---

## Environmental Impact: The Hidden Costs of Orbital Congestion

Satellite collisions are not just an operational hazard — they carry a direct environmental footprint.

### Stratospheric metal deposition

When satellites and debris fragments reenter the atmosphere, they ablate and burn up, depositing **aluminum oxide and other metallic compounds** into the stratosphere at 70–90 km altitude. A 2023 PNAS study found that aluminum particles appear in approximately **10% of stratospheric sulfuric acid particles** — at concentrations that cannot be explained by natural meteor sources. The study identified more than 20 elements in ratios consistent with spacecraft alloys.

NOAA research published in 2025 projects that within 15 years, megaconstellation reentries could deposit enough aluminum to **alter polar vortex dynamics**, raise mesosphere temperatures by 1.5°C, and catalyze ozone-depleting chlorine activation reactions. The study estimates that up to **half of all stratospheric sulfuric acid particles** could contain spacecraft reentry metals as constellation deployments continue at current rates.

Collision avoidance has a direct role here: uncontrolled fragmentations from debris collisions produce irregular, unpredictable reentry events with higher ablation rates than controlled deorbits. Fewer collisions means less unplanned stratospheric metal deposition.

### Propellant efficiency under coordination

Every avoidance maneuver burns propellant — a finite resource that determines a satellite's operational lifetime. Without coordination, both satellites may independently maneuver to resolve the same conjunction, each burning fuel for a problem that required only one maneuver. Conservative operators maneuver on low-probability events that would resolve without intervention. Late-warning maneuvers require larger delta-V for the same miss distance improvement.

Bilateral agentic negotiation optimizes **total propellant expenditure across both parties** — identifying which satellite has the better geometry for maneuvering, at what timing the burn is most fuel-efficient, and what minimum delta-V achieves the required miss distance. This directly extends satellite operational lifetimes, deferring replacement launches.

### Launch emissions

A Falcon 9 launch produces approximately **425 metric tonnes of CO₂-equivalent** from propellant combustion, with significantly higher figures for larger vehicles. Satellites destroyed in debris collisions require replacement launches. A cascade that destroys hundreds of satellites — not an implausible scenario in a congested LEO shell — would require hundreds of replacement launches, with aggregate emissions in the hundreds of thousands of tonnes of CO₂-equivalent, compounded by the stratospheric injection from the collision fragmentation events themselves.

Effective autonomous collision avoidance is therefore not just a space safety tool — it is a **climate-relevant intervention** that reduces the carbon intensity of the global satellite infrastructure.

---

## The Path Forward

This project is a proof of concept for a production-ready autonomous satellite traffic management system. The immediate next steps toward real-world deployment:

1. **Multi-agent simulation at scale**: Run 100+ simultaneous agent instances against a realistic constellation simulation, measuring negotiation convergence time, fuel efficiency vs. today's manual process, and failure modes

2. **Open protocol specification**: Define the agent-to-agent negotiation protocol as a formal open standard — message schema, round structure, acceptance criteria — analogous to how the CCSDS CDM format standardized conjunction data exchange over the past two decades

3. **Regulator engagement**: The FCC's October 2025 *Space Modernization* proceeding is the right venue. Contribute the negotiation protocol and agent decision framework as a technical comment, establishing a reference implementation for the rule

4. **On-board edge inference**: Port the lightweight XGBoost risk classifier and a quantized negotiation model to NVIDIA Jetson for next-generation satellite platforms, enabling on-board autonomous response without ground segment round-trip latency

5. **DGX SuperPOD scale-out**: Deploy the full multi-agent system on a DGX SuperPOD to handle the full active satellite catalog (~10,000 objects) in real time, running continuous bilateral negotiation across all high-risk conjunction pairs

The satellite traffic problem will not be solved by incremental improvements to today's centralized, manual, human-in-the-loop processes. It requires a step change to autonomous, decentralized, AI-driven coordination — running at machine speed, at satellite scale, with every decision explainable and every outcome logged.

The technology to build that system exists today. The orbital environment to make it necessary already exists. This project demonstrates that the two can meet.

---

*Built at the NVIDIA Hackathon using DGX Spark, Nemotron-Nano-30B, LangGraph, NVIDIA NIM embeddings, and entirely open source tooling.*

*Key statistics sourced from: ESA Space Environment Report 2025, NOAA Chemical Sciences Laboratory (2025), PNAS (2023), FCC Space Modernization NPRM (October 2025), Space-Track.org, and CelesTrak.*
