import pytest
from tests.conftest import TestingSessionLocal, test_engine
import models
from simulation import build_graph, simulate_change, find_spofs
from migrations import run_migrations

@pytest.fixture(autouse=True)
def init_test_db():
    run_migrations(test_engine)
    db = TestingSessionLocal()
    # Clean up test tables between runs
    db.query(models.Simulation).delete()
    db.query(models.Dependency).delete()
    db.query(models.Component).delete()
    db.query(models.Environment).delete()
    db.query(models.ManualProject).delete()
    db.commit()
    db.close()

def test_environment_initialization_and_clean_slates(client):
    """
    Verify clean-slate requirements:
    1. AWS Environment exists and starts with 0 components.
    2. Manual Environment exists and starts with 0 components.
    3. Demo/Waters Environment remains isolated with demo assets.
    """
    import seed
    db = TestingSessionLocal()
    seed.seed_data(db)
    db.close()

    # AWS Environment must start empty (zero synthetic components)
    res_aws = client.get("/api/twin/components?source_environment=aws")
    assert res_aws.status_code == 200
    assert len(res_aws.json()) == 0

    # Default Manual Environment must start empty
    res_manual = client.get("/api/twin/components?source_environment=manual")
    assert res_manual.status_code == 200
    assert len(res_manual.json()) == 0

    # Demo Waters Environment remains isolated with demo resources
    res_demo = client.get("/api/twin/components?source_environment=manual_waters")
    assert res_demo.status_code == 200
    assert len(res_demo.json()) == 18

    # Verify no demo resources leaked into AWS or Manual
    aws_ids = {c["id"] for c in res_aws.json()}
    manual_ids = {c["id"] for c in res_manual.json()}
    demo_ids = {c["id"] for c in res_demo.json()}
    assert len(aws_ids.intersection(demo_ids)) == 0
    assert len(manual_ids.intersection(demo_ids)) == 0

def test_multiple_environment_component_and_dependency_isolation(client):
    """
    Test creating resources in multiple environments (env_a, env_b) and asserting
    strict isolation across component and dependency listings.
    """
    # Create components in Environment Alpha
    c_a1 = client.post("/api/manual/components", json={
        "name": "alpha-api-gateway",
        "type": "gateway",
        "environment": "cloud",
        "criticality": "high",
        "source_environment": "env_alpha"
    }).json()
    c_a2 = client.post("/api/manual/components", json={
        "name": "alpha-auth-service",
        "type": "application",
        "environment": "cloud",
        "criticality": "critical",
        "source_environment": "env_alpha"
    }).json()

    # Create dependency in Environment Alpha
    dep_a = client.post("/api/manual/dependencies", json={
        "source_id": c_a1["id"],
        "target_id": c_a2["id"],
        "relationship_type": "routes_to",
        "criticality": "high",
        "source_environment": "env_alpha"
    })
    assert dep_a.status_code == 200

    # Create components in Environment Beta
    c_b1 = client.post("/api/manual/components", json={
        "name": "beta-analytics-worker",
        "type": "application",
        "environment": "cloud",
        "criticality": "medium",
        "source_environment": "env_beta"
    }).json()
    c_b2 = client.post("/api/manual/components", json={
        "name": "beta-postgres-db",
        "type": "database",
        "environment": "cloud",
        "criticality": "critical",
        "source_environment": "env_beta"
    }).json()

    # Create dependency in Environment Beta
    dep_b = client.post("/api/manual/dependencies", json={
        "source_id": c_b1["id"],
        "target_id": c_b2["id"],
        "relationship_type": "queries",
        "criticality": "critical",
        "source_environment": "env_beta"
    })
    assert dep_b.status_code == 200

    # Verify listing env_alpha contains zero resources from env_beta
    alpha_comps = client.get("/api/twin/components?source_environment=env_alpha").json()
    alpha_comp_ids = {c["id"] for c in alpha_comps}
    assert len(alpha_comps) == 2
    assert c_a1["id"] in alpha_comp_ids
    assert c_a2["id"] in alpha_comp_ids
    assert c_b1["id"] not in alpha_comp_ids
    assert c_b2["id"] not in alpha_comp_ids

    # Verify listing env_beta contains zero resources from env_alpha
    beta_comps = client.get("/api/twin/components?source_environment=env_beta").json()
    beta_comp_ids = {c["id"] for c in beta_comps}
    assert len(beta_comps) == 2
    assert c_b1["id"] in beta_comp_ids
    assert c_b2["id"] in beta_comp_ids
    assert c_a1["id"] not in beta_comp_ids
    assert c_a2["id"] not in beta_comp_ids

    # Verify dependencies are isolated
    alpha_deps = client.get("/api/twin/dependencies?source_environment=env_alpha").json()
    assert len(alpha_deps) == 1
    assert alpha_deps[0]["source_id"] == c_a1["id"]
    assert alpha_deps[0]["target_id"] == c_a2["id"]

    beta_deps = client.get("/api/twin/dependencies?source_environment=env_beta").json()
    assert len(beta_deps) == 1
    assert beta_deps[0]["source_id"] == c_b1["id"]
    assert beta_deps[0]["target_id"] == c_b2["id"]

    # Verify AWS listing contains 0 manual resources
    aws_comps = client.get("/api/twin/components?source_environment=aws").json()
    assert len(aws_comps) == 0

