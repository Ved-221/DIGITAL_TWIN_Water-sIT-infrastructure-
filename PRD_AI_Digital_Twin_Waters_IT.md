# Product Requirements Document (PRD)
## AI-Powered Digital Twin for IT Infrastructure — Waters Corporation (PS-06, Health Tech)

**Document type:** Hackathon PRD / MVP Build Guide
**Prepared for:** Smart India Hackathon — PS 06 (Health Tech)
**Version:** 1.0

---

## 1. Executive Summary

IT leaders at large, regulated enterprises can't easily answer a simple but high-stakes question: *"If I change this piece of infrastructure, what else breaks?"*

This project builds an **AI-powered Digital Twin of an IT infrastructure environment** (modeled on Waters Corporation) that lets leaders **simulate infrastructure changes — cloud migration, Kubernetes/OpenShift repositioning, server failure, network changes — before touching the real environment**, and get back a **risk score, blast-radius map, cost estimate, and plain-English AI explanation** of what will happen.

The MVP does **not** attempt to model Waters' real, proprietary infrastructure. It builds a **representative, realistic infrastructure graph** (apps, servers, databases, networks, cloud resources, dependencies) and layers a **simulation engine + AI explanation layer** on top of it. The Digital Twin and simulation engine are the source of truth; the AI (LLM) sits on top to query, explain, and recommend — it never invents infrastructure facts.

---

## 2. About the Company (Context Grounding — Waters Corporation)

> Understanding Waters is essential context for building a *credible* infrastructure model — but the MVP infrastructure itself is a representative simulation, not Waters' real internal network (which is proprietary).

### 2.1 What Waters Corporation Is
- Waters Corporation (NYSE: WAT) is a **global life-sciences, analytical-instrumentation, and diagnostics company** — **not** a water-utility company. The name is misleading.
- It builds scientific instruments, software, chemicals/consumables, and services that laboratories use to determine what a substance is made of (purity, contaminants, composition, stability).
- Core technologies: **Liquid Chromatography (LC/HPLC/UPLC)**, **Mass Spectrometry (MS)**, LC-MS, chemistry/bioseparations, and lab informatics software such as **Empower**.
- Business model: an ecosystem of **Instruments + Informatics (Software) + Consumables + Service**, with recurring revenue (>70%) from consumables and service contracts.

### 2.2 Scale (as of 2026, post BD Biosciences/Diagnostics combination)
| Metric | Value |
|---|---|
| Employees | ~16,000 |
| CY2025 revenue | ~$6.4B |
| R&D spend | ~10% of product sales |
| Recurring revenue | >70% |
| HQ | Milford, Massachusetts, USA |
| Divisions | 4 (Analytical Sciences, Biosciences, Advanced Diagnostics, Materials Sciences) |
| Footprint | Global — North America, Europe, Asia, and other international markets |

The 2026 combination with BD's Biosciences and Diagnostic Solutions businesses roughly doubled the company's complexity — four divisions instead of one, many more product lines, and a much larger, more heterogeneous IT estate to manage.

### 2.3 Why This Matters for the Project
Waters runs in a **highly regulated, pharma/diagnostics-adjacent environment**, so infrastructure changes aren't "just IT work" — they carry compliance, data-integrity, validation, and audit-trail implications. You can't just "shut a server down for two hours." This is precisely why a *predictive* impact-simulation tool is valuable instead of a reactive one.

---

## 3. IT Infrastructure Landscape (Conceptual Model)

Waters operates two connected worlds:

```
PHYSICAL WORLD                      DIGITAL WORLD
Laboratories                        Applications
  ↓                                   ↓
Scientific Instruments              Servers
  ↓                                   ↓
Manufacturing Facilities            Databases
  ↓                                   ↓
Offices / Warehouses                Cloud
  ↓                                   ↓
Service Centers                     Networks → Identity → Security → Data
```

Key characteristics that make this a strong Digital Twin use case:

