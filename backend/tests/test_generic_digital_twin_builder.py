import pytest
from main import app
import models
from database import get_db

def test_parse_natural_language_description(client):
    """
    Test parsing: "Two application servers are behind a load balancer. Both connect to PostgreSQL. PostgreSQL has an object-storage backup."
    """
    text = "Two application servers are behind a load balancer. Both connect to PostgreSQL. PostgreSQL has an object-storage backup."
    res = client.post("/api/twin/build/parse-description", json={"description": text, "domain": "general"})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["source"] == "user_description"
    assert len(data["components"]) == 5
    
    comp_names = [c["name"].lower() for c in data["components"]]
    assert "load balancer" in comp_names
    assert "application server 1" in comp_names
    assert "application server 2" in comp_names
    assert "postgresql" in comp_names
    assert "object-storage" in comp_names or "object storage" in comp_names

    # Check dependencies: exactly 5 dependencies
    deps = data["dependencies"]
    assert len(deps) == 5

    # Check zero hallucinations & explicit quotes
    for d in deps:
        assert d["source"] == "user_description"
        assert d["explicit_quote"] is not None
        assert len(d["explicit_quote"]) > 0

    assert data["ambiguities"] == []

def test_parse_ambiguous_description(client):
    """
    Test that ambiguous statements with 'might connect' or 'or' are flagged and not created.
    """
    text = "Two application servers are behind a load balancer. They might connect to Redis or Memcached."
    res = client.post("/api/twin/build/parse-description", json={"description": text, "domain": "general"})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    # Ambiguities must be populated
    assert len(data["ambiguities"]) >= 1
    # No Redis or Memcached edges created
    dep_targets = [d["target_name"].lower() for d in data["dependencies"]]
    assert "redis" not in dep_targets
    assert "memcached" not in dep_targets

def test_apply_parsed_digital_twin_and_simulate(client):
    """
    Test end-to-end: Parse description -> Apply/Commit to DB -> Query graph -> Run What-If simulation.
    """
    text = "Two application servers are behind a load balancer. Both connect to PostgreSQL. PostgreSQL has an object-storage backup."
    parse_res = client.post("/api/twin/build/parse-description", json={"description": text, "domain": "it_infrastructure"})
    assert parse_res.status_code == 200
    preview = parse_res.json()

    # Apply parsed twin
    apply_res = client.post("/api/twin/build/apply", json={
        "domain": "it_infrastructure",
        "components": preview["components"],
        "dependencies": preview["dependencies"],
        "clear_existing": True
    })
    assert apply_res.status_code == 200
    apply_data = apply_res.json()
    assert apply_data["success"] is True
    assert apply_data["components_count"] == 5
    assert apply_data["dependencies_count"] == 5

    # Verify components endpoint
    comps_res = client.get("/api/twin/components")
    assert comps_res.status_code == 200
    comps = comps_res.json()
    assert len(comps) == 5
    for c in comps:
        assert c["discovery_source"] == "user_description"
        assert c["domain"] == "it_infrastructure"
        # No fake cost or telemetry invented
        assert c["cpu"] is None

    # Verify dependencies endpoint
    deps_res = client.get("/api/twin/dependencies")
    assert deps_res.status_code == 200
    deps = deps_res.json()
    assert len(deps) == 5
    for d in deps:
        assert d["source"] == "user_description"

    # Find PostgreSQL node and run What-If simulation
    pg_comp = next((c for c in comps if "postgres" in c["name"].lower()), None)
    assert pg_comp is not None

    sim_res = client.post("/api/simulate", json={
        "target_component_id": pg_comp["id"],
        "action": "migrate",
        "destination_env": "cloud"
    })
    assert sim_res.status_code == 200
    sim_data = sim_res.json()
    assert sim_data["target_component_id"] == pg_comp["id"]
    # Blast radius should include upstream app servers & downstream storage
    assert sim_data["blast_radius"] >= 2
    assert "ai_explanation" in sim_data

def test_apply_structured_twin(client):
    """
    Test applying structured manual/CMDB JSON directly.
    """
    payload = {
        "domain": "health_tech",
        "components": [
            {"id": "hplc-1", "name": "HPLC Instrument Gateway", "type": "server", "criticality": "high"},
            {"id": "empower-app", "name": "Empower Chromatography Server", "type": "application", "criticality": "critical"},
            {"id": "oracle-db", "name": "Oracle Chromatography DB", "type": "database", "criticality": "critical"}
        ],
        "dependencies": [
            {"source_component_id": "hplc-1", "target_component_id": "empower-app", "relationship_type": "connects_to"},
            {"source_component_id": "empower-app", "target_component_id": "oracle-db", "relationship_type": "database_connection"}
        ],
        "clear_existing": True
    }
    res = client.post("/api/twin/build/structured", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["components_count"] == 3
    assert data["dependencies_count"] == 2
