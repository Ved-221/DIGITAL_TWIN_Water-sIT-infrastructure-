# Existing Digital Twin — Reverse Engineering Report

## 1. Executive Summary
This report provides a complete reverse-engineered analysis of the IT Infrastructure Digital Twin implemented in this project (named "InfraTwin"). The analysis relies exclusively on the provided codebase, which consists of a FastAPI Python backend, an SQLite database, and a React frontend utilizing React Flow. No theoretical features have been assumed; every finding is backed by the existing implementation.

## 2. Project Architecture
The project follows a standard three-tier architecture:
*   **Database**: SQLite (`infratwin.db`) accessed via SQLAlchemy ORM.
*   **Backend**: Python FastAPI providing REST endpoints (`main.py`). The backend uses `networkx` to build an in-memory graph for impact analysis (`simulation.py`) and integrates with the Google Gemini API (`ai_engine.py`) to explain simulation results.
*   **Frontend**: React + Vite application (`App.tsx`). It visualizes the infrastructure using `@xyflow/react` (React Flow) and provides a dashboard and simulation interface.

## 3. Digital Twin Model
The Digital Twin models infrastructure as a **Directed Graph**.
1.  **What is considered a "node"?** A `Component` in the system (e.g., a server, database, or application).
2.  **What is considered an "edge"?** A `Dependency` between two components.
3.  **What is considered an "entity"?** An instance of a `Component`.
4.  **What is considered a "dependency"?** A directional relationship showing how one component relies on another.
5.  **What is considered a "resource"?** Any compute, storage, or network entity defined in the `ComponentType` enum.
6.  **What is considered a "service"?** An application or identity component (e.g., SSO).
7.  **What is considered an "application"?** A node with `ComponentType.application`.
8.  **What is considered infrastructure?** The collective graph of all nodes and edges.
9.  **How are relationships represented?** As foreign-key rows in the `dependencies` database table mapping a `source_id` to a `target_id`.
10. **Is the model a graph?** Yes.
11. **If it is a graph, what graph structure is used?** A `networkx.DiGraph` (Directed Graph) constructed in-memory during simulations.
12. **Is it stored in PostgreSQL, another database, JSON, in-memory structures, or something else?** Persisted in SQLite, loaded into in-memory `networkx` for analysis.
13. **Which database tables/models represent the Digital Twin?** `components` and `dependencies` tables (`models.py`).
14. **Which code creates/populates the Digital Twin?** `seed.py` creates the initial mock data.
15. **Which code reads/traverses the Digital Twin?** `simulation.py` reads the DB, builds the graph, and uses `nx.ancestors` and `nx.descendants` to traverse it.

## 4. Actual Node Types
Extracted directly from `models.ComponentType` in `models.py`.

| Node Type | Exact Code/Schema Name | Count | What It Represents | Function | Important Attributes | Parent/Container | Dependencies | Dependents | Source |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Application | `application` | 5 | Business/IT Applications | Provides end-user functionality | environment, criticality | None explicitly | Databases, Servers | End users (implicitly) | `models.py` |
| Server | `server` | 4 | Physical/Virtual Server | Hosts applications or databases | environment, cost_per_month | None explicitly | Network | Applications | `models.py` |
| Database | `database` | 3 | Database System | Stores application data | environment | None explicitly | Servers, Storage | Applications | `models.py` |
| Network | `network` | 2 | Network Hardware/Links | Provides connectivity | environment | None explicitly | Firewalls | Servers | `models.py` |
| Cloud Resource | `cloud_resource` | 2 | Managed Cloud Service | Provides compute/storage in cloud | environment | None explicitly | Network (wan) | Applications | `models.py` |
| Storage | `storage` | 1 | Storage Array/SAN | Provides disk space | environment | None explicitly | None | Databases | `models.py` |
| Identity | `identity` | 1 | Auth/SSO Service | Handles user authentication | environment | None explicitly | None | Applications | `models.py` |
| API | `api` | 0 | API Gateway/Endpoint | Defined in schema but unused in seed | N/A | N/A | N/A | N/A | `models.py` |
| K8s Node | `k8s_node` | 0 | Kubernetes Node | Defined in schema but unused in seed | N/A | N/A | N/A | N/A | `models.py` |
| K8s Pod | `k8s_pod` | 0 | Kubernetes Pod | Defined in schema but unused in seed | N/A | N/A | N/A | N/A | `models.py` |

## 5. Actual Node Counts
*Counts obtained strictly from the `seed.py` file.*

