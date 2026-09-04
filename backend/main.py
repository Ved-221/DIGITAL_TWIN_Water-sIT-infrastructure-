from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from database import engine, Base, get_db
import models, schemas, seed, simulation
from fastapi.middleware.cors import CORSMiddleware

Base.metadata.create_all(bind=engine)

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
    db = next(get_db())
    seed.seed_data(db)

@app.get("/api/twin/components", response_model=List[schemas.Component])
def get_components(source_environment: str = "aws", db: Session = Depends(get_db)):
    if source_environment.startswith("aws_sim_"):
        aws_comps = db.query(models.Component).filter(models.Component.source_environment == "aws").all()
        sim_comps = db.query(models.Component).filter(models.Component.source_environment == source_environment).all()
        return aws_comps + sim_comps
    return db.query(models.Component).filter(models.Component.source_environment == source_environment).all()

@app.get("/api/twin/stats", response_model=schemas.TwinStats)
def get_stats(source_environment: str = "aws", db: Session = Depends(get_db)):
    if source_environment.startswith("aws_sim_"):
        aws_comps = db.query(models.Component).filter(models.Component.source_environment == "aws").all()
        sim_comps = db.query(models.Component).filter(models.Component.source_environment == source_environment).all()
        components = aws_comps + sim_comps
    else:
        components = db.query(models.Component).filter(models.Component.source_environment == source_environment).all()
    total = len(components)
    critical = sum(1 for c in components if c.criticality == "critical")
    cost = sum(c.cost_per_month for c in components if c.cost_per_month)
    on_prem = sum(1 for c in components if c.environment == "on_prem")
    cloud = sum(1 for c in components if c.environment == "cloud")
    return {
        "total_components": total,
        "critical_services_count": critical,
        "total_monthly_cost": cost,
        "on_prem_count": on_prem,
        "cloud_count": cloud
    }

@app.get("/api/twin/dependencies", response_model=List[schemas.Dependency])
def get_dependencies(source_environment: str = "aws", db: Session = Depends(get_db)):
    if source_environment.startswith("aws_sim_"):
        aws_deps = db.query(models.Dependency).filter(models.Dependency.source_environment == "aws").all()
        sim_deps = db.query(models.Dependency).filter(models.Dependency.source_environment == source_environment).all()
        return aws_deps + sim_deps
    return db.query(models.Dependency).filter(models.Dependency.source_environment == source_environment).all()

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

@app.post("/api/simulate", response_model=schemas.SimulationResult)
def simulate(request: schemas.SimulationRequest, db: Session = Depends(get_db)):
    try:
        result = simulation.simulate_change(
            db, 
            request.target_component_id, 
            request.action, 
            request.destination_env,
            request.use_ai
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Manual Project Endpoints

@app.get("/api/manual/projects", response_model=List[schemas.ManualProject])
def get_manual_projects(db: Session = Depends(get_db)):
    return db.query(models.ManualProject).all()

@app.post("/api/manual/projects", response_model=schemas.ManualProject)
def create_manual_project(project: schemas.ManualProjectCreate, db: Session = Depends(get_db)):
    import datetime
    db_proj = models.ManualProject(name=project.name, created_at=datetime.datetime.utcnow().isoformat())
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
    # source_environment is taken from the payload
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
    db_dep = models.Dependency(**dependency.model_dump())
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
