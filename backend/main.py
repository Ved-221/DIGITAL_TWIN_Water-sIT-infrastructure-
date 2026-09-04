# pyrefly: ignore [missing-import]
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import os
import logging
from datetime import datetime, timezone

from database import engine, Base, get_db
import models, schemas, seed, simulation, aws_collector, metrics_collector, feasibility_engine
from ml import recommender, trainer
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware

# Configure application logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("infratwin.api")

import database
database.init_db()

import time
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.start_time = time.time()
    app.state.last_aws_sync = None
    db = next(get_db())
    data_source = os.environ.get("INFRATWIN_DATA_SOURCE", os.environ.get("DATA_SOURCE", "unconnected")).lower()
    logger.info("Initializing InfraTwin with DATA_SOURCE=%s", data_source)

    # Ensure twin_state row exists in SQLite
    state = db.query(models.TwinState).filter_by(id=1).first()
    if not state:
        state = models.TwinState(id=1, mode="unconnected", discovery_status="idle")
        db.add(state)
        db.commit()

    if data_source == "demo":
        logger.info("Explicit demo mode requested via environment. Populating synthetic AWS environment...")
        aws_collector.sync_aws_to_db(db, mode="replace", use_synthetic=True)
        app.state.last_aws_sync = datetime.now(timezone.utc).isoformat()
    elif data_source == "aws":
        auth_status = aws_collector.check_aws_credentials()
        if auth_status["authenticated"]:
            logger.info("Syncing live AWS infrastructure on startup...")
            res = aws_collector.sync_aws_to_db(db, mode="replace")
            app.state.last_aws_sync = datetime.now(timezone.utc).isoformat()
            logger.info("AWS startup sync: %s", res.get("message"))
        else:
            logger.info("AWS credentials not configured. Starting in clean unconnected state.")
            state.mode = "unconnected"
            state.discovery_status = "idle"
            db.commit()
    else:
        # Default: clean unconnected onboarding state (NO predefined fake nodes or automatic seeding)
        logger.info("Starting InfraTwin in clean UNCONNECTED state. Awaiting user AWS connection.")
        if state.mode == "unconnected":
            # If unconnected, ensure DB has 0 components
            if db.query(models.Component).count() > 0:
                db.query(models.MetricSnapshot).delete(synchronize_session=False)
                db.query(models.Dependency).delete(synchronize_session=False)
                db.query(models.Component).delete(synchronize_session=False)
                db.commit()

    yield