| Node Type | Number of Instances | Example IDs/Names | Where Count Was Obtained |
| :--- | :--- | :--- | :--- |
| **Total Entities** | **17** | | `seed.py` |
| Application | 5 | `app_empower`, `app_erp` | `seed.py` |
| Database | 3 | `db_empower`, `db_erp` | `seed.py` |
| Server | 4 | `srv_app_01`, `edge_gw` | `seed.py` |
| Network | 2 | `net_wan`, `net_fw` | `seed.py` |
| Cloud Resource | 2 | `cloud_compute`, `cloud_s3` | `seed.py` |
| Storage | 1 | `sto_primary` | `seed.py` |
| Identity | 1 | `sec_auth` | `seed.py` |
| API | 0 | None | `seed.py` |
| K8s Node | 0 | None | `seed.py` |
| K8s Pod | 0 | None | `seed.py` |

## 6. Actual Node Instances
Complete inventory of all 17 instances found in `seed.py`:

| ID | Name | Type | Status | Location | Key Attributes | Dependencies (targets) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `app_empower` | Empower (Lab Informatics) | `application` | active (default) | US-East | critical, $5000/mo | db_empower, srv_app_01, sec_auth |
| `app_erp` | ERP System | `application` | active (default) | US-East | critical, $8000/mo | db_erp, srv_app_02, sec_auth |
| `app_crm` | CRM | `application` | active (default) | AWS-us-east-1 | high, $3000/mo | cloud_compute, sec_auth |
| `app_reporting` | Reporting/Analytics | `application` | active (default) | US-East | medium, $1500/mo | db_analytics, cloud_compute |
| `app_lab_portal` | Lab Data Portal | `application` | active (default) | Global | high, $2500/mo | app_empower, sec_auth, cloud_compute |
| `db_empower` | Empower DB | `database` | active (default) | US-East | critical, $2000/mo | srv_db_01, sto_primary |
| `db_erp` | ERP DB | `database` | active (default) | US-East | critical, $4000/mo | srv_db_01, sto_primary |
| `db_analytics` | Analytics DB | `database` | active (default) | AWS-us-east-1 | high, $3500/mo | db_erp, cloud_s3 |
| `srv_app_01` | On-prem App Server 01 | `server` | active (default) | US-East | high, $800/mo | net_wan |
| `srv_app_02` | On-prem App Server 02 | `server` | active (default) | US-East | high, $800/mo | net_wan |
| `srv_db_01` | On-prem DB Server | `server` | active (default) | US-East | critical, $1200/mo | net_wan |
| `edge_gw` | Lab Instrument Gateway | `server` | active (default) | Lab-01 | high, $300/mo | app_empower |
| `net_wan` | Corporate WAN | `network` | active (default) | Global | critical, $10000/mo | net_fw |
| `net_fw` | Core Firewall | `network` | active (default) | US-East | critical, $2000/mo | None |
| `sec_auth` | Authentication Service (SSO) | `identity` | active (default) | US-East | critical, $500/mo | None |
| `cloud_compute` | AWS EC2 Cluster | `cloud_resource` | active (default) | AWS-us-east-1 | high, $4500/mo | net_wan |
| `cloud_s3` | AWS S3 Data Lake | `cloud_resource` | active (default) | AWS-us-east-1 | high, $1200/mo | None |

## 7. Node Attributes
Identified from `models.Component` schema in `models.py`.

| Node Type | Attribute | Data Type | Meaning | Example Value | Static/Dynamic | Required/Optional |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| All | `id` | String | Unique identifier | `app_erp` | Static | Required |
| All | `name` | String | Human readable name | `ERP System` | Static | Required |
| All | `type` | Enum | Classification of component | `application` | Static | Required |
| All | `environment` | Enum | Where it runs | `on_prem`, `cloud` | Static | Required |
| All | `location` | String | Physical/Logical location | `US-East` | Static | Optional |
| All | `criticality` | Enum | Business importance | `critical`, `high` | Static | Required |
| All | `owner` | String | Responsible team | `Finance` | Static | Optional |
| All | `status` | Enum | Operational health | `active` | Dynamic | Optional (defaults active) |
| All | `cpu` | Float | CPU Allocation | `N/A` | Dynamic | Optional |
| All | `memory` | Float | RAM Allocation | `N/A` | Dynamic | Optional |
| All | `cost_per_month` | Float | Run rate | `8000.0` | Static | Optional (defaults 0.0) |
| All | `metadata_col` | JSON | Extensible data | `{}` | Static | Optional |

## 8. Relationships / Edges
Extracted directly from `models.DependencyType` and `seed.py`.

| Source Node | Relationship | Target Node | Meaning | Direction | Criticality | Source |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Application | `depends_on` | Database | App needs DB to function | Source → Target | critical | `seed.py` |
| Application | `hosted_on` | Server | App runs on OS | Source → Target | critical | `seed.py` |
| Application | `authenticates_via` | Identity | App uses SSO | Source → Target | critical | `seed.py` |
| Database | `hosted_on` | Server | DB Engine runs on OS | Source → Target | critical | `seed.py` |
| Database | `stores_in` | Storage | DB writes files to SAN | Source → Target | critical | `seed.py` |
| Server | `connects_to` | Application | Server proxies to App | Source → Target | high | `seed.py` |
| Database | `connects_to` | Database | DB pulls data from another DB | Source → Target | medium | `seed.py` |
| Server | `connects_to` | Network | Server relies on Network | Source → Target | critical | `seed.py` |
| Network | `depends_on` | Network | WAN routes to Firewall | Source → Target | critical | `seed.py` |

