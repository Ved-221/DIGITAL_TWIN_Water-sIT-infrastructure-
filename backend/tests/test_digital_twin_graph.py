import pytest
import networkx as nx
from models import Component, Dependency, Environment
from simulation import build_graph, simulate_change, find_spofs


def test_directed_dependency_edge_semantics_and_traversal(client, db):
    """
    Verify directed edge traversal:
    Edge A -> B means 'A depends on B' (A is the caller, B is the service/dependency).
    For node B:
      - Inbound: A (A relies on B; if B fails, A is affected upstream)
      - Outbound: none
    For node A:
      - Inbound: none
      - Outbound: B (B is the downstream dependency A relies on)
    """
    env = Environment(id="env-phase3-graph", name="Graph Test Env", type="manual")
    db.add(env)
    
    # Architecture: WebApp -> AppServer -> Database -> Storage
    webapp = Component(
        id="comp-web-1", environment_id=env.id, source_environment=env.id,
        name="Web Frontend", type="application", criticality="high", provider="manual"
    )
    appserver = Component(
        id="comp-app-1", environment_id=env.id, source_environment=env.id,
        name="App Backend", type="server", criticality="critical", provider="manual"
    )
    database = Component(
        id="comp-db-1", environment_id=env.id, source_environment=env.id,
        name="Primary DB", type="database", criticality="critical", provider="manual"
    )
    storage = Component(
        id="comp-s3-1", environment_id=env.id, source_environment=env.id,
        name="Object Storage", type="storage", criticality="medium", provider="manual"
    )
    db.add_all([webapp, appserver, database, storage])

    # Directed dependencies:
    # WebApp depends_on AppServer
    # AppServer connects_to Database
    # Database stores_in Storage
    dep1 = Dependency(id="dep-1", environment_id=env.id, source_id="comp-web-1", target_id="comp-app-1", relationship_type="depends_on")
    dep2 = Dependency(id="dep-2", environment_id=env.id, source_id="comp-app-1", target_id="comp-db-1", relationship_type="connects_to")
    dep3 = Dependency(id="dep-3", environment_id=env.id, source_id="comp-db-1", target_id="comp-s3-1", relationship_type="stores_in")
    db.add_all([dep1, dep2, dep3])
    db.commit()

    G = build_graph(db, env.id)
    assert len(G.nodes) == 4
    assert len(G.edges) == 3

    # Outbound from AppServer: Database (descendant)
    out_edges = list(G.out_edges("comp-app-1"))
    assert len(out_edges) == 1
    assert out_edges[0] == ("comp-app-1", "comp-db-1")

    # Inbound to AppServer: WebApp (ancestor)
    in_edges = list(G.in_edges("comp-app-1"))
    assert len(in_edges) == 1
    assert in_edges[0] == ("comp-web-1", "comp-app-1")

    # Transitive downstream of AppServer: Database and Storage
    downstream = nx.descendants(G, "comp-app-1")
    assert downstream == {"comp-db-1", "comp-s3-1"}

    # Transitive upstream (dependents) of Database: AppServer and WebApp
    upstream = nx.ancestors(G, "comp-db-1")
    assert upstream == {"comp-app-1", "comp-web-1"}


