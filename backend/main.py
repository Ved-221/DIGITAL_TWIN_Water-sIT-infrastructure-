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
def get_components(db: Session = Depends(get_db)):
    return db.query(models.Component).all()

@app.get("/api/twin/stats", response_model=schemas.TwinStats)
def get_stats(db: Session = Depends(get_db)):
    components = db.query(models.Component).all()
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
def get_dependencies(db: Session = Depends(get_db)):
    return db.query(models.Dependency).all()

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
            request.destination_env
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