1. **Hybrid infrastructure** — on-prem + cloud (AWS is used for the `waters_connect` ecosystem) + edge (lab instruments) + container/Kubernetes platforms.
2. **Highly regulated** — compliance, validation, audit trails, and availability requirements are non-negotiable.
3. **Global & distributed** — a change in one region/site can ripple across others.
4. **Deeply interdependent** — applications (e.g., Empower) connect to databases, APIs, authentication, storage, backup, and downstream lab systems. A single change can cascade across many systems.

A simplified conceptual enterprise architecture to use as the *shape* of your simulated environment:

```
WATERS ENTERPRISE
 ├── USERS → Identity/SSO
 ├── SITES → Network/WAN
 └── LABS  → Instruments → Edge Software
       ↓
   APPLICATIONS (ERP/CRM, Lab Apps, Analytics)
       ↓
   DATABASES → STORAGE → BACKUPS → MONITORING → SECURITY
```

---

## 4. Problem Statement (Official — PS-06, Health Tech)

**Title:** AI-Powered Digital Twin for IT Infrastructure

**Business Problem:** Leaders struggle to visualize the impact of infrastructure changes before implementation (e.g., migrating on-prem workloads to cloud or Kubernetes/OpenShift-based environments, application/component repositioning, etc.). This problem becomes especially critical as risks and dependencies multiply with scale.

**AI Approach:** Build a digital twin of the organization's IT infrastructure using predictive analytics and simulation.

**Data Required:** CMDB (Configuration Management Database), monitoring data, network topology, workload metrics.

**Expected Outcome:** Leaders can simulate "what-if" scenarios (cloud migration, network upgrades, outages, etc.) and see the business impact *before* execution — moving IT from reactive monitoring to strategic scenario planning.

### 4.1 Problem Statement — Plain English Translation

IT leaders manage huge, interconnected technology environments. When they want to make a change — like moving an application from their own servers to the cloud — they can't easily see all the other systems, networks, databases, and applications that might be affected. Because components depend on each other, one small change can create unexpected problems elsewhere, and by the time you find out, the damage is already done.

**The fix:** Build a digital copy of the IT infrastructure, model the relationships between its components, let leaders propose a change, simulate it, and use AI to predict impact, risk, dependencies, and recommended actions **before** the real infrastructure is touched.

### 4.2 Key Terms Explained
| Term | Meaning in this context |
|---|---|
| **Digital Twin** | A live/virtual digital representation of a real system — its components, properties, relationships, and current state — that can be experimented on safely instead of the real environment. |
| **On-prem** | Infrastructure physically owned and operated by the company (own data center: servers, storage, network gear). |
| **Cloud** | Infrastructure rented from providers like AWS/Azure/GCP instead of self-hosted. |
| **KOB** | Kubernetes/OpenShift-based (container-orchestration) target environments — workloads can move not just on-prem→cloud but across container platforms too. |
| **AP repositioning** | Changing where an infrastructure/application component is hosted or positioned within the architecture (e.g., moving a service between regions or platforms). *Note: confirm the exact organizational definition with PS organizers if asked in a jury round — for the MVP, treat it generically as "component relocation."* |
| **Blast radius** | The full set of downstream/upstream components affected when one component changes or fails. |
| **CMDB** | Configuration Management Database — the system of record for infrastructure components and their relationships (your Digital Twin effectively acts as a smart CMDB + simulator). |

### 4.3 Why This Is Hard (The Core Insight)
With a handful of systems, tracing "if I change A, what breaks?" is easy. At enterprise scale — hundreds/thousands of servers, apps, databases, APIs, and cloud resources — dependencies form a dense graph, and no human can hold that mentally. This is a classic **graph traversal + risk-scoring + explainability** problem, which is exactly what makes it tractable for a hackathon: you don't need real data, you need a **realistic graph + a real algorithm + a good explanation layer**.

---

## 5. What Our Project Solves (Our Solution Statement)

We are building **"InfraTwin"** *(placeholder name — rename freely)*: an AI-powered Digital Twin platform that:

1. **Models** an organization's IT infrastructure as an interactive dependency graph (apps, servers, databases, networks, cloud resources, identity, storage).
2. **Simulates** proposed changes (cloud migration, Kubernetes repositioning, server/node failure, network link failure, capacity changes) against that graph **before** they happen in the real world.
3. **Calculates** blast radius, risk score, estimated downtime, and cost impact using a rule-based/graph-algorithmic simulation engine (source of truth — not the LLM).
4. **Explains** results in plain English using an LLM that is *grounded* in the twin's actual data (retrieval-augmented, not hallucinated).
5. **Recommends** the safest/most cost-effective path forward (e.g., "migrate authentication connectivity first, then the app") and lets leaders compare multiple scenarios side-by-side.

**Design principle (critical for judges):** `Digital Twin → Simulation Engine → AI Explanation`, never `LLM → invents an architecture → calls it a digital twin`. The structured graph and simulation engine are ground truth; AI sits on top to make it usable via natural language.

---

## 6. Target Users & Use Cases

| User | Need | How the product helps |
|---|---|---|
| IT Infrastructure Lead | Decide whether/how to migrate a workload | What-if simulation + risk/cost report before executing |
| Cloud/Platform Architect | Understand dependency chains before repositioning services | Interactive dependency graph + blast radius view |
| CIO / IT Director (Executive) | Get a business-level view of infra health & risk, not raw logs | Executive dashboard, scenario comparison, cost projections |
| Security/Compliance Owner | Understand security impact of a proposed change | Cybersecurity impact analysis module |
| SRE / Ops (stretch) | Plan for failure scenarios and recovery | Failure simulation, disaster-recovery simulator, rollback simulation |

---

## 7. MVP Scope — Feature Prioritization

Building all 25 possible features is out of scope for a hackathon. Scope is split into **Tier 1 (must-have, build first)**, **Tier 2 (build if time remains — makes the demo impressive)**, and **Tier 3 (stretch/backlog, mention in pitch as roadmap)**.

### 🥇 Tier 1 — Must Have (Core MVP)
1. **Interactive Infrastructure Digital Twin** — a seeded, representative infra graph (apps, servers, DBs, networks, cloud resources) rendered visually.
2. **Dependency Graph & Mapping** — every component stores its dependencies and reverse-dependencies (what depends on it).
3. **What-If Simulation Engine** — propose a change (e.g., "migrate App A to cloud"), engine traverses the graph and returns affected components.
4. **Blast Radius Analysis** — visually highlight affected components by severity (🔴 critical / 🟠 high / 🟡 moderate / 🟢 none).
5. **AI Impact Explanation** — LLM turns the simulation's structured output into a plain-English explanation grounded in twin data (not free-form generation).

### 🥈 Tier 2 — High-Impact, Build If Time Allows
6. **Migration Simulator (wizard)** — select workload → select destination (on-prem/AWS/Azure/K8s) → get risk score, estimated downtime, cost delta, and a recommendation.
7. **Risk + Cost Prediction** — a computed Change Risk Score (criticality + dependency count + security impact + downtime probability + complexity + cost) and a cost comparison (current vs proposed).
8. **AI Recommendation Engine** — compares 2–3 options (do nothing / migrate directly / phased migration) with a reasoned recommendation.
9. **"What If?" Natural-Language Interface** — a chat box where a leader types a question in plain English; it's converted into a graph query + simulation, and the answer is explained in natural language.
10. **Single Point of Failure (SPOF) Detection** — automatically scans the graph for components with no redundancy and flags them.

### 🥉 Tier 3 — Stretch Goals / Roadmap (mention in pitch, build only if ahead of schedule)
- Kubernetes/K8s cluster simulator (nodes/pods, scaling, node failure).
- Cybersecurity impact analysis (IAM, encryption, network segmentation scoring).
- Architecture-diagram-to-twin auto-import via a vision-capable LLM + OCR.
- Disaster recovery simulator (RTO/RPO calculation).
- Scenario comparison table (on-prem vs cloud vs hybrid vs K8s).
- Automated, exportable Change Impact Report (PDF).
- Infrastructure "time machine" (before/after/proposed state comparison).