app = FastAPI(title="InfraTwin API - IT Infrastructure Digital Twin", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health", response_model=schemas.HealthResponse)
def get_health(db: Session = Depends(get_db)):
    """System health check, uptime, and data layer connectivity."""
    start_t = getattr(app.state, "start_time", time.time())
    uptime = round(time.time() - start_t, 2)
    auth_info = aws_collector.check_aws_credentials()
    state = db.query(models.TwinState).filter_by(id=1).first()
    mode = state.mode if state else "unconnected"
    total_comps = db.query(models.Component).count()
    return {
        "status": "ok",
        "version": "1.0.0",
        "uptime_seconds": uptime,
        "database_connected": True,
        "total_components": total_comps,
        "aws_authenticated": auth_info["authenticated"],
        "data_source": "aws_api" if (auth_info["authenticated"] and mode == "live") else mode
    }

@app.get("/api/twin/state", response_model=schemas.TwinStateResponse)
def get_twin_state(db: Session = Depends(get_db)):
    """
    Returns current Digital Twin environment mode, discovery status, and AWS account info.
    Guarantees the frontend accurately renders the active state without assuming predefined infrastructure.
    """
    state = db.query(models.TwinState).filter_by(id=1).first()
    auth_info = aws_collector.check_aws_credentials()
    mode = state.mode if state else "unconnected"

    if mode == "manual":
        total_comps = db.query(models.Component).filter_by(discovery_source="manual").count()
        total_deps = db.query(models.Dependency).filter_by(source="manual").count()
    elif mode in ["live", "demo"]:
        total_comps = db.query(models.Component).filter(models.Component.discovery_source.in_(["aws_api", "hybrid", "aws_synthetic", "proposed"])).count()
        total_deps = db.query(models.Dependency).filter(models.Dependency.source.in_(["aws_api", "hybrid", "aws_synthetic", "proposed"])).count()
    else:
        total_comps = 0
        total_deps = 0

    if not state:
        return {
            "mode": mode,
            "authenticated": auth_info["authenticated"] if mode == "live" else False,
            "account_id": auth_info.get("account_id") if mode == "live" else None,
            "arn": auth_info.get("arn") if mode == "live" else None,
            "region": auth_info.get("region", "us-east-1") if mode == "live" else "us-east-1",
            "discovery_status": "completed" if total_comps > 0 else "idle",
            "discovery_summary": {},
            "last_sync": getattr(app.state, "last_aws_sync", None) if mode == "live" else None,
            "error": None,
            "total_components": total_comps,
            "total_dependencies": total_deps
        }

    return {
        "mode": state.mode,
        "authenticated": auth_info["authenticated"] if mode == "live" else False,
        "account_id": (state.account_id or auth_info.get("account_id")) if mode == "live" else None,
        "arn": (state.arn or auth_info.get("arn")) if mode == "live" else None,
        "region": (state.region or auth_info.get("region", "us-east-1")) if mode == "live" else "us-east-1",
        "discovery_status": state.discovery_status,
        "discovery_summary": state.discovery_summary or {},
        "last_sync": (state.last_sync or getattr(app.state, "last_aws_sync", None)) if mode == "live" else None,
        "error": state.error,
        "total_components": total_comps,
        "total_dependencies": total_deps
    }

@app.post("/api/aws/connect", response_model=schemas.AWSConnectResponse)
def connect_aws(request: schemas.AWSConnectRequest, db: Session = Depends(get_db)):
    """
    Dynamically validate and configure active AWS credentials for the Digital Twin.
    Validates identity via STS GetCallerIdentity before activating the session.
    Transitions Digital Twin to LIVE mode (Awaiting Discovery). Does NOT create premature nodes.
    Preserves any manual infrastructure safely in the database.
    """
    res = aws_collector.set_active_aws_credentials(
        access_key_id=request.access_key_id,
        secret_access_key=request.secret_access_key,
        session_token=request.session_token,
        region=request.region
    )
    if res["authenticated"]:
        # Update persistent TwinState: LIVE mode, awaiting explicit discovery
        state = db.query(models.TwinState).filter_by(id=1).first()
        if not state:
            state = models.TwinState(id=1)
            db.add(state)
        state.mode = "live"
        state.account_id = res.get("account_id")
        state.arn = res.get("arn")
        state.region = res.get("region", "us-east-1")
        state.discovery_status = "idle" # Awaiting explicit discovery click
        state.discovery_summary = {}
        state.last_sync = None
        state.error = None

        # Clean prior AWS environment data to guarantee fresh discovery without touching manual resources
        db.query(models.MetricSnapshot).delete(synchronize_session=False)
        db.query(models.Dependency).filter(models.Dependency.source != "manual").delete(synchronize_session=False)
        db.query(models.Component).filter(models.Component.discovery_source != "manual").delete(synchronize_session=False)
        db.commit()
        app.state.last_aws_sync = None

        return {
            "authenticated": True,
            "account_id": res.get("account_id"),
            "arn": res.get("arn"),
            "region": res.get("region", "us-east-1"),
            "message": f"Successfully authenticated as AWS Account {res.get('account_id')} ({res.get('arn')}). Ready for infrastructure discovery.",
            "error": None
        }
    else:
        return {
            "authenticated": False,
            "account_id": None,
            "arn": None,
            "region": request.region or "us-east-1",
            "message": "AWS Authentication failed. Please check credentials and permissions.",
            "error": res.get("error")
        }

@app.post("/api/twin/reset", response_model=schemas.TwinResetResponse)
def reset_twin_environment(db: Session = Depends(get_db)):
    """
    Resets the active Digital Twin environment to clean unconnected state.
    """
    db.query(models.MetricSnapshot).delete(synchronize_session=False)
    db.query(models.Dependency).delete(synchronize_session=False)
    db.query(models.Component).delete(synchronize_session=False)
    state = db.query(models.TwinState).filter_by(id=1).first()
    if not state:
        state = models.TwinState(id=1)
        db.add(state)
    state.mode = "unconnected"
    state.account_id = None
    state.arn = None
    state.region = "us-east-1"
    state.discovery_status = "idle"
    state.discovery_summary = {}
    state.last_sync = None
    state.error = None
    db.commit()

    aws_collector._ACTIVE_AWS_SESSION = None
    app.state.last_aws_sync = None

    return {
        "success": True,
        "message": "Digital Twin environment reset to clean unconnected state.",
        "mode": "unconnected"
    }

@app.post("/api/twin/demo", response_model=schemas.AWSSyncResponse)
def launch_demo_environment(request: schemas.TwinModeRequest = schemas.TwinModeRequest(), db: Session = Depends(get_db)):
    """
    Explicitly launches synthetic demo environment if invoked.
    """
    result = aws_collector.sync_aws_to_db(
        db=db,
        mode="replace",
        use_synthetic=True,
        region=request.region or "us-east-1"
    )
    app.state.last_aws_sync = datetime.now(timezone.utc).isoformat()
    return result

# ==========================================
# MANUAL INFRASTRUCTURE BUILDER ENDPOINTS
# ==========================================

@app.post("/api/manual/start", response_model=schemas.ManualEnvironmentResponse)
def start_manual_environment(db: Session = Depends(get_db)):
    """
    Activates the Manual Infrastructure Builder mode.
    Starts with existing manual resources or an empty canvas (0 resources).
    """
    state = db.query(models.TwinState).filter_by(id=1).first()
    if not state:
        state = models.TwinState(id=1)
        db.add(state)
    state.mode = "manual"
    state.discovery_status = "completed"
    state.error = None
    db.commit()

    total_comps = db.query(models.Component).filter_by(discovery_source="manual").count()
    total_deps = db.query(models.Dependency).filter_by(source="manual").count()

    return {
        "success": True,
        "message": "Manual Infrastructure Builder activated.",
        "mode": "manual",
        "total_components": total_comps,
        "total_dependencies": total_deps
    }

@app.post("/api/manual/activate")
def activate_manual_mode(db: Session = Depends(get_db)):
    """Switch active view back to Manual Environment."""
    state = db.query(models.TwinState).filter_by(id=1).first()
    if not state:
        state = models.TwinState(id=1)
        db.add(state)
    state.mode = "manual"
    db.commit()
    return {"success": True, "mode": "manual"}

@app.post("/api/aws/activate")
def activate_aws_mode(db: Session = Depends(get_db)):
    """Switch active view back to AWS Environment."""
    state = db.query(models.TwinState).filter_by(id=1).first()
    if not state:
        state = models.TwinState(id=1)
        db.add(state)
    state.mode = "live"
    db.commit()
    return {"success": True, "mode": "live"}

@app.post("/api/manual/components", response_model=schemas.Component)
def create_manual_component(request: schemas.ManualComponentCreate, db: Session = Depends(get_db)):
    """
    Dynamically creates and persists a manual infrastructure component.
    """
    import uuid
    comp_id = request.id.strip() if request.id and request.id.strip() else f"{request.type.value}-{uuid.uuid4().hex[:6]}"
    existing = db.query(models.Component).filter_by(id=comp_id).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Component with ID '{comp_id}' already exists.")

    meta = dict(request.metadata or {})
    if request.assumptions:
        meta["assumptions"] = request.assumptions.model_dump()

    comp = models.Component(
        id=comp_id,
        name=request.name.strip(),
        type=request.type,
        criticality=request.criticality or models.Criticality.medium,
        environment=request.environment or models.Environment.cloud,
        location=request.location or "us-east-1",
        owner=request.owner or "Infrastructure Team",
        cost_per_month=float(request.cost_per_month or 0.0),
        discovery_source="manual",
        cpu=request.assumptions.cpu if request.assumptions else None,
        memory=request.assumptions.memory if request.assumptions else None,
        metadata_col=meta,
        updated_at=datetime.now(timezone.utc).isoformat()
    )
    db.add(comp)
    db.commit()
    db.refresh(comp)
    return comp

@app.put("/api/manual/components/{component_id}", response_model=schemas.Component)
def update_manual_component(component_id: str, request: schemas.ManualComponentUpdate, db: Session = Depends(get_db)):
    """
    Updates properties of an existing manual infrastructure component.
    """
    comp = db.query(models.Component).filter_by(id=component_id, discovery_source="manual").first()
    if not comp:
        raise HTTPException(status_code=404, detail=f"Manual component '{component_id}' not found.")

    if request.name is not None:
        comp.name = request.name.strip()
    if request.type is not None:
        comp.type = request.type
    if request.criticality is not None:
        comp.criticality = request.criticality
    if request.environment is not None:
        comp.environment = request.environment
    if request.location is not None:
        comp.location = request.location
    if request.owner is not None:
        comp.owner = request.owner
    if request.cost_per_month is not None:
        comp.cost_per_month = float(request.cost_per_month)

    meta = dict(comp.metadata_col or {})
    if request.metadata is not None:
        meta.update(request.metadata)
    if request.assumptions is not None:
        meta["assumptions"] = request.assumptions.model_dump()
        comp.cpu = request.assumptions.cpu
        comp.memory = request.assumptions.memory

    comp.metadata_col = meta
    comp.updated_at = datetime.now(timezone.utc).isoformat()
    db.commit()
    db.refresh(comp)
    return comp

@app.delete("/api/manual/components/{component_id}")
def delete_manual_component(component_id: str, db: Session = Depends(get_db)):
    """
    Deletes a manual component and cleanly purges all its inbound and outbound dependency edges.
    """
    comp = db.query(models.Component).filter_by(id=component_id, discovery_source="manual").first()
    if not comp:
        raise HTTPException(status_code=404, detail=f"Manual component '{component_id}' not found.")

    # Cascading delete of all dependencies linking to or from this component
    db.query(models.Dependency).filter(
        (models.Dependency.source_component_id == component_id) |
        (models.Dependency.target_component_id == component_id) |
        (models.Dependency.source_id == component_id) |
        (models.Dependency.target_id == component_id)
    ).delete(synchronize_session=False)

    db.delete(comp)
    db.commit()
    return {"success": True, "message": f"Deleted manual component '{component_id}' and associated dependencies."}

@app.post("/api/manual/dependencies", response_model=schemas.Dependency)
def create_manual_dependency(request: schemas.ManualDependencyCreate, db: Session = Depends(get_db)):
    """
    Creates a user-defined dependency between two manual components.
    """
    import uuid
    src_id = request.source_component_id
    tgt_id = request.target_component_id

    if src_id == tgt_id:
        raise HTTPException(status_code=400, detail="Self-referencing dependencies (source == target) are not allowed.")

    source_comp = db.query(models.Component).filter_by(id=src_id, discovery_source="manual").first()
    target_comp = db.query(models.Component).filter_by(id=tgt_id, discovery_source="manual").first()
    if not source_comp or not target_comp:
        raise HTTPException(status_code=400, detail="Both source and target must be registered manual components.")

    # Deduplicate existing edge
    existing = db.query(models.Dependency).filter(
        (
            (models.Dependency.source_component_id == src_id) |
            (models.Dependency.source_id == src_id)
        ),
        (
            (models.Dependency.target_component_id == tgt_id) |
            (models.Dependency.target_id == tgt_id)
        ),
        models.Dependency.relationship_type == request.relationship_type
    ).first()
    if existing:
        return existing

    dep_id = f"dep-{uuid.uuid4().hex[:8]}"
    dep = models.Dependency(
        id=dep_id,
        source_component_id=src_id,
        target_component_id=tgt_id,
        relationship_type=request.relationship_type,
        criticality=request.criticality or models.Criticality.medium,
        source="manual",
        discovery_source="manual",
        metadata_col=request.metadata or {}
    )
    db.add(dep)
    db.commit()
    db.refresh(dep)
    return dep

@app.delete("/api/manual/dependencies/{dependency_id}")
def delete_manual_dependency(dependency_id: str, db: Session = Depends(get_db)):
    """
    Deletes a user-defined dependency edge.
    """
    dep = db.query(models.Dependency).filter_by(id=dependency_id, source="manual").first()
    if not dep:
        raise HTTPException(status_code=404, detail=f"Manual dependency '{dependency_id}' not found.")
    db.delete(dep)
    db.commit()
    return {"success": True, "message": f"Deleted manual dependency '{dependency_id}'."}

@app.post("/api/manual/clear")
def clear_manual_infrastructure(db: Session = Depends(get_db)):
    """
    Clears all manual components and dependencies without touching live AWS resources.
    """
    db.query(models.Dependency).filter_by(source="manual").delete(synchronize_session=False)
    db.query(models.Component).filter_by(discovery_source="manual").delete(synchronize_session=False)
    db.commit()
    return {"success": True, "message": "Cleared all manual infrastructure."}

@app.post("/api/aws/discover", response_model=schemas.AWSSyncResponse)
def discover_aws(request: schemas.AWSSyncRequest = schemas.AWSSyncRequest(), db: Session = Depends(get_db)):
    """
    Triggers live AWS multi-resource discovery and generates the Digital Twin.
    """
    return sync_aws(request=schemas.AWSSyncRequest(mode="replace", use_synthetic=False, region=request.region), db=db)



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
def get_components(db: Session = Depends(get_db)):
    state = db.query(models.TwinState).filter_by(id=1).first()
    if not state:
        return db.query(models.Component).all()
    mode = state.mode
    if mode == "manual":
        return db.query(models.Component).filter_by(discovery_source="manual").all()
    elif mode in ["live", "demo"]:
        return db.query(models.Component).filter(models.Component.discovery_source.in_(["aws_api", "hybrid", "aws_synthetic", "proposed"])).all()
    return []

@app.get("/api/twin/stats", response_model=schemas.TwinStats)
def get_stats(db: Session = Depends(get_db)):
    components = get_components(db=db)
    total = len(components)
    critical = sum(1 for c in components if c.criticality == "critical" or (hasattr(c.criticality, "value") and c.criticality.value == "critical"))
    cost = sum(c.cost_per_month for c in components if c.cost_per_month)
    on_prem = sum(1 for c in components if c.environment == "on_prem" or (hasattr(c.environment, "value") and c.environment.value == "on_prem"))
    cloud = sum(1 for c in components if c.environment == "cloud" or (hasattr(c.environment, "value") and c.environment.value == "cloud"))
    return {
        "total_components": total,
        "critical_services_count": critical,
        "total_monthly_cost": round(cost, 2),
        "on_prem_count": on_prem,
        "cloud_count": cloud,
        "currency": currency
    }

@app.get("/api/twin/dependencies", response_model=List[schemas.Dependency])
def get_dependencies(db: Session = Depends(get_db)):
    state = db.query(models.TwinState).filter_by(id=1).first()
    if not state:
        return db.query(models.Dependency).all()
    mode = state.mode
    if mode == "manual":
        return db.query(models.Dependency).filter_by(source="manual").all()
    elif mode in ["live", "demo"]:
        return db.query(models.Dependency).filter(models.Dependency.source.in_(["aws_api", "hybrid", "aws_synthetic", "proposed"])).all()
    return []

@app.get("/api/aws/status", response_model=schemas.AWSStatusResponse)
def get_aws_status(db: Session = Depends(get_db)):
    """Check AWS connection status, active credentials, and resource counts."""
    auth_info = aws_collector.check_aws_credentials()
    state = db.query(models.TwinState).filter_by(id=1).first()
    mode = state.mode if state else "unconnected"
    aws_comps = db.query(models.Component).filter(models.Component.arn.isnot(None)).count()
    total_comps = db.query(models.Component).count()
    return {
        "authenticated": auth_info["authenticated"],
        "account_id": state.account_id if (state and state.account_id) else auth_info.get("account_id"),
        "arn": state.arn if (state and state.arn) else auth_info.get("arn"),
        "region": state.region if (state and state.region) else auth_info.get("region", "us-east-1"),
        "configured_source": mode,
        "last_sync": state.last_sync if (state and state.last_sync) else getattr(app.state, "last_aws_sync", None),
        "aws_components_count": aws_comps,
        "total_components_count": total_comps,
        "error": auth_info.get("error")
    }

@app.get("/api/aws/cost", response_model=schemas.AWSCostReport)
def get_aws_cost_report():
    """
    Queries AWS Cost Explorer (ce:GetCostAndUsage) to report actual month-to-date
    account spending across discovered AWS services.
    """
    session = aws_collector.get_boto3_session()
    import cost_engine
    return cost_engine.get_actual_cost_and_usage(session)

@app.get("/api/aws/health-events", response_model=schemas.AWSHealthReport)
def get_aws_health_events():
    """
    Queries AWS Health (health:DescribeEvents) to report active infrastructure alerts.
    Requires global us-east-1 endpoint and AWS Business/Enterprise Support plan.
    Never fabricates fake health data.
    """
    session = aws_collector.get_boto3_session()
    return aws_collector.collect_health_events(session)

@app.post("/api/aws/sync", response_model=schemas.AWSSyncResponse)
def sync_aws(request: schemas.AWSSyncRequest = schemas.AWSSyncRequest(), db: Session = Depends(get_db)):
    """
    Trigger AWS infrastructure synchronization into the Digital Twin.
    Supports mode='merge' (preserves on-prem data) or mode='replace'.
    Supports use_synthetic=True for offline testing when credentials are not available.
    """
    result = aws_collector.sync_aws_to_db(
        db=db,
        mode=request.mode,
        use_synthetic=request.use_synthetic,
        region=request.region
    )
    if result.get("success"):
        app.state.last_aws_sync = datetime.now(timezone.utc).isoformat()
    return result

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
            target_component_id=request.target_component_id, 
            change_action=request.action, 
            destination_env=request.destination_env,
            use_ml_recommendation=request.use_ml_recommendation
        )
        return result
    except Exception as e:
        logger.error("Simulation error: %s", str(e))
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/feasible-solutions/generate", response_model=schemas.FeasibleSolutionsResponse)
def generate_feasible_solutions_endpoint(
    request: schemas.FeasibleSolutionsGenerateRequest,
    db: Session = Depends(get_db)
):
    """
    Dynamically generates candidate solutions for an identified infrastructure problem,
    evaluating each via an in-memory clone sandbox simulation against operational constraints.
    Returns only candidate options that are practically feasible.
    """
    try:
        sim_data = getattr(request, "current_simulation", None) or getattr(request, "simulation_result", None)
        response = feasibility_engine.generate_feasible_solutions(
            db=db,
            target_component_id=request.target_component_id,
            current_simulation=sim_data
        )
        return response
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Feasible solutions generation error: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Feasible solution evaluation error: {str(e)}")