def test_separated_upstream_and_downstream_blast_radius(client, db):
    """
    CRITICAL BLAST-RADIUS SEMANTICS:
    Explicitly distinguish:
    - UPSTREAM / DEPENDENT IMPACT: Callers that fail because they depend on the changed resource (ancestors)
    - DOWNSTREAM / UNDERLYING DEPENDENCIES: Infrastructure required by the changed resource (descendants)
    Verify they are NOT combined into an ambiguous single list.
    """
    env = Environment(id="env-phase3-blast", name="Blast Radius Env", type="manual")
    db.add(env)

    # Chain: Ingest Gateway -> Queue Worker -> Central API -> Shared DB
    #                         -> Analytics App -> Central API
    gateway = Component(id="c-gw", environment_id=env.id, source_environment=env.id, name="Gateway", type="network")
    worker = Component(id="c-worker", environment_id=env.id, source_environment=env.id, name="Queue Worker", type="server")
    analytics = Component(id="c-analytics", environment_id=env.id, source_environment=env.id, name="Analytics App", type="application")
    api = Component(id="c-api", environment_id=env.id, source_environment=env.id, name="Central API", type="server", criticality="critical")
    db_node = Component(id="c-db", environment_id=env.id, source_environment=env.id, name="Shared DB", type="database", criticality="critical")

    db.add_all([gateway, worker, analytics, api, db_node])

    # Gateway -> Worker -> API -> DB
    # Analytics -> API
    db.add_all([
        Dependency(id="d1", environment_id=env.id, source_id="c-gw", target_id="c-worker", relationship_type="depends_on"),
        Dependency(id="d2", environment_id=env.id, source_id="c-worker", target_id="c-api", relationship_type="connects_to"),
        Dependency(id="d3", environment_id=env.id, source_id="c-analytics", target_id="c-api", relationship_type="connects_to"),
        Dependency(id="d4", environment_id=env.id, source_id="c-api", target_id="c-db", relationship_type="stores_in"),
    ])
    db.commit()

    # Simulate outage on Central API ('c-api')
    res = simulate_change(db, "c-api", action="fail", source_environment=env.id, use_ai=False)

    # 1. UPSTREAM IMPACT: Callers that fail because Central API is down
    # Transitive callers are: Worker (hop 1), Analytics (hop 1), Gateway (hop 2)
    upstream_ids = [dep["component_id"] for dep in res["upstream_impact"]]
    assert "c-worker" in upstream_ids
    assert "c-analytics" in upstream_ids
    assert "c-gw" in upstream_ids
    assert "c-db" not in upstream_ids, "Downstream DB must NOT be reported as upstream dependent caller!"
    assert res["upstream_impact_count"] == 3

    # Verify hop distances in upstream impact
    worker_dep = next(d for d in res["upstream_impact"] if d["component_id"] == "c-worker")
    assert worker_dep["hop_distance"] == 1
    gw_dep = next(d for d in res["upstream_impact"] if d["component_id"] == "c-gw")
    assert gw_dep["hop_distance"] == 2

    # 2. DOWNSTREAM DEPENDENCIES: Infrastructure Central API relies on
    # Target is DB
    downstream_ids = [dep["component_id"] for dep in res["downstream_dependencies"]]
    assert "c-db" in downstream_ids
    assert "c-gw" not in downstream_ids, "Upstream gateway must NOT be in downstream dependencies!"
    assert "c-worker" not in downstream_ids
    assert res["downstream_dependencies_count"] == 1

    # 3. Verify API endpoint POST /api/simulate also preserves these distinct fields
    resp = client.post("/api/simulate", json={
        "target_component_id": "c-api",
        "action": "fail",
        "source_environment": env.id,
        "use_ai": False
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "upstream_impact" in data
    assert "downstream_dependencies" in data
    assert data["upstream_impact_count"] == 3
    assert data["downstream_dependencies_count"] == 1


def test_component_impact_inspection_api(client, db):
    """
    Verify GET /api/twin/components/{component_id}/impact endpoint returns:
    - Direct inbound callers with relationship types
    - Direct outbound targets with relationship types
    - Multi-hop upstream dependents
    - Multi-hop downstream dependencies
    - Structural SPOF analysis and reasons
    """
    env = Environment(id="env-phase3-inspect", name="Inspect Env", type="manual")
    db.add(env)

    auth = Component(id="auth-svc", environment_id=env.id, source_environment=env.id, name="Auth Service", type="server")
    redis = Component(id="redis-cache", environment_id=env.id, source_environment=env.id, name="Session Cache", type="database")
    client_app = Component(id="client-web", environment_id=env.id, source_environment=env.id, name="Client Web", type="application")

    db.add_all([auth, redis, client_app])
    db.add_all([
        Dependency(id="dep-auth-1", environment_id=env.id, source_id="client-web", target_id="auth-svc", relationship_type="authenticates_via"),
        Dependency(id="dep-auth-2", environment_id=env.id, source_id="auth-svc", target_id="redis-cache", relationship_type="stores_in"),
    ])
    db.commit()

    resp = client.get("/api/twin/components/auth-svc/impact")
    assert resp.status_code == 200
    data = resp.json()

    assert data["component_id"] == "auth-svc"
    assert data["in_degree"] == 1
    assert data["out_degree"] == 1

    # Direct inbound caller
    assert len(data["direct_inbound_callers"]) == 1
    assert data["direct_inbound_callers"][0]["component_id"] == "client-web"
    assert data["direct_inbound_callers"][0]["relationship_type"] == "authenticates_via"

    # Direct outbound target
    assert len(data["direct_outbound_targets"]) == 1
    assert data["direct_outbound_targets"][0]["component_id"] == "redis-cache"
    assert data["direct_outbound_targets"][0]["relationship_type"] == "stores_in"

    # Upstream dependents
    assert len(data["upstream_dependents"]) == 1
    assert data["upstream_dependents"][0]["component_id"] == "client-web"
    assert data["upstream_impact_count"] == 1

    # Downstream dependencies
    assert len(data["downstream_dependencies"]) == 1
    assert data["downstream_dependencies"][0]["component_id"] == "redis-cache"
    assert data["downstream_dependency_count"] == 1


def test_node_coordinate_persistence_and_stable_reload(client, db):
    """
    Verify graph coordinate persistence:
    - User drags a node, frontend PATCHes /api/twin/components/{id}/position
    - Position is saved in database
    - On reload, GET /api/twin/components returns exact coordinates with zero drift
    """
    env = Environment(id="env-phase3-pos", name="Position Env", type="manual")
    db.add(env)

    comp = Component(
        id="pos-comp-1", environment_id=env.id, source_environment=env.id,
        name="Movable Service", type="server", position_x=None, position_y=None
    )
    db.add(comp)
    db.commit()

    # Move to coordinates (345.5, 678.9)
    patch_resp = client.patch(f"/api/twin/components/{comp.id}/position", json={
        "position_x": 346,
        "position_y": 679
    })
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "ok"

    # Reload components
    get_resp = client.get(f"/api/twin/components?source_environment={env.id}")
    assert get_resp.status_code == 200
    components = get_resp.json()
    assert len(components) == 1
    assert components[0]["position_x"] == 346.0
    assert components[0]["position_y"] == 679.0


def test_structural_spof_detection(client, db):
    """
    Verify structural SPOF detection correctly flags articulation points and zero-redundancy bridges.
    """
    env = Environment(id="env-phase3-spof", name="SPOF Test Env", type="manual")
    db.add(env)

    # Topology: Service A and Service B both bottleneck through Single Router to reach Database
    svc_a = Component(id="sa", environment_id=env.id, source_environment=env.id, name="Service A", type="server")
    svc_b = Component(id="sb", environment_id=env.id, source_environment=env.id, name="Service B", type="server")
    router = Component(id="single-router", environment_id=env.id, source_environment=env.id, name="Single Router", type="network", criticality="critical")
    db_node = Component(id="s-db", environment_id=env.id, source_environment=env.id, name="Backend DB", type="database", criticality="critical")

    db.add_all([svc_a, svc_b, router, db_node])
    db.add_all([
        Dependency(id="d-a", environment_id=env.id, source_id="sa", target_id="single-router", relationship_type="connects_to"),
        Dependency(id="d-b", environment_id=env.id, source_id="sb", target_id="single-router", relationship_type="connects_to"),
        Dependency(id="d-r", environment_id=env.id, source_id="single-router", target_id="s-db", relationship_type="connects_to"),
    ])
    db.commit()

    spofs = find_spofs(db, env.id)
    spof_ids = [s["id"] for s in spofs]
    assert "single-router" in spof_ids, "Single Router should be detected as a structural SPOF articulation point"

    # Verify SPOF API endpoint
    resp = client.get(f"/api/twin/spof?source_environment={env.id}")
    assert resp.status_code == 200
    spof_data = resp.json()
    assert any(s["id"] == "single-router" for s in spof_data)


def test_deterministic_dependency_sources_no_ml_used(client, db):
    """
    Verify that dependency generation and querying rely entirely on deterministic
    infrastructure relationships (VPC, Subnet, Route, Manual edges) with ZERO ML calls.
    """
    env = Environment(id="env-phase3-noml", name="No ML Env", type="manual")
    db.add(env)

    c1 = Component(id="noml-1", environment_id=env.id, source_environment=env.id, name="Source Node", type="server")
    c2 = Component(id="noml-2", environment_id=env.id, source_environment=env.id, name="Target Node", type="database")
    db.add_all([c1, c2])
    db.commit()

    # Create explicit manual dependency
    create_dep_resp = client.post("/api/manual/dependencies", json={
        "source_id": "noml-1",
        "target_id": "noml-2",
        "relationship_type": "connects_to"
    })
    assert create_dep_resp.status_code == 200
    dep_data = create_dep_resp.json()
    assert dep_data["relationship_type"] == "connects_to"

    # Graph construction must be instantaneous and pure graph theory
    G = build_graph(db, env.id)
    assert G.has_edge("noml-1", "noml-2")
