from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from database import engine, Base, get_db
import models, schemas, seed, simulation, migrations
from fastapi.middleware.cors import CORSMiddleware

migrations.run_migrations(engine)

app = FastAPI(title="InfraTwin API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    migrations.run_migrations(engine)
    db = next(get_db())
    seed.seed_data(db)


@app.get("/api/environments", response_model=List[schemas.EnvironmentSchema])
def get_environments(db: Session = Depends(get_db)):
    return db.query(models.Environment).all()

@app.post("/api/environments", response_model=schemas.EnvironmentSchema)
def create_environment(env: schemas.EnvironmentCreate, db: Session = Depends(get_db)):
    db_env = models.Environment(**env.model_dump(exclude_unset=True))
    db.add(db_env)
    db.commit()
    db.refresh(db_env)
    return db_env

@app.delete("/api/environments/{env_id}")
def delete_environment(env_id: str, db: Session = Depends(get_db)):
    if env_id in ["aws", "manual"]:
        raise HTTPException(status_code=400, detail="Cannot delete default AWS environment" if env_id == "aws" else "Cannot delete default manual environment")
    
    db.query(models.Dependency).filter((models.Dependency.source_environment == env_id) | (models.Dependency.environment_id == env_id)).delete()
    db.query(models.Component).filter((models.Component.source_environment == env_id) | (models.Component.environment_id == env_id)).delete()
    db.query(models.Simulation).filter(models.Simulation.source_environment == env_id).delete()
    
    env = db.query(models.Environment).filter(models.Environment.id == env_id).first()
    if env:
        db.delete(env)
    proj = db.query(models.ManualProject).filter(models.ManualProject.id == env_id).first()
    if proj:
        db.delete(proj)
        
    db.commit()
    return {"message": f"Environment '{env_id}' deleted successfully"}

@app.get("/api/twin/components", response_model=List[schemas.Component])
def get_components(source_environment: str = "aws", db: Session = Depends(get_db)):
    if source_environment.startswith("aws_sim_"):
        aws_comps = db.query(models.Component).filter(models.Component.source_environment == "aws").all()
        sim_comps = db.query(models.Component).filter(models.Component.source_environment == source_environment).all()
        return aws_comps + sim_comps
    return db.query(models.Component).filter(models.Component.source_environment == source_environment).all()

@app.patch("/api/twin/components/{component_id}/position")
def update_component_position(component_id: str, pos: schemas.ComponentPositionUpdate, db: Session = Depends(get_db)):
    comp = db.query(models.Component).filter(models.Component.id == component_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Component not found")
    comp.position_x = pos.position_x
    comp.position_y = pos.position_y
    db.commit()
    db.refresh(comp)
    return {
        "status": "ok",
        "id": comp.id,
        "name": comp.name,
        "type": comp.type,
        "environment": comp.environment,
        "position_x": comp.position_x,
        "position_y": comp.position_y,
        "source_environment": comp.source_environment
    }

@app.get("/api/twin/stats", response_model=schemas.TwinStats)
def get_stats(source_environment: str = "aws", db: Session = Depends(get_db)):
    if source_environment.startswith("aws_sim_"):
        aws_comps = db.query(models.Component).filter(models.Component.source_environment == "aws").all()
        sim_comps = db.query(models.Component).filter(models.Component.source_environment == source_environment).all()
        components = aws_comps + sim_comps
    else:
        components = db.query(models.Component).filter(models.Component.source_environment == source_environment).all()
    total = len(components)
    critical = sum(1 for c in components if str(c.criticality).lower() == "critical")
    cost = sum(float(c.cost_per_month or 0.0) for c in components)
    on_prem = sum(1 for c in components if str(c.environment).lower() == "on_prem")
    cloud = sum(1 for c in components if str(c.environment).lower() == "cloud")
    currency = components[0].currency if components and hasattr(components[0], "currency") else "USD"
    return {
        "total_components": total,
        "critical_services_count": critical,
        "total_monthly_cost": round(cost, 2),
        "on_prem_count": on_prem,
        "cloud_count": cloud,
        "currency": currency
    }

@app.get("/api/twin/dependencies", response_model=List[schemas.Dependency])
def get_dependencies(source_environment: str = "aws", db: Session = Depends(get_db)):
    if source_environment.startswith("aws_sim_"):
        aws_deps = db.query(models.Dependency).filter(models.Dependency.source_environment == "aws").all()
        sim_deps = db.query(models.Dependency).filter(models.Dependency.source_environment == source_environment).all()
        return aws_deps + sim_deps
    return db.query(models.Dependency).filter(models.Dependency.source_environment == source_environment).all()

@app.get("/api/twin/spof")
def get_spofs(source_environment: str = "aws", db: Session = Depends(get_db)):
    return simulation.find_spofs(db, source_environment)

@app.get("/api/twin/health/{component_id}")
def get_health(component_id: str, db: Session = Depends(get_db)):
    comp = db.query(models.Component).filter(models.Component.id == component_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Component not found")
    
    try:
        import cloudwatch_service
        return cloudwatch_service.get_resource_health(comp)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@app.get("/api/twin/compliance/{component_id}")
def get_compliance(component_id: str, db: Session = Depends(get_db)):
    comp = db.query(models.Component).filter(models.Component.id == component_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Component not found")
    
    try:
        import config_rules_service
        return config_rules_service.get_resource_compliance(comp)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@app.get("/api/twin/components/{component_id}/impact")
def get_component_impact(component_id: str, db: Session = Depends(get_db)):
    comp = db.query(models.Component).filter(models.Component.id == component_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Component not found")
        
    source_env = comp.source_environment or "aws"
    G = simulation.build_graph(db, source_env)
    if component_id not in G:
        raise HTTPException(status_code=404, detail=f"Component '{component_id}' not found in graph")
        
    import networkx as nx
    in_deg = G.in_degree(component_id)
    out_deg = G.out_degree(component_id)
    
    direct_inbound = []
    for u, v, data in G.in_edges(component_id, data=True):
        direct_inbound.append({
            "component_id": u,
            "id": u,
            "name": G.nodes[u].get("name", u),
            "relationship_type": data.get("relationship_type", "depends_on"),
            "criticality": data.get("criticality", "medium")
        })
        
    direct_outbound = []
    for u, v, data in G.out_edges(component_id, data=True):
        direct_outbound.append({
            "component_id": v,
            "id": v,
            "name": G.nodes[v].get("name", v),
            "relationship_type": data.get("relationship_type", "depends_on"),
            "criticality": data.get("criticality", "medium")
        })
        
    ancestors = nx.ancestors(G, component_id)
    upstream = []
    for a in ancestors:
        try:
            hop = nx.shortest_path_length(G, source=a, target=component_id)
        except Exception:
            hop = 1
        upstream.append({
            "component_id": a,
            "id": a,
            "name": G.nodes[a].get("name", a),
            "type": G.nodes[a].get("type", "server"),
            "hop_distance": hop
        })
    upstream.sort(key=lambda x: x["hop_distance"])
    
    descendants = nx.descendants(G, component_id)
    downstream = []
    for d in descendants:
        try:
            hop = nx.shortest_path_length(G, source=component_id, target=d)
        except Exception:
            hop = 1
        downstream.append({
            "component_id": d,
            "id": d,
            "name": G.nodes[d].get("name", d),
            "type": G.nodes[d].get("type", "server"),
            "hop_distance": hop
        })
    downstream.sort(key=lambda x: x["hop_distance"])
    
    spofs = simulation.find_spofs(db, source_env)
    is_spof = any(s["id"] == component_id for s in spofs)
    
    return {
        "component_id": component_id,
        "in_degree": in_deg,
        "out_degree": out_deg,
        "direct_inbound_callers": direct_inbound,
        "direct_outbound_targets": direct_outbound,
        "upstream_dependents": upstream,
        "upstream_impact_count": len(upstream),
        "downstream_dependencies": downstream,
        "downstream_dependency_count": len(downstream),
        "is_spof": is_spof
    }

@app.post("/api/simulate", response_model=schemas.SimulationResult)
@app.post("/api/twin/simulate", response_model=schemas.SimulationResult)
def simulate(request: schemas.SimulationRequest, db: Session = Depends(get_db)):
    try:
        target_id = request.get_component_id()
        if not target_id:
            raise HTTPException(status_code=400, detail="Target component ID is required.")
            
        # Discover source environment if not given
        source_env = request.source_environment
        if not source_env:
            comp = db.query(models.Component).filter(models.Component.id == target_id).first()
            if comp and comp.source_environment:
                source_env = comp.source_environment
            else:
                source_env = "aws"

        result = simulation.simulate_change(
            db=db,
            target_component_id=target_id,
            action=request.action,
            destination_env=request.destination_env or request.target_environment,
            source_environment=source_env,
            use_ai=request.use_ai
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/ml/metadata")
def get_ml_metadata():
    from ml.inference import get_model_metadata
    return get_model_metadata()

@app.post("/api/solutions/generate")
def generate_solutions(request: schemas.SimulationRequest, db: Session = Depends(get_db)):
    try:
        import solution_generator
        target_id = request.get_component_id()
        source_env = request.source_environment or "aws"
        comp = db.query(models.Component).filter(models.Component.id == target_id).first()
        if not comp:
            raise HTTPException(status_code=404, detail="Component not found")
            
        sim_res = simulation.simulate_change(db=db, target_component_id=target_id, action=request.action, source_environment=source_env, use_ai=False)
        candidates = solution_generator.generate_applicable_candidates(component=comp, simulation_result=sim_res, currency=comp.currency or "USD")
        return {"target_component_id": target_id, "candidates_count": len(candidates), "candidates": candidates}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/solutions/rank")
def rank_solutions(request: schemas.SolutionRankRequest, db: Session = Depends(get_db)):
    try:
        from ml.inference import rank_candidate_solutions
        sim_res = request.simulation_result
        target_id = sim_res.get("target_component_id") or sim_res.get("component_id")
        comp = db.query(models.Component).filter(models.Component.id == target_id).first() if target_id else None
        candidates = request.candidate_solutions or sim_res.get("feasible_solutions", [])
        ranked = rank_candidate_solutions(simulation_result=sim_res, candidate_solutions=candidates, component_data=comp.__dict__ if comp else None)
        return {"ranked_solutions": ranked}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/solutions/apply")
def apply_solution(request: schemas.SolutionApplyRequest, db: Session = Depends(get_db)):
    try:
        import solution_applicator
        comparison = solution_applicator.apply_solution_to_sandbox(
            db=db,
            source_environment=request.source_environment,
            target_component_id=request.target_component_id,
            solution=request.solution,
            solution_id=request.solution_id,
            solution_name=request.solution_name,
            strategy_type=request.strategy_type,
            action=request.action or "migrate"
        )
        return comparison
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/solutions/accept")
def accept_solution(request: schemas.SnapshotActionRequest, db: Session = Depends(get_db)):
    try:
        import snapshot_manager
        if request.snapshot_id:
            res = snapshot_manager.accept_snapshot(db, request.snapshot_id)
            return {"message": "Architecture change accepted and persisted.", **res}
        return {"message": "Architecture change accepted."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/solutions/rollback")
def rollback_solution(request: schemas.SnapshotActionRequest, db: Session = Depends(get_db)):
    try:
        import snapshot_manager
        if not request.snapshot_id:
            raise HTTPException(status_code=400, detail="Snapshot ID is required for rollback.")
        res = snapshot_manager.restore_snapshot(db, request.snapshot_id)
        
        sim_res = None
        if request.target_component_id and res.get("environment_id"):
            sim_res = simulation.simulate_change(
                db=db,
                target_component_id=request.target_component_id,
                action=request.action or "migrate",
                source_environment=res["environment_id"],
                use_ai=False
            )
            
        return {
            "message": "Architecture change rejected. Sandbox restored to the previous state.",
            "restored": True,
            "environment_id": res.get("environment_id"),
            "components_count": res.get("components_count"),
            "dependencies_count": res.get("dependencies_count"),
            "baseline_simulation": sim_res
        }
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/twin/simulations", response_model=List[schemas.SimulationRecord])
@app.get("/api/simulations", response_model=List[schemas.SimulationRecord])
def get_simulations(source_environment: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(models.Simulation)
    if source_environment:
        query = query.filter(models.Simulation.source_environment == source_environment)
    return query.order_by(models.Simulation.created_at.desc()).all()

@app.get("/api/twin/simulations/{simulation_id}", response_model=schemas.SimulationRecord)
@app.get("/api/simulations/{simulation_id}", response_model=schemas.SimulationRecord)
def get_simulation_detail(simulation_id: str, db: Session = Depends(get_db)):
    sim = db.query(models.Simulation).filter(models.Simulation.id == simulation_id).first()
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation record not found")
    return sim

# Manual Project Endpoints

@app.get("/api/manual/projects", response_model=List[schemas.ManualProject])
def get_manual_projects(db: Session = Depends(get_db)):
    return db.query(models.ManualProject).all()

@app.post("/api/manual/projects", response_model=schemas.ManualProject)
def create_manual_project(project: schemas.ManualProjectCreate, db: Session = Depends(get_db)):
    db_proj = models.ManualProject(name=project.name)
    db.add(db_proj)
    db.commit()
    db.refresh(db_proj)
    return db_proj

@app.delete("/api/manual/projects/{project_id}")
def delete_manual_project(project_id: str, db: Session = Depends(get_db)):
    db_proj = db.query(models.ManualProject).filter(models.ManualProject.id == project_id).first()
    if not db_proj:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Delete associated components and dependencies
    db.query(models.Dependency).filter(models.Dependency.source_environment == project_id).delete()
    db.query(models.Component).filter(models.Component.source_environment == project_id).delete()
    
    db.delete(db_proj)
    db.commit()
    return {"message": "Deleted successfully"}

@app.post("/api/manual/projects/{project_id}/push-to-aws")
def push_to_aws(project_id: str, db: Session = Depends(get_db)):
    db_proj = db.query(models.ManualProject).filter(models.ManualProject.id == project_id).first()
    if not db_proj:
        raise HTTPException(status_code=404, detail="Project not found")
        
    components = db.query(models.Component).filter(models.Component.source_environment == project_id).all()
    dependencies = db.query(models.Dependency).filter(models.Dependency.source_environment == project_id).all()
    
    # Clear existing sandbox data
    db.query(models.Dependency).filter(models.Dependency.source_environment == f"aws_sim_{project_id}").delete()
    db.query(models.Component).filter(models.Component.source_environment == f"aws_sim_{project_id}").delete()
    db.commit()
    
    id_mapping = {}
    import uuid
    for comp in components:
        new_id = str(uuid.uuid4())
        id_mapping[comp.id] = new_id
        db_comp = models.Component(
            id=new_id,
            name=comp.name,
            type=comp.type,
            environment=comp.environment,
            location=comp.location,
            criticality=comp.criticality,
            owner="Planned Deployment",
            status=comp.status,
            cpu=comp.cpu,
            memory=comp.memory,
            cost_per_month=comp.cost_per_month,
            currency=comp.currency,
            position_x=comp.position_x,
            position_y=comp.position_y,
            metadata_col=comp.metadata_col,
            source_environment=f"aws_sim_{project_id}"
        )
        db.add(db_comp)
        
    for dep in dependencies:
        new_source = id_mapping.get(dep.source_id, dep.source_id)
        new_target = id_mapping.get(dep.target_id, dep.target_id)
        db_dep = models.Dependency(
            id=str(uuid.uuid4()),
            source_id=new_source,
            target_id=new_target,
            relationship_type=dep.relationship_type,
            criticality=dep.criticality,
            source_environment=f"aws_sim_{project_id}"
        )
        db.add(db_dep)
        
    db.commit()
    return {"message": "Pushed to AWS successfully", "cloned_components": len(components)}

# Manual Environment Endpoints

@app.post("/api/manual/components", response_model=schemas.Component)
def create_manual_component(component: schemas.ComponentCreate, db: Session = Depends(get_db)):
    db_comp = models.Component(**component.model_dump())
    db.add(db_comp)
    db.commit()
    db.refresh(db_comp)
    return db_comp

@app.put("/api/manual/components/{component_id}", response_model=schemas.Component)
def update_manual_component(component_id: str, component: schemas.ComponentCreate, db: Session = Depends(get_db)):
    db_comp = db.query(models.Component).filter(models.Component.id == component_id).first()
    if not db_comp or (db_comp.source_environment.startswith("aws") and db_comp.owner != "Planned Deployment"):
        raise HTTPException(status_code=404, detail="Manual component not found")
    
    update_data = component.model_dump()
    for key, value in update_data.items():
        setattr(db_comp, key, value)
    
    db.commit()
    db.refresh(db_comp)
    return db_comp

@app.delete("/api/manual/components/{component_id}")
def delete_manual_component(component_id: str, db: Session = Depends(get_db)):
    db_comp = db.query(models.Component).filter(models.Component.id == component_id).first()
    if not db_comp or (db_comp.source_environment.startswith("aws") and db_comp.owner != "Planned Deployment"):
        raise HTTPException(status_code=404, detail="Manual component not found")
    
    # Also delete related dependencies
    db.query(models.Dependency).filter((models.Dependency.source_id == component_id) | (models.Dependency.target_id == component_id)).delete()
    
    db.delete(db_comp)
    db.commit()
    return {"message": "Deleted successfully"}

@app.post("/api/manual/dependencies", response_model=schemas.Dependency)
def create_manual_dependency(dependency: schemas.DependencyCreate, db: Session = Depends(get_db)):
    if dependency.source_environment == "aws":
        raise HTTPException(status_code=400, detail="Cannot manually create dependencies in default AWS environment")
        
    src = db.query(models.Component).filter(models.Component.id == dependency.source_id).first()
    tgt = db.query(models.Component).filter(models.Component.id == dependency.target_id).first()
    
    if not src or not tgt:
        raise HTTPException(status_code=404, detail="Source or target component not found")
        
    if src.source_environment != tgt.source_environment:
        raise HTTPException(status_code=400, detail="Dependencies cannot cross across different environments")
        
    if dependency.source_environment and dependency.source_environment != src.source_environment:
        raise HTTPException(status_code=400, detail="Dependencies cannot cross across different environments")
        
    dep_data = dependency.model_dump()
    if not dep_data.get("source_environment"):
        dep_data["source_environment"] = src.source_environment
    if not dep_data.get("environment_id"):
        dep_data["environment_id"] = src.source_environment
        
    db_dep = models.Dependency(**dep_data)
    db.add(db_dep)
    db.commit()
    db.refresh(db_dep)
    return db_dep

@app.delete("/api/manual/dependencies/{dependency_id}")
def delete_manual_dependency(dependency_id: str, db: Session = Depends(get_db)):
    db_dep = db.query(models.Dependency).filter(models.Dependency.id == dependency_id).first()
    if not db_dep or db_dep.source_environment == "aws":
        raise HTTPException(status_code=404, detail="Manual dependency not found")
    
    db.delete(db_dep)
    db.commit()
    return {"message": "Deleted successfully"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