def test_graph_construction_zero_cross_contamination():
    """
    Test that build_graph loaded for Environment A contains ZERO resources from Environment B.
    Even if a malicious or orphaned cross-environment dependency exists in the DB,
    build_graph must never synthesize external nodes into Environment A's graph.
    """
    db = TestingSessionLocal()
    # Create node in env_a
    c_a = models.Component(
        id="node_env_a_1",
        name="Node A1",
        type="server",
        criticality="high",
        source_environment="env_a"
    )
    # Create node in env_b
    c_b = models.Component(
        id="node_env_b_1",
        name="Node B1",
        type="database",
        criticality="critical",
        source_environment="env_b"
    )
    db.add_all([c_a, c_b])
    db.commit()

    # Manually insert cross-environment dependency into DB
    cross_dep = models.Dependency(
        id="cross_dep_1",
        source_id="node_env_a_1",
        target_id="node_env_b_1",
        relationship_type="depends_on",
        source_environment="env_a"
    )
    db.add(cross_dep)
    db.commit()

    # Build graph for env_a
    G_a = build_graph(db, "env_a")
    # Must only have node_env_a_1
    assert "node_env_a_1" in G_a.nodes
    assert "node_env_b_1" not in G_a.nodes
    assert len(G_a.nodes) == 1
    # Edge to external node must NOT be added
    assert G_a.number_of_edges() == 0

    # Build graph for env_b
    G_b = build_graph(db, "env_b")
    assert "node_env_b_1" in G_b.nodes
    assert "node_env_a_1" not in G_b.nodes
    assert len(G_b.nodes) == 1
    assert G_b.number_of_edges() == 0

    db.close()

def test_cross_environment_dependency_rejection(client):
    """Verify that attempting to create a dependency crossing different environments is rejected."""
    c_prod = client.post("/api/manual/components", json={
        "name": "prod-web",
        "type": "application",
        "source_environment": "env_prod"
    }).json()

    c_dev = client.post("/api/manual/components", json={
        "name": "dev-db",
        "type": "database",
        "source_environment": "env_dev"
    }).json()

    # Attempt to link prod to dev
    bad_dep = client.post("/api/manual/dependencies", json={
        "source_id": c_prod["id"],
        "target_id": c_dev["id"],
        "relationship_type": "queries",
        "source_environment": "env_prod"
    })
    assert bad_dep.status_code == 400
    assert "Dependencies cannot cross across different environments" in bad_dep.json()["detail"]

    # Attempt to create manual dependency in 'aws'
    aws_dep = client.post("/api/manual/dependencies", json={
        "source_id": c_prod["id"],
        "target_id": c_dev["id"],
        "relationship_type": "queries",
        "source_environment": "aws"
    })
    assert aws_dep.status_code == 400

