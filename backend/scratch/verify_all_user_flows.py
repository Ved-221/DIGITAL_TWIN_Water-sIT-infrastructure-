import requests
import json
import sys

BASE = "http://localhost:8000/api"

def test_all_flows():
    print("==================================================")
    print("RUNNING COMPREHENSIVE TEST SUITE FOR USER FLOWS 1-8")
    print("==================================================")

    # ----------------------------------------------------
    # TEST 1: Fresh application startup -> empty Digital Twin
    # ----------------------------------------------------
    print("\n--- TEST 1: Fresh application startup ---")
    r = requests.post(f"{BASE}/twin/reset")
    assert r.status_code == 200, f"Reset failed: {r.text}"
    state = requests.get(f"{BASE}/twin/state").json()
    assert state["mode"] == "unconnected", f"Expected unconnected mode, got {state['mode']}"
    assert state["total_components"] == 0, f"Expected 0 components, got {state['total_components']}"
    assert state["total_dependencies"] == 0, f"Expected 0 dependencies, got {state['total_dependencies']}"
    assert state["discovery_status"] == "idle", f"Expected idle status, got {state['discovery_status']}"

    comps = requests.get(f"{BASE}/twin/components").json()
    assert len(comps) == 0, f"Expected 0 components, got {len(comps)}"
    deps = requests.get(f"{BASE}/twin/dependencies").json()
    assert len(deps) == 0, f"Expected 0 dependencies, got {len(deps)}"
    print("✓ TEST 1 PASSED: True empty Digital Twin on fresh startup (0 components, 0 dependencies, 0 sandbox transformations).")

    # ----------------------------------------------------
    # TEST 2: Build Manually -> create resources -> topology appears
    # ----------------------------------------------------
    print("\n--- TEST 2: Build Manually ---")
    r = requests.post(f"{BASE}/manual/start")
    assert r.status_code == 200, f"Manual start failed: {r.text}"
    man_state = r.json()
    assert man_state["mode"] == "manual"

    comp_payload = {
        "id": "web-server-1",
        "name": "Web Server 1",
        "type": "server",
        "criticality": "high",
        "environment": "cloud",
        "source_environment": "manual",
        "cost_per_month": 45.0,
        "metadata": {"specs": "t3.medium"}
    }
    r = requests.post(f"{BASE}/manual/components", json=comp_payload)
    assert r.status_code == 200, f"Failed to create manual component: {r.text}"
    created_comp = r.json()
    assert created_comp["id"] == "web-server-1"

    man_comps = requests.get(f"{BASE}/twin/components?source_environment=manual").json()
    assert len(man_comps) == 1, f"Expected 1 manual component, got {len(man_comps)}"
    assert man_comps[0]["id"] == "web-server-1"
    print("✓ TEST 2 PASSED: Build Manually creates resources and manual topology appears.")

    # ----------------------------------------------------
    # TEST 3: Describe & Build -> parse description -> review -> apply -> topology appears
    # ----------------------------------------------------
    print("\n--- TEST 3: Describe & Build (NLP) ---")
    nlp_desc = "Application Server connects to PostgreSQL Database. PostgreSQL Database connects to S3 Storage."
    r = requests.post(f"{BASE}/twin/build/parse-description", json={"description": nlp_desc, "domain": "cloud"})
    assert r.status_code == 200, f"NLP parse failed: {r.text}"
    parse_result = r.json()
    assert len(parse_result["components"]) >= 3, f"Expected >=3 components parsed, got {len(parse_result['components'])}"
    assert len(parse_result["dependencies"]) >= 2, f"Expected >=2 dependencies parsed, got {len(parse_result['dependencies'])}"

    r = requests.post(f"{BASE}/twin/build/apply", json={
        "domain": "cloud",
        "components": parse_result["components"],
        "dependencies": parse_result["dependencies"],
        "clear_existing": True
    })
    assert r.status_code == 200, f"Apply NLP failed: {r.text}"
    nlp_apply = r.json()
    assert nlp_apply["success"] is True
    assert nlp_apply["components_count"] >= 3

    twin_comps = requests.get(f"{BASE}/twin/components?source_environment=manual").json()
    assert len(twin_comps) >= 3, f"Expected >= 3 components, got {len(twin_comps)}"
    print(f"✓ TEST 3 PASSED: Describe & Build parsed and constructed topology with {len(twin_comps)} components.")

    # ----------------------------------------------------
    # TEST 4: Import JSON -> structured build -> topology appears
    # ----------------------------------------------------
    print("\n--- TEST 4: Import JSON (Structured Twin Build) ---")
    json_payload = {
        "domain": "cloud",
        "components": [
            {"id": "api-gw", "name": "API Gateway", "type": "api", "criticality": "high", "cost_per_month": 50.0},
            {"id": "auth-svc", "name": "Auth Service", "type": "application", "criticality": "critical", "cost_per_month": 80.0},
            {"id": "user-db", "name": "User DB", "type": "database", "criticality": "critical", "cost_per_month": 150.0}
        ],
        "dependencies": [
            {"source_id": "api-gw", "target_id": "auth-svc", "relationship_type": "calls", "criticality": "high"},
            {"source_id": "auth-svc", "target_id": "user-db", "relationship_type": "queries", "criticality": "critical"}
        ],
        "clear_existing": True
    }
    r = requests.post(f"{BASE}/twin/build/structured", json=json_payload)
    assert r.status_code == 200, f"Structured build failed: {r.text}"
    struct_res = r.json()
    assert struct_res["success"] is True
    assert struct_res["components_count"] == 3
    assert struct_res["dependencies_count"] == 2

    struct_comps = requests.get(f"{BASE}/twin/components?source_environment=manual").json()
    assert len(struct_comps) == 3
    print("✓ TEST 4 PASSED: Import JSON builds structured topology cleanly.")

    # ----------------------------------------------------
    # TEST 5: Connect AWS -> AWS discovery -> real AWS topology appears
    # ----------------------------------------------------
    print("\n--- TEST 5: Connect AWS & Discover Infrastructure ---")
    r = requests.post(f"{BASE}/aws/sync", json={"mode": "replace"})
    assert r.status_code == 200, f"AWS sync failed: {r.text}"
    aws_sync = r.json()
    assert aws_sync["success"] is True
    assert aws_sync["total_components"] > 0, "Expected discovered AWS components"
    print(f"✓ TEST 5 PASSED: AWS discovery succeeded ({aws_sync['total_components']} resources, {aws_sync['total_dependencies']} dependencies).")

    # ----------------------------------------------------
    # TEST 6: Existing Twin -> What-If -> Simulate -> Candidate Solutions -> ML/Agents -> Apply to Sandbox
    # ----------------------------------------------------
    print("\n--- TEST 6: What-If, Simulation, Three Agents & Apply to Sandbox ---")
    aws_comps = requests.get(f"{BASE}/twin/components?source_environment=aws").json()
    target_comp = aws_comps[0]["id"]
    print(f"Target component for What-If: {target_comp}")

    # Generate candidates
    cand_req = {
        "target_component_id": target_comp,
        "action": "fail",
        "source_environment": "aws",
        "domain": "cloud"
    }
    r = requests.post(f"{BASE}/twin/what-if/candidates", json=cand_req)
    assert r.status_code == 200, f"What-If candidates failed: {r.text}"
    cand_data = r.json()
    assert cand_data["success"] is True
    candidates = cand_data["candidates"]
    assert len(candidates) > 0, "Expected at least 1 candidate solution"
    print(f"Generated {len(candidates)} candidates. Ranking status: {cand_data.get('ranking_status')}")

    # Three-Agents evaluation
    selected_candidate = candidates[0]
    eval_req = {
        "candidate": selected_candidate,
        "target_component_id": target_comp,
        "baseline_summary": {
            "total_monthly_cost": 500.0,
            "overall_health_score": 75.0,
            "spof_count": 2,
            "total_components": len(aws_comps)
        },
        "ml_suggestion": {
            "recommended_action": selected_candidate.get("action", "auto"),
            "confidence_score": 0.85
        }
    }
    r = requests.post(f"{BASE}/twin/what-if/agents/evaluate", json=eval_req)
    assert r.status_code == 200, f"Agent evaluation failed: {r.text}"
    agent_eval = r.json()
    assert "financial" in agent_eval and "risk" in agent_eval and "architect" in agent_eval and "consensus" in agent_eval
    print(f"Three Agents evaluated: Consensus verdict = {agent_eval['consensus']['agreement']} on candidate {agent_eval['consensus']['candidate_id']}")

    # Apply to Sandbox
    apply_payload = {
        "source_environment": "aws",
        "target_component_id": target_comp,
        "candidate_id": selected_candidate.get("candidate_id") or selected_candidate.get("id"),
        "candidate_data": selected_candidate,
        "sandbox_env_id": "sandbox"
    }
    r = requests.post(f"{BASE}/twin/sandbox/apply", json=apply_payload)
    assert r.status_code == 200, f"Apply to sandbox failed: {r.text}"
    sb_apply = r.json()
    assert sb_apply["success"] is True
    assert sb_apply["sandbox_id"] == "sandbox"
    snapshot_id = sb_apply["snapshot_id"]
    assert snapshot_id is not None

    # Verify transformed architecture appears in sandbox ONLY
    sb_comps = requests.get(f"{BASE}/twin/components?source_environment=sandbox").json()
    assert len(sb_comps) > 0, "Expected sandbox components"
    for sc in sb_comps:
        assert sc["id"].startswith("sb-"), f"Sandbox component {sc['id']} should have sb- prefix"
    
    # Verify original AWS twin remains unchanged
    aws_comps_after = requests.get(f"{BASE}/twin/components?source_environment=aws").json()
    assert len(aws_comps_after) == len(aws_comps), "Original AWS twin must remain untouched"
    print(f"✓ TEST 6 PASSED: Solution applied to sandbox ({len(sb_comps)} transformed components in sandbox; original AWS twin untouched).")

    # ----------------------------------------------------
    # TEST 7: Sandbox -> Before/After -> Rollback -> Original Twin Intact
    # ----------------------------------------------------
    print("\n--- TEST 7: Sandbox Rollback ---")
    r = requests.post(f"{BASE}/twin/sandbox/rollback", json={
        "snapshot_id": snapshot_id,
        "sandbox_id": "sandbox"
    })
    assert r.status_code == 200, f"Rollback failed: {r.text}"
    rollback_res = r.json()
    assert rollback_res["restored"] is True
    print(f"Rollback restored: {rollback_res['components_count']} components")

    # Verify original Twin intact
    aws_comps_final = requests.get(f"{BASE}/twin/components?source_environment=aws").json()
    assert len(aws_comps_final) == len(aws_comps), "Original AWS twin must remain intact after rollback"
    print("✓ TEST 7 PASSED: Sandbox rolled back successfully, baseline intact.")

    # ----------------------------------------------------
    # TEST 8: Accept -> Transformation retained according to existing behavior
    # ----------------------------------------------------
    print("\n--- TEST 8: Apply and Accept ---")
    # Apply again
    r = requests.post(f"{BASE}/twin/sandbox/apply", json=apply_payload)
    assert r.status_code == 200
    sb_apply2 = r.json()
    snapshot_id2 = sb_apply2["snapshot_id"]

    # Accept
    r = requests.post(f"{BASE}/twin/sandbox/accept", json={
        "snapshot_id": snapshot_id2,
        "sandbox_id": "sandbox"
    })
    assert r.status_code == 200, f"Accept failed: {r.text}"
    accept_res = r.json()
    assert accept_res["accepted"] is True
    print(f"Accept status: {accept_res['status']}")
    print("✓ TEST 8 PASSED: Sandbox transformation accepted successfully.")

    # Final cleanup to leave in pristine empty state for user
    print("\n--- Final Cleanup to pristine empty state ---")
    requests.post(f"{BASE}/twin/reset")
    final_state = requests.get(f"{BASE}/twin/state").json()
    assert final_state["total_components"] == 0
    print("Digital twin reset to clean 0 components initial state.")

    print("\n==================================================")
    print("ALL 8 USER FLOW TESTS PASSED FLAWLESSLY!")
    print("==================================================")

if __name__ == "__main__":
    test_all_flows()