---

## 8. How the Product Works — End-to-End Flow

```
1. Leader logs in → sees Executive Dashboard (infra health, risk, cost overview)
2. Leader opens the Infrastructure Graph → explores current-state components & dependencies
3. Leader initiates a "What-If" action:
      - via UI wizard ("Migrate App A → AWS"), or
      - via natural-language chat ("What happens if we move the ERP database to the cloud?")
4. Simulation Engine:
      a. Parses the proposed change
      b. Traverses the dependency graph (forward + reverse dependencies)
      c. Applies rule-based impact logic (network, security, cost, downtime heuristics)
      d. Computes: affected components, risk score, estimated downtime, cost delta
5. AI Layer:
      a. Receives the structured simulation result (never raw infra secrets, never free invention)
      b. Generates a plain-English explanation + recommendation
6. UI renders:
      - Before/After graph state
      - Blast radius heat-map (🔴🟠🟡🟢)
      - Risk/Cost/Downtime scorecard
      - AI explanation + "Why?" drill-down
      - Recommended migration strategy
```

### 8.1 Example Demo Script (for judges)
1. Show the current-state infrastructure graph (Empower app → Database → Storage → Auth → dependent apps).
2. Type in chat: *"What happens if we migrate Empower's database to AWS?"*
3. System highlights blast radius: Empower, 2 dependent apps, Auth service, Reporting.
4. Show computed **Risk: High**, **Estimated downtime: 42 min**, **Cost delta: +$2,100/month**.
5. Click **"Why?"** → AI explains: *"Risk is high because Empower has a hard dependency on Database X, which has no cross-region replica, creating a cross-environment latency risk."*
6. Click **AI Recommendation** → shows 3 options (do nothing / direct migration / phased migration) and recommends the phased approach with reasoning.
7. (If time) Run a **Blast Radius / SPOF scan** across the whole graph to show proactive risk discovery, not just reactive simulation.

---

## 9. Data Model (MVP)

### 9.1 Core Entities

**`components`**
| Field | Type | Notes |
|---|---|---|
| id | UUID/string | Primary key |
| name | string | e.g., "Empower", "Auth Service", "DB-01" |
| type | enum | application, server, database, network, cloud_resource, storage, api, identity, k8s_node, k8s_pod |
| environment | enum | on-prem, cloud, kubernetes, hybrid |
| location | string | site/region |
| criticality | enum | low, medium, high, critical |
| owner | string | team/person responsible |
| status | enum | active, degraded, offline |
| cpu / memory / cost_per_month | numeric | for simulation math |
| metadata | JSON | extensible attributes |

**`dependencies`**
| Field | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| source_id | FK → components.id | The dependent component |
| target_id | FK → components.id | The component depended on |
| relationship_type | enum | depends_on, connects_to, stores_in, authenticates_via, hosted_on |
| criticality | enum | hard dependency vs soft dependency |

**`simulations`**
| Field | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| requested_change | JSON | e.g., `{action: "migrate", target: "app_001", destination: "aws"}` |
| affected_components | JSON array | computed |
| risk_score | int (0–100) | computed |
| estimated_downtime_min | int | computed |
| cost_delta_monthly | numeric | computed |
| ai_explanation | text | LLM output, stored for audit/history |
| created_at | timestamp | |

**`users`** — standard auth table (id, name, email, role).

### 9.2 Example Component JSON
```json
{
  "id": "app_001",
  "name": "Empower",
  "type": "application",
  "environment": "on-prem",
  "criticality": "high",
  "dependencies": ["db_001", "storage_001", "auth_001"]
}
```

