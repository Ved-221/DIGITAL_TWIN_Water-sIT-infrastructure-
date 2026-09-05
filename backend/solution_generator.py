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
    Ensures that every supported What-If action generates a matching primary candidate.
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
    
    candidate_map: Dict[str, Dict[str, Any]] = {}

    # 1. Strategy: Scale Up Compute & Capacity
    sol_scale_cost = round(base_cost * 0.50, 2) if base_cost > 0 else 25.0
    candidate_map["scale_up"] = {
        "id": f"opt-scale-{uuid.uuid4().hex[:6]}",
        "strategy_type": "scale_up",
        "name": f"Scale Up Compute Capacity for {comp_name}",
        "description": f"Double CPU and RAM compute resources for {comp_name} to eliminate capacity saturation and handle peak loads.",
        "risk_level": "LOW",
        "estimated_downtime_minutes": 1,
        "cost_delta_monthly": sol_scale_cost,
        "complexity": 1,
        "provides_redundancy": False,
        "requires_data_sync": False,
        "zero_downtime_capable": True,
        "downtime_basis": "Near-zero downtime rolling capacity scale",
        "cost_basis": "50% increase over current compute instance allocation",
        "prerequisites": [
            "Compute instance type sizing availability",
            "Auto-scaling group or instance reconfiguration window"
        ],
        "pros": [
            "Instant capacity headroom increase",
            "Zero structural topology refactoring required",
            "Safeguards against high-load throttling"
        ],
        "cons": [
            "Increases monthly operational compute expenditure",
            "Does not eliminate existing Single Point of Failure (SPOF)"
        ],
        "implementation_steps": [
            f"1. Double allocated vCPUs and RAM memory parameters for {comp_name}",
            "2. Apply instance resizing / scaling policy in runtime environment",
            "3. Monitor synthetic latency and resource consumption headroom"
        ]
    }

    # 2. Strategy: Safe Decommission / Remove
    candidate_map["remove"] = {
        "id": f"opt-remove-{uuid.uuid4().hex[:6]}",
        "strategy_type": "remove",
        "name": f"Safe Decommission & Removal of {comp_name}",
        "description": f"Safely retire {comp_name}, sever incident dependency links, and reclaim unneeded compute/storage capacity.",
        "risk_level": "HIGH" if (affected_count > 0 and is_spof) else ("MODERATE" if affected_count > 0 else "LOW"),
        "estimated_downtime_minutes": 0,
        "cost_delta_monthly": -round(base_cost, 2),
        "complexity": 2,
        "provides_redundancy": False,
        "requires_data_sync": False,
        "zero_downtime_capable": True,
        "downtime_basis": "Zero operational downtime once dependency callers are detached",
        "cost_basis": f"Full elimination of baseline monthly cost (-${base_cost:,.2f})",
        "prerequisites": [
            f"Notify {affected_count} connected service owner(s)",
            f"Verify archival backup of {comp_name} data state"
        ],
        "pros": [
            f"Saves ${base_cost:,.2f}/month in infrastructure costs",
            "Eliminates operational maintenance and security attack surface",
            "Removes unneeded architectural complexity"
        ],
        "cons": [
            f"Permanently terminates {affected_count} incoming/outgoing dependency relationships",
            "Irreversible without snapshot rollback"
        ],
        "implementation_steps": [
            f"1. Drain all active traffic and caller connections to {comp_name}",
            f"2. Gracefully disconnect {affected_count} incident dependency link(s)",
            f"3. Decommission and release runtime compute resources for {comp_name}"
        ]
    }

    # 3. Strategy: Resilient Multi-AZ Modernization
    sol_mod_cost = round(base_cost * -0.10, 2) if base_cost > 500 else (round(base_cost * 0.25, 2) if base_cost > 0 else 25.0)
    candidate_map["multi_az_modernize"] = {
        "id": f"opt-modernize-{uuid.uuid4().hex[:6]}",
        "strategy_type": "multi_az_modernize",
        "name": f"Resilient Multi-AZ Modernization for {comp_name}",
        "description": f"Refactor {comp_name} into a multi-AZ managed architecture with automated health probes, standby replica, and seamless failover.",
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
            "Initial provisioning overhead for standby replica and load balancer"
        ],
        "implementation_steps": [
            f"1. Define multi-AZ infrastructure template for {comp_name}",
            "2. Implement automated health probes and auto-healing groups",
            f"3. Reconfigure endpoints for {affected_count} dependent service(s)",
            "4. Enable continuous metric monitoring in CloudWatch"
        ]
    }

    # 4. Strategy: Read Replica Offload
    sol_replica_cost = round(base_cost * 0.50, 2) if base_cost > 0 else 35.0
    candidate_map["read_replica_offload"] = {
        "id": f"opt-replica-{uuid.uuid4().hex[:6]}",
        "strategy_type": "read_replica_offload",
        "name": f"Read Replica Query Offloading for {comp_name}",
        "description": f"Provision a read-only database replica to isolate heavy analytics and reporting queries from primary {comp_name}.",
        "risk_level": "LOW",
        "estimated_downtime_minutes": 0,
        "cost_delta_monthly": sol_replica_cost,
        "complexity": 2,
        "provides_redundancy": True,
        "requires_data_sync": True,
        "zero_downtime_capable": True,
        "downtime_basis": "Zero downtime live replica provisioning",
        "cost_basis": "Cost of auxiliary read-replica compute instance",
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
    }

    # 5. Strategy: Dependency Decoupling & Circuit Breaker
    candidate_map["dependency_circuit_breaker"] = {
        "id": f"opt-circuit-{uuid.uuid4().hex[:6]}",
        "strategy_type": "dependency_circuit_breaker",
        "name": f"Asynchronous Queue & Circuit Breaker Decoupling for {comp_name}",
        "description": f"Introduce an asynchronous message buffer (e.g. SQS/Kafka) in front of {comp_name} to isolate caller services from downstream outages.",
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
            f"Isolates calling services from downstream outages",
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
    }

    # 6. Strategy: Phased Rollout with Parallel Standby (Blue/Green)
    sol_phased_cost = round(base_cost * 0.35, 2) if (action == "migrate" and base_cost > 0) else (round(base_cost * 0.20, 2) if base_cost > 0 else 0.0)
    candidate_map["phased_blue_green"] = {
        "id": f"opt-phased-{uuid.uuid4().hex[:6]}",
        "strategy_type": "phased_blue_green",
        "name": f"Phased Rollout with Parallel Standby (Blue/Green) for {comp_name}",
        "description": f"Deploy a standby shadow instance of {comp_name} with real-time data replication before performing traffic cutover.",
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
    }

    # 7. Strategy: Direct Maintenance Window Execution (Lift-and-Shift)
    sol_lift_cost = cost_delta if cost_delta is not None else (round(base_cost * 0.15, 2) if (action == "migrate" and base_cost > 0) else 0.0)
    sol_lift_dt = downtime_minutes if downtime_minutes is not None else (25 if comp_type in ["database", "storage"] else 15)
    candidate_map["direct_lift_shift"] = {
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
    }

    # Now assemble the candidate list with the primary candidate matching the user's action at index 0
    candidates = []

    if action == "scale_up" or action == "scale":
        candidates.append(candidate_map["scale_up"])
        candidates.append(candidate_map["multi_az_modernize"])
        if comp_type == "database":
            candidates.append(candidate_map["read_replica_offload"])
        candidates.append(candidate_map["phased_blue_green"])

    elif action == "remove" or action == "decommission":
        candidates.append(candidate_map["remove"])
        if affected_count > 0:
            candidates.append(candidate_map["dependency_circuit_breaker"])
        candidates.append(candidate_map["direct_lift_shift"])

    elif action == "read_replica_offload" or action == "read_replica":
        candidates.append(candidate_map["read_replica_offload"])
        candidates.append(candidate_map["multi_az_modernize"])
        candidates.append(candidate_map["phased_blue_green"])

    elif action == "dependency_circuit_breaker" or action == "circuit_breaker":
        candidates.append(candidate_map["dependency_circuit_breaker"])
        candidates.append(candidate_map["multi_az_modernize"])
        candidates.append(candidate_map["phased_blue_green"])

    elif action == "multi_az_modernize" or action == "multi_az":
        candidates.append(candidate_map["multi_az_modernize"])
        candidates.append(candidate_map["phased_blue_green"])
        candidates.append(candidate_map["direct_lift_shift"])
        if comp_type == "database":
            candidates.append(candidate_map["read_replica_offload"])

    elif action == "phased_blue_green" or action == "blue_green":
        candidates.append(candidate_map["phased_blue_green"])
        candidates.append(candidate_map["multi_az_modernize"])
        candidates.append(candidate_map["direct_lift_shift"])

    elif action == "migrate" or action == "migration":
        candidates.append(candidate_map["direct_lift_shift"])
        candidates.append(candidate_map["phased_blue_green"])
        candidates.append(candidate_map["multi_az_modernize"])

    elif action in ["fail", "outage"]:
        # Remediation strategies to prevent or mitigate outage
        candidates.append(candidate_map["multi_az_modernize"])
        candidates.append(candidate_map["phased_blue_green"])
        candidates.append(candidate_map["direct_lift_shift"])
        if upstream_count >= 1:
            candidates.append(candidate_map["dependency_circuit_breaker"])

    else:
        # Generic fallback
        candidates.append(candidate_map["direct_lift_shift"])
        candidates.append(candidate_map["phased_blue_green"])
        candidates.append(candidate_map["multi_az_modernize"])
        if include_extended and comp_type == "database":
            candidates.append(candidate_map["read_replica_offload"])
        if include_extended and upstream_count >= 1:
            candidates.append(candidate_map["dependency_circuit_breaker"])

    return candidates