## 9. Dependencies
Example explanations derived from implementation behavior in `simulation.py`.

| Dependent | Dependency | Type | Direct/Indirect | Failure Impact | Implemented? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `app_erp` | `db_erp` | `depends_on` | Direct | App goes offline if DB fails. | Yes (`nx.ancestors` traverses this) |
| `app_erp` | `srv_db_01` | `hosted_on` (via db) | Indirect | App goes offline if DB server fails. | Yes (graph traversal catches it) |
| `srv_app_01`| `net_wan` | `connects_to` | Direct | Server loses network if WAN fails. | Yes |

## 10. Dependency Graph
Representation of the `app_empower` stack generated from `seed.py`:

```text
app_empower (Application)
    │
    ├── depends_on ───────► db_empower (Database)
    │                           │
    │                           ├── hosted_on ────► srv_db_01 (Server)
    │                           │                       └── connects_to ──► net_wan
    │                           │
    │                           └── stores_in ────► sto_primary (Storage)
    │
    ├── hosted_on ────────► srv_app_01 (Server)
    │                           └── connects_to ──► net_wan (Network)
    │                                                   └── depends_on ──► net_fw
    │
    └── authenticates_via ──► sec_auth (Identity)

edge_gw (Server)
    │
    └── connects_to ──────► app_empower (Application)
```

## 11. Failure & Impact Analysis
**VERIFIED FROM CODE** (`backend/simulation.py` `simulate_change()`)

When simulating a change (e.g., migrating a node):
1.  **What code detects the failure/change?** Triggered via API POST to `/api/simulate` carrying a `target_component_id`.
2.  **What data structure is queried?** The SQLite database is queried for all components and dependencies, which are instantly mapped into a `networkx.DiGraph`.
3.  **How are dependencies discovered?** `networkx` is used to build the graph.
4.  **How does traversal happen?** 
    *   `nx.ancestors(G, target_component_id)` finds everything that directly or indirectly depends on the target (Dependents).
    *   `nx.descendants(G, target_component_id)` finds everything the target directly or indirectly relies on (Dependencies).
5.  **Which nodes are marked affected?** A Python `set()` named `affected_components` combines both ancestors and descendants. These are returned to the frontend and marked with the `blastRadius` boolean flag, turning them red.
6.  **How is the final impact displayed/calculated?** 
    *   **Risk Score**: Calculated mathematically. Base risk is added based on target criticality (Critical=+40, High=+20). It adds +10 for every high/critical component in the blast radius (max 40) and +15 for every cross-environment dependency introduced by a migration (max 20).
    *   **Cost**: Uses a hardcoded 15% heuristic increase if `destination_env == "cloud"`.
    *   **Downtime**: Estimated using a simple heuristic (DB/Storage=120m, Network/Identity=60m, others=30m).
    *   **AI Explanation**: The JSON risk profile is sent to Google Gemini (`ai_engine.py`) to generate natural language explanations and recommendations.

**NOT CURRENTLY IMPLEMENTED**: Real-time health checks, automated failure detection (nodes are manually marked degraded/offline), or actual SPOF automated detection beyond comment stubs.

## 12. State Model
Extracted from `models.Status` in `models.py`.

| Node Type | State Attribute | Possible Values | Meaning | Used By Simulation? |
| :--- | :--- | :--- | :--- | :--- |
| All | `status` | `active`, `degraded`, `offline` | Current operational health of the node. | No. The simulation currently models hypothetical migrations, ignoring current operational state. |

**State Characteristics**: Currently Static/Hard-coded in DB. There are no polling mechanisms or API integrations to update health dynamically. 

## 13. Digital Twin Data Flow
**Architecture Flow mapped from codebase:**

```text
Database (SQLite `infratwin.db`)
        ↓ (SQLAlchemy)
Backend Models (`models.py`)
        ↓ (FastAPI GET endpoints in `main.py`)
Frontend Graph Data (JSON fetched by `App.tsx`)
        ↓ (React Flow Rendering)
User clicks "Run Simulation"
        ↓ (FastAPI POST `/api/simulate`)
Dependency Engine (`simulation.py` using `networkx.DiGraph`)
        ↓ (Calculates Impact, Risk, Cost)
AI Insights Engine (`ai_engine.py` calls Gemini API)
        ↓ (Returns JSON Explanation & Recommendation)
Frontend Visualization (`App.tsx` renders results & highlights blast radius)
```