### 9.3 Example Simulation Result JSON
```json
{
  "change": "Migrate Application A (Empower) from on-prem to AWS",
  "affected_components": 7,
  "risk_score": 78,
  "risk_level": "HIGH",
  "estimated_downtime_minutes": 42,
  "cost_delta_monthly": 2100,
  "critical_dependency": "Authentication Service remains on-prem — cross-environment dependency",
  "recommendation": "Migrate authentication connectivity first, validate network access, then migrate the application."
}
```

---

## 10. Simulation Logic (MVP — Rule-Based, No ML Needed)

For the MVP, use **deterministic, explainable rules over the dependency graph** rather than machine learning — this is faster to build, easier to demo, and more defensible to judges ("How does your system *know* this?").

Example rule set:
```
IF application moves to cloud
AND a hard dependency (e.g., database) stays on-prem
THEN increase latency_risk
AND flag "cross-environment dependency"
AND require "secure network connection" recommendation

IF component has 0 redundant/backup nodes
THEN flag as Single Point of Failure (SPOF)

IF affected_components > 5 AND includes a "critical" component
THEN risk_level = HIGH

risk_score = f(business_criticality, dependency_count, security_impact,
               downtime_probability, migration_complexity, cost_impact)
```

Graph traversal (forward dependencies + reverse dependencies) can be implemented with **NetworkX** in Python (BFS/DFS from the changed node in both directions).

---

## 11. Recommended Tech Stack

Kept intentionally lean — practical for a hackathon timeline, not "30 technologies."

| Layer | Technology | Why |
|---|---|---|
| Frontend | React + TypeScript + Vite | Standard, fast to build, judge-friendly |
| Styling | Tailwind CSS | Fast, clean UI |
| Infrastructure graph visualization | **React Flow** | Purpose-built node/edge graph rendering — don't build this from scratch |
| Charts | Recharts | Risk/cost/performance charts |
| Backend | **Python + FastAPI** | Best fit for graph algorithms, simulation logic, AI integration, quick REST APIs |
| Primary database | **PostgreSQL** | Stores components, dependencies, simulation results, metrics |
| Graph algorithms | **NetworkX** (Python) | Dependency traversal, blast radius, SPOF detection — no need for a separate graph DB at MVP scale |
| Vector DB / RAG (optional) | **pgvector** on Postgres | If doing RAG over Waters public docs — avoids adding a new DB |
| AI / LLM | OpenAI API / Claude API / Gemini API (pick one) | Explanation + recommendation layer, grounded in simulation output |
| RAG framework (optional) | LangChain or LlamaIndex | If building the knowledge-base/RAG feature |
| Vision (stretch) | Vision-capable LLM + OCR | For "upload architecture diagram → auto-generate twin" feature |
| Auth | Supabase Auth (or Clerk/Auth0) | Don't build auth from scratch |
| File storage | Supabase Storage | For uploaded diagrams/docs (stretch feature) |
| Frontend deployment | Vercel | Zero-config React deploys |
| Backend deployment | Render / Railway | Simple FastAPI hosting |
| DB hosting | Supabase PostgreSQL | Bundles Postgres + pgvector + Auth + Storage |
| Version control | GitHub | — |

**Note on graph database:** Start with PostgreSQL relational tables (`components`, `dependencies`). Only introduce Neo4j if the graph genuinely becomes too complex for relational queries — don't add it just because "Digital Twin = graph database."

### 11.1 Reference Architecture
```
                    USER
                     │
                     ▼
        ┌─────────────────────────┐
        │ React + TypeScript UI   │
        │ (Graph View + Chat +    │
        │  Dashboard)             │
        └────────────┬────────────┘
                     │ REST / WebSocket
                     ▼
        ┌─────────────────────────┐
        │     FastAPI Backend     │
        └────────────┬────────────┘
                     │
     ┌───────────────┼────────────────┐
     ▼                ▼                ▼
┌──────────┐   ┌───────────────┐  ┌────────────┐
│ Digital  │   │  Simulation   │  │ AI / LLM   │
│ Twin     │   │  Engine       │  │ Engine     │
│ Engine   │   │ (NetworkX +   │  │ (grounded  │
│          │   │  rule engine) │  │ explanations)│
└────┬─────┘   └───────┬───────┘  └─────┬──────┘
     └────────────────┼─────────────────┘
                     ▼
        ┌─────────────────────────┐
        │  PostgreSQL             │
        │  (components, deps,     │
        │   simulations, pgvector)│
        └─────────────────────────┘
```