def test_simulation_and_blast_radius_containment(client):
    """Verify simulation queries and blast radius evaluation remain strictly contained within the environment."""
    # Build a 3-tier topology in env_finance
    web = client.post("/api/manual/components", json={
        "name": "finance-frontend",
        "type": "application",
        "criticality": "high",
        "source_environment": "env_finance"
    }).json()
    api = client.post("/api/manual/components", json={
        "name": "finance-ledger-api",
        "type": "application",
        "criticality": "critical",
        "source_environment": "env_finance"
    }).json()
    db_node = client.post("/api/manual/components", json={
        "name": "finance-oracle-db",
        "type": "database",
        "criticality": "critical",
        "source_environment": "env_finance"
    }).json()

    client.post("/api/manual/dependencies", json={
        "source_id": web["id"],
        "target_id": api["id"],
        "relationship_type": "calls",
        "source_environment": "env_finance"
    })
    client.post("/api/manual/dependencies", json={
        "source_id": api["id"],
        "target_id": db_node["id"],
        "relationship_type": "queries",
        "source_environment": "env_finance"
    })

    # Create an unrelated component in env_hr
    hr_app = client.post("/api/manual/components", json={
        "name": "hr-portal",
        "type": "application",
        "criticality": "medium",
        "source_environment": "env_hr"
    }).json()

    # Simulate outage on finance-ledger-api in env_finance
    sim_res = client.post("/api/twin/simulate", json={
        "component_id": api["id"],
        "action": "fail",
        "source_environment": "env_finance"
    })
    assert sim_res.status_code == 200
    data = sim_res.json()

    # Verify blast radius contains finance nodes only
    affected_ids = {c["id"] for c in data["affected_components"]}
    assert hr_app["id"] not in affected_ids
    assert web["id"] in affected_ids or db_node["id"] in affected_ids

    # Simulating hr component inside env_finance must fail
    cross_sim = client.post("/api/twin/simulate", json={
        "component_id": hr_app["id"],
        "action": "fail",
        "source_environment": "env_finance"
    })
    assert cross_sim.status_code == 400

    # Simulation records must be scoped by environment
    fin_sims = client.get("/api/simulations?source_environment=env_finance").json()
    hr_sims = client.get("/api/simulations?source_environment=env_hr").json()
    assert len(fin_sims) == 1
    assert len(hr_sims) == 0

def test_stats_and_spof_scoping(client):
    """Verify twin stats and SPOF analysis are computed strictly for the requested environment."""
    # Create 3 components in env_x
    for i in range(3):
        client.post("/api/manual/components", json={
            "name": f"comp-x-{i}",
            "type": "server",
            "criticality": "critical" if i == 0 else "low",
            "cost_per_month": 100.0,
            "source_environment": "env_x"
        })

    # Create 1 component in env_y
    client.post("/api/manual/components", json={
        "name": "comp-y-0",
        "type": "server",
        "criticality": "low",
        "cost_per_month": 50.0,
        "source_environment": "env_y"
    })

    stats_x = client.get("/api/twin/stats?source_environment=env_x").json()
    stats_y = client.get("/api/twin/stats?source_environment=env_y").json()

    assert stats_x["total_components"] == 3
    assert stats_x["total_monthly_cost"] == 300.0
    assert stats_x["critical_services_count"] == 1

    assert stats_y["total_components"] == 1
    assert stats_y["total_monthly_cost"] == 50.0
    assert stats_y["critical_services_count"] == 0

def test_deletion_environment_scoping(client):
    """Verify deleting resources or environments does not affect other environments."""
    c1 = client.post("/api/manual/components", json={
        "name": "c1", "type": "server", "source_environment": "env_del_test"
    }).json()
    c2 = client.post("/api/manual/components", json={
        "name": "c2", "type": "server", "source_environment": "env_safe"
    }).json()

    # Delete component c1
    del_res = client.delete(f"/api/manual/components/{c1['id']}")
    assert del_res.status_code == 200

    # Ensure c2 is untouched
    safe_comps = client.get("/api/twin/components?source_environment=env_safe").json()
    assert len(safe_comps) == 1
    assert safe_comps[0]["id"] == c2["id"]

    # Deleting 'aws' default environment must be rejected
    del_aws = client.delete("/api/environments/aws")
    assert del_aws.status_code == 400
    assert "Cannot delete default AWS environment" in del_aws.json()["detail"]