@app.post("/api/feasible-solutions/apply", response_model=schemas.ApplySolutionResponse)
def apply_feasible_solution_endpoint(
    request: schemas.ApplySolutionRequest,
    db: Session = Depends(get_db)
):
    """
    Applies the chosen feasible solution to the Digital Twin model.
    In LIVE AWS mode: NEVER calls AWS APIs; updates the Digital Twin tagged as 'proposed'.
    In MANUAL mode: Updates the user-defined Digital Twin topology model.
    Returns authoritative before vs after metrics and Gemini architectural explanation.
    """
    try:
        sol_data = request.solution_data or (request.solution.model_dump() if request.solution else {})
        response = feasibility_engine.apply_feasible_solution(
            db=db,
            target_component_id=request.target_component_id,
            solution_id=request.solution_id,
            solution_data=sol_data
        )
        return response
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Apply feasible solution error: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Apply solution error: {str(e)}")

@app.get("/api/twin/metrics", response_model=List[schemas.MetricSnapshot])
@app.get("/api/twin/metrics/latest", response_model=List[schemas.MetricSnapshot])
def get_latest_metrics(db: Session = Depends(get_db)):
    """
    Returns the most recent metric snapshot for each component in the Digital Twin.
    Strictly forbids falling back to synthetic metrics in LIVE AWS mode.
    """
    from sqlalchemy import func
    subq = db.query(
        models.MetricSnapshot.resource_id,
        func.max(models.MetricSnapshot.timestamp).label("max_ts")
    ).group_by(models.MetricSnapshot.resource_id).subquery()

    latest = db.query(models.MetricSnapshot).join(
        subq,
        (models.MetricSnapshot.resource_id == subq.c.resource_id) &
        (models.MetricSnapshot.timestamp == subq.c.max_ts)
    ).all()

    if not latest:
        state = db.query(models.TwinState).filter_by(id=1).first()
        auth_info = aws_collector.check_aws_credentials()
        if state and state.mode == "demo":
            snapshots, _ = metrics_collector.collect_and_store_metrics(db, use_synthetic=True)
            return db.query(models.MetricSnapshot).all()
        elif auth_info["authenticated"]:
            # Query real CloudWatch (never synthetic)
            snapshots, _ = metrics_collector.collect_and_store_metrics(db, use_synthetic=False)
            return db.query(models.MetricSnapshot).all()
        return []

    return latest