## 14. Database Model
**VERIFIED FROM CODE** (`backend/models.py`)

| Table | Purpose | Important Columns | Represents |
| :--- | :--- | :--- | :--- |
| `components` | Stores nodes | `id`, `name`, `type`, `environment`, `criticality`, `cost_per_month` | Digital Twin Entities |
| `dependencies`| Stores edges | `id`, `source_id` (FK), `target_id` (FK), `relationship_type` | Digital Twin Relationships |

The database uses a standard adjacency list format to represent a graph. The relationships table maps Foreign Keys back to the components table.

## 15. API Model
**VERIFIED FROM CODE** (`backend/main.py`)

| Endpoint | Method | Purpose | Input | Output | Digital Twin Function |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/api/twin/components` | GET | Retrieve all nodes | None | List of Component JSON | Populate graph nodes |
| `/api/twin/dependencies`| GET | Retrieve all edges | None | List of Dependency JSON | Populate graph edges |
| `/api/twin/stats` | GET | Retrieve dashboard metrics | None | JSON object with counts/cost | Executive dashboard view |
| `/api/simulate` | POST | Run what-if scenario | JSON (`target_component_id`, `action`, `destination_env`) | JSON (Affected count, Risk, Cost delta, AI Insights) | Core Simulation Engine |

## 16. Frontend Visualization
**VERIFIED FROM CODE** (`frontend/src/App.tsx`)

*   **Graph Library**: `@xyflow/react` (React Flow).
*   **Node Rendering**: Custom component `CustomNode`. Uses `lucide-react` icons based on `node.type`.
*   **Edge Rendering**: Uses React Flow `animated: true` edges with arrows.
*   **Node Colors/Status**: Default is `bg-slate-800`. If `blastRadius` is true, the node turns `border-red-500 bg-red-950/40` with an `AlertTriangle` icon.
*   **Failure/Impact Visualization**: Nodes dynamically update their state and re-render in red based on the `affected_components` list returned by the `/api/simulate` endpoint.
*   **Dashboards**: A separate "Executive View" tab calculates real-time metrics (run rate, critical count, on-prem vs cloud breakdown).

## 17. Terminology / Glossary
Glossary specific to **THIS** implementation:

| Term | Exact Meaning in This Project | Simple Explanation | Where Used |
| :--- | :--- | :--- | :--- |
| **Component** | A single row in the `components` DB table. | A node in the graph (App, Server, etc.) | Backend models, DB. |
| **Dependency** | A single row in the `dependencies` DB table pointing from source to target. | A directional edge in the graph. | Backend models, DB. |
| **Blast Radius** | The set of `affected_components` returned by a simulation. | Everything that breaks if this node changes/fails. | `App.tsx`, `simulation.py`. |
| **Simulate** | A POST request calculating the impact of migrating a component. | Running a "what-if" scenario. | `main.py`, `App.tsx`. |
| **Criticality** | Enum value (`critical`, `high`, `medium`, `low`). | How important a component is. | Used heavily in risk score calculation. |

## 18. Verified vs Inferred vs Unknown
*   **VERIFIED FROM CODE**: All schemas, routes, database tables, react components, graph parsing logic, risk score mathematical models, and seed data relationships.
*   **INFERRED**: The direction of `depends_on`. While stored as `source` and `target`, `networkx` traverses ancestors (dependents) and descendants (dependencies) based on the assumption that `source` relies on `target`.
*   **UNKNOWN**: Whether the application can handle massive scale (10,000+ nodes) efficiently using the current `networkx` on-the-fly graph building approach, as it currently rebuilds the graph on every request.

## 19. What I Need To Learn
To fully understand and extend this project, you should understand these concepts in order:

1.  **FastAPI & SQLAlchemy Basics**: How `main.py` serves data from SQLite.
2.  **React Flow (`@xyflow/react`)**: How `App.tsx` maps JSON arrays into visual nodes and edges on a canvas.
3.  **Graph Theory (Directed Graphs)**: Understanding Ancestors vs Descendants.
4.  **NetworkX Library**: How `simulation.py` uses `nx.DiGraph`, `nx.ancestors()`, and `nx.descendants()` to calculate the blast radius.
5.  **LLM Integration (Gemini)**: How `ai_engine.py` passes JSON data to the AI model to generate human-readable explanations.

## 20. Files / Code Locations
Key locations for modifications:

*   **Node/Edge Definition**: `backend/models.py`
*   **Graph Traversal & Risk Math**: `backend/simulation.py` (`simulate_change()`)
*   **AI Prompt Logic**: `backend/ai_engine.py` (`generate_explanation()`)
*   **API Routes**: `backend/main.py`
*   **Mock Infrastructure Data**: `backend/seed.py`
*   **UI Graph & Simulation Panel**: `frontend/src/App.tsx`
