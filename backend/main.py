# pyrefly: ignore [missing-import]
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any, Union
from pydantic import ValidationError
import os
import logging
from datetime import datetime, timezone

from database import engine, Base, get_db
import models, schemas, seed, simulation, aws_collector, metrics_collector, feasibility_engine, what_if_engine, sandbox_engine
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
    try:
        models.Base.metadata.create_all(bind=db.get_bind())
    except Exception:
        pass
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

    source_env = getattr(request, "source_environment", None) or "manual"
    comp = models.Component(
        id=comp_id,
        name=request.name.strip(),
        type=request.type,
        criticality=request.criticality or models.Criticality.medium,
        environment=request.environment or models.EnvironmentEnum.cloud,
        location=request.location or "us-east-1",
        owner=request.owner or "Infrastructure Team",
        cost_per_month=float(request.cost_per_month or 0.0),
        discovery_source="manual",
        source_environment=source_env,
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
    src_id = getattr(request, "source_component_id", None) or getattr(request, "source_id", None)
    tgt_id = getattr(request, "target_component_id", None) or getattr(request, "target_id", None)

    if not src_id or not tgt_id:
        raise HTTPException(status_code=422, detail="Both source and target IDs are required.")

    if src_id == tgt_id:
        raise HTTPException(status_code=400, detail="Self-referencing dependencies (source == target) are not allowed.")

    source_comp = db.query(models.Component).filter_by(id=src_id).first()
    target_comp = db.query(models.Component).filter_by(id=tgt_id).first()
    if not source_comp or not target_comp:
        raise HTTPException(status_code=400, detail="Both source and target must be registered components.")

    src_env = getattr(source_comp, "source_environment", None) or getattr(source_comp, "environment_id", "manual")
    tgt_env = getattr(target_comp, "source_environment", None) or getattr(target_comp, "environment_id", "manual")
    if src_env != tgt_env:
        raise HTTPException(status_code=400, detail="Dependencies cannot cross across different environments. Cross-environment dependencies are not allowed.")

    if not request.source_environment or (request.source_environment == "manual" and src_env != "manual"):
        env_id = src_env
    else:
        env_id = request.source_environment

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
        source_id=src_id,
        target_id=tgt_id,
        relationship_type=request.relationship_type,
        criticality=request.criticality or models.Criticality.medium,
        source=env_id,
        discovery_source=env_id,
        source_environment=env_id,
        environment_id=env_id,
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
    Clears all manual & user-described components and dependencies without touching live AWS resources.
    """
    db.query(models.Dependency).filter(models.Dependency.source.in_(["manual", "user_description"])).delete(synchronize_session=False)
    db.query(models.Component).filter(models.Component.discovery_source.in_(["manual", "user_description"])).delete(synchronize_session=False)
    db.commit()
    return {"success": True, "message": "Cleared all manual and user-described infrastructure."}

# ==========================================
# GENERIC DIGITAL TWIN BUILDER ENDPOINTS
# ==========================================

@app.post("/api/twin/build/parse-description", response_model=schemas.ParsedDigitalTwinPreview)
def parse_twin_description(request: schemas.NaturalLanguageParseRequest):
    """
    Parses natural-language system description into a structured preview with components,
    explicit dependencies, source provenance, and ambiguity warnings.
    """
    import nl_parser
    result = nl_parser.parse_system_description(request.description, domain=request.domain or "general")
    return result

@app.post("/api/twin/build/apply", response_model=schemas.ApplyParsedTwinResponse)
def apply_parsed_twin(request: schemas.ApplyParsedTwinRequest, db: Session = Depends(get_db)):
    """
    Commits a previewed/confirmed generic digital twin into the database.
    Preserves existing graph & simulation engine compatibility.
    """
    import uuid
    from datetime import datetime, timezone
    now_str = datetime.now(timezone.utc).isoformat()

    if request.clear_existing:
        db.query(models.Dependency).filter(models.Dependency.source.in_(["user_description", "manual"])).delete(synchronize_session=False)
        db.query(models.Component).filter(models.Component.discovery_source.in_(["user_description", "manual"])).delete(synchronize_session=False)
        db.commit()

    id_map = {}
    created_components = []

    for c in request.components:
        raw_type = c.type.lower()
        matched_type = models.ComponentType.application
        for ct in models.ComponentType:
            if ct.value == raw_type or ct.name == raw_type:
                matched_type = ct
                break
        
        comp_id = f"{matched_type.value}-{uuid.uuid4().hex[:6]}"
        id_map[c.temp_id] = comp_id

        crit = models.Criticality.medium
        if c.criticality:
            for cr in models.Criticality:
                if cr.value == str(c.criticality).lower():
                    crit = cr
                    break

        meta = dict(c.metadata or {})
        if c.properties:
            meta["properties"] = c.properties
        if c.raw_mention:
            meta["raw_mention"] = c.raw_mention

        comp_record = models.Component(
            id=comp_id,
            name=c.name,
            type=matched_type,
            environment=models.EnvironmentEnum.cloud,
            location="generic-dc-1",
            criticality=crit,
            owner="User Defined",
            status=models.Status.active,
            cpu=c.properties.get("cpu") if isinstance(c.properties, dict) else None,
            memory=c.properties.get("memory") if isinstance(c.properties, dict) else None,
            cost_per_month=float(c.properties.get("cost_per_month", 0.0) if isinstance(c.properties, dict) else 0.0),
            discovery_source="user_description",
            source_environment="manual",
            domain=c.domain or request.domain or "general",
            properties=c.properties or {},
            metadata_col=meta,
            created_at=now_str,
            updated_at=now_str
        )
        db.add(comp_record)
        created_components.append(comp_record)

    db.commit()

    created_deps = []
    for d in request.dependencies:
        src_id = id_map.get(d.source_temp_id)
        tgt_id = id_map.get(d.target_temp_id)
        if src_id and tgt_id:
            dep_record = models.Dependency(
                id=f"dep-{uuid.uuid4().hex[:8]}",
                source_component_id=src_id,
                target_component_id=tgt_id,
                source_id=src_id,
                target_id=tgt_id,
                relationship_type=d.relationship_type or "connects_to",
                criticality=models.Criticality.medium,
                source="user_description",
                discovery_source="user_description",
                metadata_col={
                    "explicit_quote": d.explicit_quote,
                    "source": "user_description",
                    **(d.metadata or {})
                }
            )
            db.add(dep_record)
            created_deps.append(dep_record)

    state = db.query(models.TwinState).filter_by(id=1).first()
    if not state:
        state = models.TwinState(id=1)
        db.add(state)
    state.mode = "manual"
    state.discovery_status = "completed"
    state.last_sync = now_str
    db.commit()

    for comp in created_components:
        db.refresh(comp)
    for dep in created_deps:
        db.refresh(dep)

    return {
        "success": True,
        "message": f"Successfully created Generic Digital Twin with {len(created_components)} component(s) and {len(created_deps)} dependency(ies).",
        "components_count": len(created_components),
        "dependencies_count": len(created_deps),
        "components": created_components,
        "dependencies": created_deps
    }

@app.post("/api/twin/build/structured", response_model=schemas.ApplyParsedTwinResponse)
def apply_structured_twin(request: schemas.StructuredTwinBuildRequest, db: Session = Depends(get_db)):
    """
    Builds and persists a domain-neutral Digital Twin directly from structured manual/CMDB JSON.
    """
    parsed_comps = []
    for idx, c in enumerate(request.components):
        temp_id = c.get("id") or c.get("temp_id") or f"c_{idx+1}"
        parsed_comps.append(schemas.ParsedComponentPreview(
            temp_id=temp_id,
            name=c.get("name", f"Component {idx+1}"),
            type=c.get("type", "application"),
            domain=c.get("domain", request.domain or "general"),
            status=c.get("status", "active"),
            criticality=c.get("criticality", "medium"),
            properties=c.get("properties", {}),
            metrics=c.get("metrics"),
            metadata=c.get("metadata", {}),
            source=c.get("source", "manual_structured"),
            source_id=c.get("source_id") or c.get("arn"),
            raw_mention=c.get("raw_mention")
        ))

    parsed_deps = []
    for d in request.dependencies:
        src = d.get("source_component_id") or d.get("source_temp_id") or d.get("source_id") or d.get("source")
        tgt = d.get("target_component_id") or d.get("target_temp_id") or d.get("target_id") or d.get("target")
        if src and tgt:
            parsed_deps.append(schemas.ParsedDependencyPreview(
                source_temp_id=src,
                target_temp_id=tgt,
                source_name=d.get("source_name", src),
                target_name=d.get("target_name", tgt),
                relationship_type=d.get("relationship_type", "connects_to"),
                source=d.get("source", "manual_structured"),
                explicit_quote=d.get("explicit_quote"),
                metadata=d.get("metadata", {})
            ))

    apply_req = schemas.ApplyParsedTwinRequest(
        domain=request.domain,
        components=parsed_comps,
        dependencies=parsed_deps,
        clear_existing=request.clear_existing
    )
    return apply_parsed_twin(apply_req, db=db)

@app.post("/api/aws/discover", response_model=schemas.AWSSyncResponse)
def discover_aws(request: schemas.AWSSyncRequest = schemas.AWSSyncRequest(), db: Session = Depends(get_db)):
    """
    Triggers live AWS multi-resource discovery and generates the Digital Twin.
    """
    return sync_aws(request=schemas.AWSSyncRequest(mode="replace", use_synthetic=False, region=request.region), db=db)

@app.get("/api/environments", response_model=List[schemas.EnvironmentSchema])
def list_environments(db: Session = Depends(get_db)):
    envs = db.query(models.Environment).all()
    projects = db.query(models.ManualProject).all()
    
    results = []
    for env in envs:
        results.append(schemas.EnvironmentSchema(
            id=env.id,
            name=env.name,
            provider=env.provider or "aws",
            source_type=env.source_type or "aws",
            is_active=env.is_active,
            status=env.status or "connected",
            created_at=str(env.created_at) if env.created_at else None
        ))
        
    for proj in projects:
        results.append(schemas.EnvironmentSchema(
            id=proj.id,
            name=proj.name,
            provider="manual",
            source_type="manual",
            is_active=True,
            status="active",
            created_at=str(proj.created_at) if proj.created_at else None
        ))
    return results

@app.post("/api/environments", response_model=schemas.EnvironmentSchema)
def create_environment(env_in: schemas.EnvironmentCreate, db: Session = Depends(get_db)):
    new_proj = models.ManualProject(name=env_in.name)
    db.add(new_proj)
    db.commit()
    db.refresh(new_proj)
    return schemas.EnvironmentSchema(
        id=new_proj.id,
        name=new_proj.name,
        provider="manual",
        source_type="manual",
        is_active=True,
        status="active",
        created_at=str(new_proj.created_at) if new_proj.created_at else None
    )

@app.delete("/api/environments/{env_id}")
def delete_environment(env_id: str, db: Session = Depends(get_db)):
    if env_id in ["aws", "default"]:
        raise HTTPException(status_code=400, detail=f"Default environment '{env_id}' cannot be deleted. Cannot delete default AWS environment.")

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

@app.get("/api/twin/spof")
@app.get("/api/spof")
def get_spofs_endpoint(source_environment: Optional[str] = "aws", db: Session = Depends(get_db)):
    result = simulation.find_spofs(db, source_environment or "aws")
    return list(result)

@app.get("/api/twin/components", response_model=List[schemas.Component])
def get_components(source_environment: Optional[str] = None, db: Session = Depends(get_db)):
    if source_environment:
        if source_environment == "manual":
            comps = db.query(models.Component).filter(
                (models.Component.source_environment == "manual") |
                (models.Component.discovery_source.in_(["manual", "user_description"]))
            ).all()
        elif source_environment in ["manual_waters", "demo"]:
            comps = db.query(models.Component).filter(
                models.Component.source_environment.in_(["manual_waters", "demo"])
            ).all()
        elif source_environment == "aws":
            comps = db.query(models.Component).filter(
                (models.Component.source_environment == "aws") |
                (models.Component.discovery_source.in_(["aws_api", "hybrid", "aws_synthetic"]))
            ).all()
        else:
            comps = db.query(models.Component).filter(
                (models.Component.source_environment == source_environment) |
                (models.Component.environment_id == source_environment)
            ).all()
    else:
        state = db.query(models.TwinState).filter_by(id=1).first()
        mode = state.mode if state else "demo"
        if mode == "unconnected":
            comps = []
        elif mode == "manual":
            comps = db.query(models.Component).filter(
                (models.Component.source_environment == "manual") |
                (models.Component.discovery_source.in_(["manual", "user_description"]))
            ).all()
        elif mode == "live":
            comps = db.query(models.Component).filter(
                (models.Component.source_environment == "aws") |
                (models.Component.discovery_source.in_(["aws_api", "hybrid", "proposed"]))
            ).all()
        elif mode == "demo":
            comps = db.query(models.Component).filter(
                (models.Component.source_environment.in_(["manual_waters", "demo", "aws"])) |
                (models.Component.discovery_source.in_(["aws_api", "hybrid", "aws_synthetic", "proposed"]))
            ).all()
            if not comps and db.query(models.Component).filter(models.Component.source_environment == "manual_waters").count() == 0:
                seed.seed_data(db)
                comps = db.query(models.Component).filter(
                    models.Component.source_environment.in_(["manual_waters", "demo"])
                ).all()
        else:
            if db.query(models.Component).filter(models.Component.source_environment == "manual_waters").count() == 0:
                seed.seed_data(db)
            comps = db.query(models.Component).all()

    for c in comps:
        if not getattr(c, "environment", None):
            c.environment = models.Environment.cloud
        if not getattr(c, "criticality", None):
            c.criticality = models.Criticality.medium
        if not getattr(c, "type", None):
            c.type = models.ComponentType.server
    return comps

@app.get("/api/twin/stats", response_model=schemas.TwinStats)
def get_stats(source_environment: Optional[str] = None, db: Session = Depends(get_db)):
    components = get_components(source_environment=source_environment, db=db)
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
        "currency": "USD"
    }

@app.get("/api/twin/dependencies", response_model=List[schemas.Dependency])
def get_dependencies(source_environment: Optional[str] = None, db: Session = Depends(get_db)):
    if source_environment:
        if source_environment == "manual":
            return db.query(models.Dependency).filter(
                (models.Dependency.source_environment == "manual") |
                (models.Dependency.source.in_(["manual", "user_description"])) |
                (models.Dependency.discovery_source.in_(["manual", "user_description"]))
            ).all()
        elif source_environment in ["manual_waters", "demo"]:
            return db.query(models.Dependency).filter(
                models.Dependency.source_environment.in_(["manual_waters", "demo"])
            ).all()
        elif source_environment == "aws":
            return db.query(models.Dependency).filter(
                (models.Dependency.source_environment == "aws") |
                (models.Dependency.discovery_source.in_(["aws_api", "hybrid", "aws_synthetic"]))
            ).all()
        else:
            return db.query(models.Dependency).filter(
                (models.Dependency.source_environment == source_environment) |
                (models.Dependency.environment_id == source_environment)
            ).all()
    state = db.query(models.TwinState).filter_by(id=1).first()
    mode = state.mode if state else "demo"
    if mode == "unconnected":
        return []
    elif mode == "manual":
        return db.query(models.Dependency).filter(
            (models.Dependency.source_environment == "manual") |
            (models.Dependency.source.in_(["manual", "user_description"])) |
            (models.Dependency.discovery_source.in_(["manual", "user_description"]))
        ).all()
    elif mode == "live":
        return db.query(models.Dependency).filter(
            (models.Dependency.source_environment == "aws") |
            (models.Dependency.discovery_source.in_(["aws_api", "hybrid"]))
        ).all()
    elif mode == "demo":
        return db.query(models.Dependency).filter(
            (models.Dependency.source_environment.in_(["manual_waters", "demo", "aws"])) |
            (models.Dependency.source.in_(["aws_api", "hybrid", "aws_synthetic", "proposed"]))
        ).all()
    return db.query(models.Dependency).all()

@app.get("/api/twin/components/{component_id}/impact")
def get_component_impact(component_id: str, db: Session = Depends(get_db)):
    comp = db.query(models.Component).filter(models.Component.id == component_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Component not found")
    
    env_id = comp.source_environment or "aws"
    G = simulation.build_graph(db, env_id)
    if component_id not in G:
        raise HTTPException(status_code=404, detail="Component not found in graph")
        
    in_edges = list(G.in_edges(component_id, data=True))
    out_edges = list(G.out_edges(component_id, data=True))
    
    direct_inbound = [
        {"component_id": u, "relationship_type": data.get("relationship_type", "depends_on")}
        for u, _, data in in_edges
    ]
    direct_outbound = [
        {"component_id": v, "relationship_type": data.get("relationship_type", "connects_to")}
        for _, v, data in out_edges
    ]
    
    import networkx as nx
    upstream_nodes = nx.ancestors(G, component_id)
    downstream_nodes = nx.descendants(G, component_id)
    
    upstream_dependents = [{"component_id": nid} for nid in upstream_nodes]
    downstream_dependencies = [{"component_id": nid} for nid in downstream_nodes]
    
    spof_result = simulation.find_spofs(db, env_id)
    spofs_list = getattr(spof_result, "spofs", None) or getattr(spof_result, "spof_nodes", None) or list(spof_result)
    is_spof = any((s.get("id") if isinstance(s, dict) else s) == component_id for s in spofs_list)
    
    return {
        "component_id": component_id,
        "name": comp.name,
        "in_degree": len(in_edges),
        "out_degree": len(out_edges),
        "direct_inbound_callers": direct_inbound,
        "direct_outbound_targets": direct_outbound,
        "upstream_dependents": upstream_dependents,
        "upstream_impact_count": len(upstream_dependents),
        "downstream_dependencies": downstream_dependencies,
        "downstream_dependency_count": len(downstream_dependencies),
        "is_spof": is_spof,
        "spof_reasons": ["Articulation point / single path bottleneck"] if is_spof else []
    }

@app.patch("/api/twin/components/{component_id}/position")
def update_component_position(component_id: str, req: schemas.ComponentPositionUpdate, db: Session = Depends(get_db)):
    comp = db.query(models.Component).filter(models.Component.id == component_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Component not found")
    comp.position_x = req.position_x
    comp.position_y = req.position_y
    db.commit()
    return {"status": "ok", "component_id": component_id, "position_x": req.position_x, "position_y": req.position_y}

@app.get("/api/twin/simulations")
@app.get("/api/simulations")
def list_simulations(source_environment: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(models.Simulation)
    if source_environment:
        query = query.filter((models.Simulation.source_environment == source_environment) | (models.Simulation.environment_id == source_environment))
    sims = query.order_by(models.Simulation.created_at.desc()).all()
    return [
        {
            "id": s.id,
            "target_component_id": s.target_component_id,
            "action": s.action,
            "source_environment": s.source_environment,
            "destination_env": s.destination_env,
            "risk_score": s.risk_score,
            "risk_level": s.risk_level,
            "estimated_downtime_minutes": s.estimated_downtime_minutes,
            "cost_delta_monthly": s.cost_delta_monthly,
            "status": s.status,
            "created_at": s.created_at
        }
        for s in sims
    ]

@app.get("/api/twin/simulations/{simulation_id}")
@app.get("/api/simulations/{simulation_id}")
def get_simulation_detail(simulation_id: str, db: Session = Depends(get_db)):
    s = db.query(models.Simulation).filter(models.Simulation.id == simulation_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Simulation record not found")
    return {
        "id": s.id,
        "target_component_id": s.target_component_id,
        "action": s.action,
        "source_environment": s.source_environment,
        "destination_env": s.destination_env,
        "affected_components": s.affected_components,
        "risk_score": s.risk_score,
        "risk_level": s.risk_level,
        "estimated_downtime_minutes": s.estimated_downtime_minutes,
        "cost_delta_monthly": s.cost_delta_monthly,
        "status": s.status,
        "created_at": s.created_at
    }


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

def run_simulation_common(request: schemas.SimulationRequest, db: Session):
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

    use_ai_flag = bool(getattr(request, "use_ai", False) or getattr(request, "use_ml_recommendation", False))
    return simulation.simulate_change(
        db=db, 
        target_component_id=target_id, 
        action=request.action or "migrate", 
        destination_env=request.destination_env,
        source_environment=source_env,
        use_ai=use_ai_flag,
        use_ml_recommendation=getattr(request, "use_ml_recommendation", False)
    )

@app.post("/api/simulate", response_model=schemas.SimulationResult)
def simulate(request: schemas.SimulationRequest, db: Session = Depends(get_db)):
    try:
        return run_simulation_common(request, db)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Simulation error: %s", str(e))
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/twin/simulate", response_model=schemas.SimulationResult)
def twin_simulate(request: schemas.SimulationRequest, db: Session = Depends(get_db)):
    try:
        result = run_simulation_common(request, db)
        if isinstance(result, dict):
            res_dict = dict(result)
            details = list(res_dict.get("affected_components_details") or [])
            detail_ids = {d.get("id") for d in details if isinstance(d, dict) and "id" in d}
            for cid in res_dict.get("affected_components", []):
                if cid not in detail_ids:
                    details.append({"id": cid, "component_id": cid, "name": str(cid)})
            res_dict["affected_components"] = details
            res_dict["affected_component_ids"] = list(result.get("affected_components", []))
            return res_dict
        elif hasattr(result, "affected_components"):
            details = list(getattr(result, "affected_components_details", []) or [])
            detail_ids = {d.get("id") for d in details if isinstance(d, dict) and "id" in d}
            for cid in getattr(result, "affected_components", []):
                if isinstance(cid, str) and cid not in detail_ids:
                    details.append({"id": cid, "component_id": cid, "name": str(cid)})
            setattr(result, "affected_components", details)
            setattr(result, "affected_component_ids", list(getattr(result, "affected_components", [])))
            return result
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Twin simulation error: %s", str(e))
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
    except ValidationError as e:
        logger.error("Feasible solutions validation error: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Feasible solution validation error: {str(e)}")
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
        if not sol_data.get("name") and sol_data.get("title"):
            sol_data["name"] = sol_data["title"]
        response = feasibility_engine.apply_feasible_solution(
            db=db,
            target_component_id=request.target_component_id,
            solution_id=request.solution_id,
            solution_data=sol_data
        )
        return response
    except ValidationError as e:
        logger.error("Apply feasible solution validation error: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Apply solution validation error: {str(e)}")
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

@app.post("/api/twin/what-if/candidates", response_model=schemas.WhatIfCandidateResponse)
def what_if_candidates(
    request: schemas.WhatIfRequest,
    db: Session = Depends(get_db)
):
    """
    Given a target component and a change type (action), generate multiple candidate
    solutions and simulate each one independently on isolated in-memory graph copies.

    The original Digital Twin is NEVER mutated. Each candidate runs on a deep-copied
    snapshot. Missing data is reported as 'unknown' — never fabricated.
    """
    try:
        result = what_if_engine.generate_what_if_candidates(
            db=db,
            target_component_id=request.target_component_id,
            action=request.action,
            source_environment=request.source_environment,
        )
        return result
    except Exception as e:
        logger.error("What-if candidates error: %s", str(e))
        raise HTTPException(status_code=400, detail=str(e))


# ─── Digital Twin Sandbox Execution Routes ───────────────────────────────────

@app.post("/api/twin/sandbox/apply", response_model=schemas.SandboxApplyResponse)
def sandbox_apply(
    request: schemas.SandboxApplyRequest,
    db: Session = Depends(get_db)
):
    """
    Applies a selected candidate solution ONLY to an isolated SANDBOX environment.
    Never mutates original Twin or live AWS infrastructure.
    Captures baseline snapshot, mutates sandbox rows in DB, rebuilds NetworkX graph,
    re-simulates, and returns structured Before vs After comparisons.
    """
    try:
        res = sandbox_engine.apply_candidate_to_sandbox(
            db=db,
            source_environment=request.source_environment,
            target_component_id=request.target_component_id,
            candidate_id=request.candidate_id,
            action=request.action,
            candidate_data=request.candidate_data,
            sandbox_env_id=request.sandbox_env_id or "sandbox"
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Sandbox apply error: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Sandbox apply error: {str(e)}")


@app.post("/api/twin/sandbox/rollback", response_model=schemas.SandboxRollbackResponse)
@app.post("/api/solutions/rollback")
def sandbox_rollback(
    request: schemas.SandboxRollbackRequest,
    db: Session = Depends(get_db)
):
    """
    Rolls back the sandbox to the baseline snapshot state.
    Restores components & dependencies in the sandbox environment.
    Keeps the original Twin and live AWS completely untouched.
    """
    try:
        env_id = request.sandbox_id or request.environment_id or "sandbox"
        res = sandbox_engine.rollback_sandbox(
            db=db,
            snapshot_id=request.snapshot_id,
            sandbox_env_id=env_id
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Sandbox rollback error: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Sandbox rollback error: {str(e)}")


@app.post("/api/twin/sandbox/accept", response_model=schemas.SandboxAcceptResponse)
@app.post("/api/solutions/accept")
def sandbox_accept(
    request: schemas.SandboxAcceptRequest,
    db: Session = Depends(get_db)
):
    """
    Accepts the mutated sandbox state and marks the snapshot as accepted.
    Keeps the mutated topology in the sandbox as the approved baseline.
    Original Twin and live AWS infrastructure remain completely unchanged.
    """
    try:
        env_id = request.sandbox_id or request.environment_id or "sandbox"
        res = sandbox_engine.accept_sandbox(
            db=db,
            snapshot_id=request.snapshot_id,
            sandbox_env_id=env_id
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Sandbox accept error: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Sandbox accept error: {str(e)}")


@app.get("/api/twin/sandbox/before-after/{snapshot_id}", response_model=schemas.SandboxBeforeAfterResponse)
def sandbox_before_after(
    snapshot_id: str,
    db: Session = Depends(get_db)
):
    """
    Retrieves Before vs After comparison and snapshot details.
    """
    try:
        return sandbox_engine.get_before_after_comparison(db, snapshot_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Sandbox before-after error: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Sandbox before-after error: {str(e)}")



if __name__ == "__main__":
    # pyrefly: ignore [missing-import]
    import uvicorn 
    uvicorn.run(app, host="0.0.0.0", port=8000)