@app.get("/api/twin/metrics/{resource_id}", response_model=List[schemas.MetricSnapshot])
def get_resource_metrics(resource_id: str, limit: int = 10, db: Session = Depends(get_db)):
    """
    Returns metric history for a specific resource, ordered by timestamp descending.
    Strictly forbids falling back to synthetic metrics in LIVE AWS mode.
    """
    snaps = db.query(models.MetricSnapshot).filter_by(resource_id=resource_id)\
        .order_by(models.MetricSnapshot.timestamp.desc()).limit(limit).all()
    if not snaps:
        comp = db.query(models.Component).filter_by(id=resource_id).first()
        if not comp:
            raise HTTPException(status_code=404, detail="Resource not found")
        state = db.query(models.TwinState).filter_by(id=1).first()
        auth_info = aws_collector.check_aws_credentials()
        if state and state.mode == "demo":
            metrics_collector.collect_and_store_metrics(db, use_synthetic=True)
            snaps = db.query(models.MetricSnapshot).filter_by(resource_id=resource_id).all()
        elif auth_info["authenticated"]:
            metrics_collector.collect_and_store_metrics(db, use_synthetic=False)
            snaps = db.query(models.MetricSnapshot).filter_by(resource_id=resource_id).all()

    return snaps

@app.get("/api/metrics/{resource_id}", response_model=List[schemas.MetricSnapshot])
def get_metrics_standard_alias(resource_id: str, limit: int = 10, db: Session = Depends(get_db)):
    """Standard endpoint alias: returns metric history for a specific resource."""
    return get_resource_metrics(resource_id=resource_id, limit=limit, db=db)

