import uuid
from typing import List, Dict, Any, Optional, Union
import models
import schemas

def generate_applicable_candidates(
    component: Union[models.Component, Dict[str, Any]],
    simulation_result: Dict[str, Any],
    currency: str = "USD",
    include_extended: bool = False
) -> List[Dict[str, Any]]:
    """
    Generates a pool of technically applicable candidate remediation / architecture strategies
    based on component type, topological position, and simulated change impact.
    """
    comp_name = component.name if hasattr(component, "name") else component.get("name", "Component")
    comp_type = str(component.type if hasattr(component, "type") else component.get("type", "server")).lower()
    base_cost = float(component.cost_per_month if hasattr(component, "cost_per_month") else component.get("cost_per_month", 0.0) or 0.0)
    meta = (component.metadata_col if hasattr(component, "metadata_col") else component.get("metadata_col", {})) or {}
    
    action = simulation_result.get("action", "migrate").lower()
    action_clean = action.replace("_", " ").title()
    affected_count = int(simulation_result.get("affected_count", len(simulation_result.get("affected_components", []))))
    upstream_count = int(simulation_result.get("upstream_impact_count", 0))
    is_spof = simulation_result.get("risk_factors", {}).get("is_single_point_of_failure", False)
    risk_score = float(simulation_result.get("risk_score", 0.0))
    
    cost_delta = simulation_result.get("cost_delta_monthly")
    downtime_minutes = simulation_result.get("estimated_downtime_minutes")
    
    candidates = []
    
    # 1. Strategy: Direct Maintenance Window Execution (Lift-and-Shift)
    sol_lift_cost = cost_delta if cost_delta is not None else (round(base_cost * 0.15, 2) if (action == "migrate" and base_cost > 0) else 0.0)
    sol_lift_dt = downtime_minutes if downtime_minutes is not None else (25 if comp_type in ["database", "storage"] else 15)
    candidates.append({
        "id": f"opt-lift-shift-{uuid.uuid4().hex[:6]}",
        "strategy_type": "direct_lift_shift",
        "name": f"Direct Lift-and-Shift {action_clean}",
        "description": f"Standard sequential execution of '{action}' for {comp_name} during an approved service maintenance window.",
        "risk_level": "HIGH" if risk_score >= 70 else ("MODERATE" if risk_score >= 40 else "LOW"),
        "estimated_downtime_minutes": sol_lift_dt,
        "cost_delta_monthly": sol_lift_cost,
        "complexity": 1,
        "provides_redundancy": False,
        "requires_data_sync": False,
        "zero_downtime_capable": False,
        "downtime_basis": "Based on single-instance sequential cutover window" if sol_lift_dt is not None else None,
        "cost_basis": "Computed from direct instance delta" if sol_lift_cost is not None else None,
        "prerequisites": [
            f"Take point-in-time snapshot and configuration backup of {comp_name}",
            f"Notify stakeholders managing {affected_count} connected service(s)"
        ],
        "pros": [
            "Fastest operational timeline",
            "Minimal architectural reconfiguration required",
            "Preserves existing application workflows"
        ],
        "cons": [
            f"Requires service maintenance window affecting {affected_count} component(s)",
            "Retains existing single-point-of-failure exposure"
        ],
        "implementation_steps": [
            f"1. Take point-in-time configuration snapshot and backup of {comp_name}",
            f"2. Notify dependent teams managing {affected_count} connected service(s)",
            f"3. Execute '{action}' operational sequence",
            f"4. Run synthetic health verification and DNS rerouting"
        ]
    })
    
    # 2. Strategy: Phased Rollout with Parallel Standby (Blue/Green)
    sol_phased_cost = round(base_cost * 0.35, 2) if (action == "migrate" and base_cost > 0) else (round(base_cost * 0.20, 2) if base_cost > 0 else 0.0)
    candidates.append({
        "id": f"opt-phased-{uuid.uuid4().hex[:6]}",
        "strategy_type": "phased_blue_green",
        "name": f"Phased Rollout with Parallel Standby (Blue/Green)",
        "description": f"Deploy a standby shadow instance of {comp_name} in target environment with live data replication before traffic cutover.",
        "risk_level": "LOW" if risk_score < 70 else "MODERATE",
        "estimated_downtime_minutes": 2 if action == "migrate" else 0,
        "cost_delta_monthly": sol_phased_cost,
        "complexity": 2,
        "provides_redundancy": True,
        "requires_data_sync": True,
        "zero_downtime_capable": True,
        "downtime_basis": "Near-zero cutover via progressive traffic shifting",
        "cost_basis": "Includes dual-run standby capacity during transition",
        "prerequisites": [
            "Bi-directional replication sync configuration",
            "Load balancer target group support"
        ],
        "pros": [
            "Near-zero downtime cutover (<2 minutes)",
            "Instant automated fallback capability if errors detected",
            f"Guarantees SLA continuity for {affected_count} dependent system(s)"
        ],
        "cons": [
            "Temporary dual-run infrastructure cost during replication phase",
            "Requires data replication sync setup"
        ],
        "implementation_steps": [
            f"1. Provision parallel shadow instance of {comp_name}",
            "2. Establish real-time data replication and health probes",
            "3. Perform progressive traffic shifting (10% -> 50% -> 100%)",
            "4. Decommission legacy instance after soak validation"
        ]
    })
    
    # 3. Strategy: Resilient Multi-AZ Modernization
    sol_mod_cost = round(base_cost * -0.10, 2) if base_cost > 500 else (round(base_cost * 0.25, 2) if base_cost > 0 else 0.0)
    candidates.append({
        "id": f"opt-modernize-{uuid.uuid4().hex[:6]}",
        "strategy_type": "multi_az_modernize",
        "name": f"Resilient Multi-AZ Modernization",
        "description": f"Refactor {comp_name} into a multi-AZ managed cluster with automated health probes and elastic failover.",
        "risk_level": "LOW",
        "estimated_downtime_minutes": 0,
        "cost_delta_monthly": sol_mod_cost,
        "complexity": 3,
        "provides_redundancy": True,
        "requires_data_sync": False,
        "zero_downtime_capable": True,
        "downtime_basis": "Zero downtime via Multi-AZ high availability",
        "cost_basis": "Managed service baseline vs unmanaged overhead",
        "prerequisites": [
            "Multi-AZ VPC subnet availability",
            "Infrastructure-as-Code pipeline integration"
        ],
        "pros": [
            "Zero downtime architecture with multi-AZ high availability",
            "Eliminates single point of failure (SPOF)",
            "Automated scaling and reduced long-term maintenance overhead"
        ],
        "cons": [
            "Requires infrastructure-as-code updates",
            "Longer initial deployment effort"
        ],
        "implementation_steps": [
            f"1. Define multi-AZ infrastructure template for {comp_name}",
            "2. Implement automated health probes and auto-healing groups",
            f"3. Reconfigure endpoints for {affected_count} dependent service(s)",
            "4. Enable continuous metric monitoring in CloudWatch"
        ]
    })
        
    # 4. Strategy: Read Replica Offload (for Database with high callers)
    if include_extended and comp_type == "database" and upstream_count >= 2:
        candidates.append({
            "id": f"opt-replica-{uuid.uuid4().hex[:6]}",
            "strategy_type": "read_replica_offload",
            "name": f"Read Replica Query Offloading for {comp_name}",
            "description": f"Provision a read-only database replica to isolate heavy analytics and reporting queries from the primary transaction database.",
            "risk_level": "LOW",
            "estimated_downtime_minutes": 0,
            "cost_delta_monthly": round(base_cost * 0.50, 2),
            "complexity": 2,
            "provides_redundancy": True,
            "requires_data_sync": True,
            "zero_downtime_capable": True,
            "downtime_basis": "Zero downtime live replica provisioning",
            "cost_basis": "Cost of auxiliary read-replica instance",
            "prerequisites": [
                "Asynchronous database replication support",
                "Read/write split connection routing in client services"
            ],
            "pros": [
                "Reduces primary database CPU and IOPS bottlenecks",
                "Provides instantaneous read failover standby",
                "Isolates heavy analytical workloads from live user transactions"
            ],
            "cons": [
                "Slight replication lag on heavy write bursts",
                "Additional monthly compute cost for replica instance"
            ],
            "implementation_steps": [
                f"1. Provision managed Read Replica for {comp_name}",
                "2. Reconfigure connection pools on non-critical caller services",
                "3. Validate query throughput and replication lag metrics",
                "4. Enable automated promotion alarms in CloudWatch"
            ]
        })
        
    # 5. Strategy: Dependency Decoupling & Circuit Breaker
    if include_extended and upstream_count >= 2:
        candidates.append({
            "id": f"opt-circuit-{uuid.uuid4().hex[:6]}",
            "strategy_type": "dependency_circuit_breaker",
            "name": f"Asynchronous Queue & Circuit Breaker Decoupling",
            "description": f"Introduce an asynchronous message buffer (e.g. SQS/Kafka) between {upstream_count} upstream caller(s) and {comp_name} to eliminate hard dependency coupling.",
            "risk_level": "LOW",
            "estimated_downtime_minutes": 0,
            "cost_delta_monthly": 15.0,
            "complexity": 2,
            "provides_redundancy": False,
            "requires_data_sync": False,
            "zero_downtime_capable": True,
            "downtime_basis": "Zero downtime architecture change",
            "cost_basis": "Managed message queue baseline consumption",
            "prerequisites": [
                "Idempotent message handling support in consumers",
                "Dead-letter queue configuration"
            ],
            "pros": [
                f"Isolates {upstream_count} calling services from downstream outages",
                "Buffers high traffic spikes gracefully without dropping requests",
                "Reduces blast radius of target failures to near zero"
            ],
            "cons": [
                "Requires event-driven handler refactoring",
                "Eventual consistency model for processed requests"
            ],
            "implementation_steps": [
                f"1. Deploy managed message queue in front of {comp_name}",
                "2. Implement circuit-breaker retry policy in callers",
                "3. Enable Dead-Letter Queue (DLQ) for failed message handling",
                "4. Verify end-to-end telemetry and backpressure alerts"
            ]
        })
        
    return candidates
