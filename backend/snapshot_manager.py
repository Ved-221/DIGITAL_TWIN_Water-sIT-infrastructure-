import uuid
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
import models

def create_snapshot(
    db: Session,
    environment_id: str,
    solution_info: Optional[Dict[str, Any]] = None
) -> str:
    """
    Captures a full baseline snapshot of an environment before applying mutations.
    Preserves components, dependencies, metadata, telemetry, and coordinates.
    """
    sol_info = solution_info or {}
    
    comps = db.query(models.Component).filter(models.Component.source_environment == environment_id).all()
    deps = db.query(models.Dependency).filter(models.Dependency.source_environment == environment_id).all()
    
    serialized_comps = []
    for c in comps:
        serialized_comps.append({
            "id": c.id,
            "name": c.name,
            "type": c.type,
            "environment": c.environment,
            "environment_id": c.environment_id,
            "provider": c.provider,
            "region": c.region,
            "location": c.location,
            "criticality": c.criticality,
            "owner": c.owner,
            "status": c.status,
            "cpu": c.cpu,
            "memory": c.memory,
            "cost_per_month": c.cost_per_month,
            "currency": c.currency,
            "position_x": c.position_x,
            "position_y": c.position_y,
            "metadata_col": dict(c.metadata_col or {}),
            "telemetry": dict(c.telemetry or {}),
            "source_environment": c.source_environment
        })
        
    serialized_deps = []
    for d in deps:
        serialized_deps.append({
            "id": d.id,
            "environment_id": d.environment_id,
            "source_id": d.source_id,
            "target_id": d.target_id,
            "relationship_type": d.relationship_type,
            "criticality": d.criticality,
            "source_environment": d.source_environment,
            "metadata_col": dict(d.metadata_col or {})
        })
        
    state_payload = {
        "environment_id": environment_id,
        "components": serialized_comps,
        "dependencies": serialized_deps
    }
    
    snapshot = models.SandboxSnapshot(
        id=f"snap-{uuid.uuid4().hex[:10]}",
        environment_id=environment_id,
        solution_id=sol_info.get("id") or sol_info.get("solution_id"),
        solution_name=sol_info.get("name") or sol_info.get("solution_name"),
        strategy_type=sol_info.get("strategy_type"),
        state_json=state_payload,
        status="pending"
    )
    
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot.id

def restore_snapshot(db: Session, snapshot_id: str) -> Dict[str, Any]:
    """
    Atomically restores an environment to its baseline snapshot state upon user rejection.
    """
    snapshot = db.query(models.SandboxSnapshot).filter(models.SandboxSnapshot.id == snapshot_id).first()
    if not snapshot:
        raise ValueError(f"Snapshot '{snapshot_id}' not found.")
        
    state = snapshot.state_json or {}
    env_id = snapshot.environment_id
    
    try:
        # 1. Clear current mutated state in this environment
        db.query(models.Dependency).filter(models.Dependency.source_environment == env_id).delete()
        db.query(models.Component).filter(models.Component.source_environment == env_id).delete()
        db.flush()
        
        # 2. Re-insert baseline components
        for c_data in state.get("components", []):
            db_c = models.Component(**c_data)
            db.add(db_c)
            
        # 3. Re-insert baseline dependencies
        for d_data in state.get("dependencies", []):
            db_d = models.Dependency(**d_data)
            db.add(db_d)
            
        snapshot.status = "rejected"
        db.commit()
        
        return {
            "restored": True,
            "snapshot_id": snapshot_id,
            "environment_id": env_id,
            "components_count": len(state.get("components", [])),
            "dependencies_count": len(state.get("dependencies", []))
        }
    except Exception as e:
        db.rollback()
        raise RuntimeError(f"Failed to restore snapshot {snapshot_id}: {str(e)}")

def accept_snapshot(db: Session, snapshot_id: str) -> Dict[str, Any]:
    """
    Marks a snapshot as accepted and preserves the mutated sandbox topology.
    """
    snapshot = db.query(models.SandboxSnapshot).filter(models.SandboxSnapshot.id == snapshot_id).first()
    if not snapshot:
        raise ValueError(f"Snapshot '{snapshot_id}' not found.")
        
    snapshot.status = "accepted"
    db.commit()
    return {
        "accepted": True,
        "snapshot_id": snapshot_id,
        "environment_id": snapshot.environment_id
    }