@app.post("/api/twin/metrics/collect", response_model=schemas.MetricsCollectResponse)
def trigger_metrics_collection(
    request: schemas.MetricsCollectRequest = schemas.MetricsCollectRequest(),
    db: Session = Depends(get_db)
):
    """
    Triggers an infrastructure performance metrics collection run (via CloudWatch or synthetic).
    """
    snapshots, data_source = metrics_collector.collect_and_store_metrics(
        db=db,
        use_synthetic=request.use_synthetic,
        period_seconds=request.period_seconds,
        region=request.region
    )
    now_str = datetime.now(timezone.utc).isoformat()
    return {
        "success": True,
        "message": f"Successfully collected {len(snapshots)} resource metrics.",
        "data_source": data_source,
        "timestamp": now_str,
        "metrics_collected": len(snapshots),
        "snapshots": snapshots
    }

# ML Recommendation Engine Endpoints
@app.get("/api/ml/recommend/{resource_id}", response_model=schemas.MLRecommendation)
def get_resource_recommendation(resource_id: str, db: Session = Depends(get_db)):
    """
    Predicts the recommended operational action for a specific infrastructure component
    using the trained Random Forest model.
    """
    try:
        rec = recommender.predict_component_action(resource_id, db)
        return rec
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Error generating recommendation for %s: %s", resource_id, str(e))
        raise HTTPException(status_code=500, detail=f"ML inference error: {str(e)}")