### 11.2 Sample API Surface
```
POST   /api/twin                  # create/seed the twin
GET    /api/twin/components       # list components
GET    /api/twin/dependencies     # list dependency edges
POST   /api/simulate              # run a what-if simulation
POST   /api/migration             # run migration wizard
GET    /api/risk                  # get current risk overview
POST   /api/chat                  # natural-language "what if" interface
GET    /api/blast-radius/{id}     # blast radius for a component
GET    /api/spof                  # single-points-of-failure scan
```

---

## 12. Phase-Wise Implementation Plan

Assuming a typical hackathon timeline (adjust hours to your actual schedule — shown here as a 5-phase, ~48–72 hour plan).

### Phase 0 — Setup & Design (Hours 0–4)
- Finalize team roles (frontend / backend / AI-integration / design-pitch).
- Set up repo, project scaffolding (FastAPI backend, React+Vite frontend, Postgres via Supabase).
- Design the seed dataset: ~15–25 representative components (apps, DBs, servers, network, cloud resources) with realistic dependencies, modeled conceptually on Waters' environment (Empower-like app, LC/MS data pipeline, ERP, auth service, etc.).
- Define the `components` / `dependencies` / `simulations` schema.

### Phase 1 — Core Digital Twin (Hours 4–14)
- Build Postgres schema + seed script for components/dependencies.
- Build backend CRUD endpoints (`/twin/components`, `/twin/dependencies`).
- Build the frontend graph view using React Flow — render the seeded infra as an interactive node/edge diagram.
- Component detail panel (click a node → see dependencies, dependents, criticality, owner).

**Deliverable:** A working, browsable infrastructure graph — this alone should already look impressive.

### Phase 2 — Simulation Engine (Hours 14–26)
- Implement graph traversal with NetworkX (forward + reverse dependency BFS/DFS from a changed node).
- Implement rule-based impact logic (latency risk, cross-environment dependency flags, cost delta estimation, downtime estimation).
- Implement Change Risk Score calculation.
- Build `/api/simulate` and `/api/migration` endpoints.
- Frontend: "Simulate Change" UI (select component → select action: migrate to cloud / migrate to K8s / remove / fail) → results panel.

**Deliverable:** You can pick a component, propose a change, and get a structured impact result.

### Phase 3 — Blast Radius + AI Explanation Layer (Hours 26–36)
- Implement Blast Radius visualization: color-code affected nodes (🔴🟠🟡🟢) directly on the React Flow graph.
- Integrate LLM API: feed the structured simulation JSON into a prompt template that produces a grounded, plain-English explanation (never let the LLM invent infra facts — always pass it the actual simulation output as context).
- Implement the "Why?" drill-down and AI Recommendation Engine (compare 2–3 options with reasoning).
- Build the Natural-Language "What If?" chat interface (`/api/chat`) — parses user intent into a structured simulation call.

**Deliverable:** The full "propose → simulate → visualize → explain → recommend" loop works end-to-end. This is your core demo.

### Phase 4 — Executive Dashboard + Polish (Hours 36–46)
- Build the Executive Dashboard: overall infra health %, critical services count, high-risk components count, current infra cost, migration opportunity estimate, SPOF count.
- Implement Single Point of Failure (SPOF) auto-detection scan.
- UI/UX polish: consistent styling (Tailwind), loading states, error handling, responsive layout.
- (If time) Add one Tier-2/3 stretch feature: scenario comparison table, or Change Impact Report export.

**Deliverable:** A demo-ready, visually polished product with an executive-level summary view, not just a graph.