@app.get("/api/recommendations/{resource_id}", response_model=schemas.MLRecommendation)
def get_recommendation_standard_alias(resource_id: str, db: Session = Depends(get_db)):
    """Standard endpoint alias: predicts recommendation for resource."""
    return get_resource_recommendation(resource_id=resource_id, db=db)

@app.get("/api/ml/recommendations", response_model=List[schemas.MLRecommendation])
def get_all_recommendations(db: Session = Depends(get_db)):
    """
    Generates operational recommendations across all active infrastructure components.
    """
    try:
        recs = recommender.predict_all_components(db)
        return recs
    except Exception as e:
        logger.error("Error generating recommendations: %s", str(e))
        raise HTTPException(status_code=500, detail=f"ML inference error: {str(e)}")

@app.post("/api/ml/train", response_model=schemas.MLTrainResponse)
def train_recommendation_model(samples_per_class: int = 250):
    """
    Retrains the RandomForest recommendation model on the SRE policy telemetry dataset
    and reports held-out test evaluation metrics.
    """
    try:
        _, metadata = trainer.train_and_evaluate(num_samples_per_class=samples_per_class)
        recommender.reload_recommender_model()
        return {
            "success": True,
            "message": "Model successfully trained, evaluated on held-out test split, and persisted.",
            "model_type": metadata["model_type"],
            "trained_at": metadata["trained_at"],
            "n_samples_total": metadata["n_samples_total"],
            "validation_macro_f1": metadata["validation_macro_f1"],
            "test_accuracy": metadata["test_accuracy"],
            "test_macro_f1": metadata["test_macro_f1"],
            "top_features": metadata.get("top_feature_importances", [])
        }
    except Exception as e:
        logger.error("Error during model training: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Training error: {str(e)}")

@app.get("/api/ml/model/status", response_model=schemas.MLModelStatus)
def get_model_status():
    """
    Returns current model training status, test macro F1 score, accuracy, and top feature importances.
    """
    try:
        _, metadata = recommender.get_recommender_model()
        return {
            "is_trained": True,
            "model_type": metadata.get("model_type", "RandomForestClassifier"),
            "trained_at": metadata.get("trained_at"),
            "test_macro_f1": metadata.get("test_macro_f1"),
            "test_accuracy": metadata.get("test_accuracy"),
            "classes": metadata.get("classes", []),
            "top_features": metadata.get("top_feature_importances", [])
        }
    except Exception as e:
        return {
            "is_trained": False,
            "model_type": "None",
            "top_features": []
        }

if __name__ == "__main__":
    # pyrefly: ignore [missing-import]
    import uvicorn 
    uvicorn.run(app, host="0.0.0.0", port=8000)