### Phase 5 — Demo Prep & Deployment (Hours 46–52)
- Deploy frontend to Vercel, backend to Render/Railway, DB on Supabase.
- Rehearse the demo script (Section 8.1).
- Prepare the pitch deck: Problem → Why it matters at Waters' scale → Solution architecture → Live demo → Roadmap (Tier 3 features) → Impact/business value.
- Buffer time for bug fixes discovered during rehearsal.

**Deliverable:** Deployed, working MVP + rehearsed demo + pitch deck.

---

## 13. Success Metrics (How to Judge Your Own MVP)

- ✅ Can a user propose a change and get a **risk score + affected-component list** in under 2 seconds?
- ✅ Does the blast radius visually and correctly reflect the dependency graph (no hallucinated dependencies)?
- ✅ Is every AI explanation **traceable back to actual simulation data** (never free-floating LLM claims)?
- ✅ Can the natural-language chat correctly convert at least 3–5 example questions into valid simulations?
- ✅ Does the executive dashboard summarize risk/cost at a glance, understandable by a non-technical judge in <10 seconds?

---

## 14. Risks, Assumptions & Mitigations

| Risk | Mitigation |
|---|---|
| No real Waters infra data available | Use a realistic, clearly-labeled *representative/simulated* dataset — state this explicitly in the pitch; judges expect this for SIH PS problems. |
| LLM hallucinating infra facts | Never let the LLM free-generate architecture facts — always ground it by injecting the simulation engine's structured JSON output into the prompt (RAG-style grounding, not open generation). |
| Scope creep (trying to build all 25 features) | Stick strictly to the Tier 1 list first; only move to Tier 2/3 once Tier 1 is fully working end-to-end. |
| Graph visualization becoming cluttered/unreadable | Cap the seed dataset at ~15–25 nodes; use color-coding and collapsible groups rather than showing everything at once. |
| Team unfamiliar with graph algorithms | NetworkX has simple built-in BFS/DFS/shortest-path functions — no need to hand-roll graph theory. |
| Running out of time for AI integration | Build the rule-based simulation engine first (it works standalone and is demoable on its own); layer the LLM explanation on top last — it degrades gracefully if the LLM step is skipped. |

---

## 15. Elevator Pitch (For the Jury)

> "IT leaders at companies like Waters manage thousands of interdependent applications, servers, and cloud resources. When someone proposes migrating a workload to the cloud or repositioning it to Kubernetes, nobody can fully predict what breaks — because the risks and dependencies multiply with scale. We built an AI-powered Digital Twin that lets leaders simulate any infrastructure change *before* they make it — instantly seeing the blast radius, risk score, downtime estimate, and cost impact, with an AI layer that explains *why* in plain English and recommends the safest path forward. This turns IT from reactive firefighting into strategic, predictive scenario planning."

---

## 16. References
- Waters 2025 Annual Report (public financials, business model, regulatory context) — useful as a grounding source for the digital twin's assumptions.
- Waters public cybersecurity disclosures (network segmentation, IAM, DLP, monitoring — useful for the stretch Cybersecurity Impact Analysis feature).
- PS-06 official problem statement text (Section 4 of this document).

---

### Appendix A — Suggested Seed Dataset (Starting Point)

To get moving immediately, seed ~18–20 components such as:

- **Applications:** Empower (lab informatics), ERP System, CRM, Reporting/Analytics App, Lab Data Portal
- **Databases:** Empower DB, ERP DB, Analytics DB
- **Servers:** On-prem App Server (x2), On-prem DB Server
- **Network:** Corporate WAN, Firewall, Load Balancer, VPN Gateway
- **Cloud resources:** AWS Compute, AWS RDS, AWS S3 (representing `waters_connect`-style cloud usage)
- **Identity/Security:** Authentication Service (SSO), IAM
- **Edge/Lab:** Lab Instrument Gateway (edge software layer)
- **Storage/Backup:** Primary Storage, Backup System

Wire dependencies so that at least one critical node (e.g., Authentication Service) has many dependents — this makes your SPOF detection and blast-radius demos genuinely compelling.
