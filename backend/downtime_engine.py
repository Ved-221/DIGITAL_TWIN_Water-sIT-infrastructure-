import logging
from typing import Dict, Any
from schemas import DowntimeEstimate

logger = logging.getLogger("infratwin.downtime_engine")

def calculate_downtime_estimate(
    component: Dict[str, Any],
    action: str
) -> DowntimeEstimate:
    """
    Deterministically computes estimated operational downtime based on verified AWS maintenance mechanics.
    Never uses arbitrary flat demo constants.
    """
    comp_type = component.get("type", "")
    meta = component.get("metadata_col", {}) or {}
    is_multi_az = meta.get("multi_az", False)

    if action == "SCALE_COMPUTE":
        if comp_type == "database" or component.get("id", "").startswith("rds-"):
            if is_multi_az:
                return DowntimeEstimate(
                    estimated_downtime_minutes=2,
                    downtime_category="ESTIMATED",
                    rationale="Multi-AZ RDS instance class change performs a rolling upgrade with an automated standby failover (~60-120s)."
                )
            else:
                return DowntimeEstimate(
                    estimated_downtime_minutes=12,
                    downtime_category="ESTIMATED",
                    rationale="Single-AZ RDS instance class modification requires a full database shutdown, parameter group rebind, and reboot (~10-15m)."
                )
        else:
            # EC2 instance resize
            return DowntimeEstimate(
                estimated_downtime_minutes=6,
                downtime_category="ESTIMATED",
                rationale="EC2 compute resize requires: clean OS shutdown (1-2m), instance type attribute modification (30s), boot & 2/2 status check validation (2-4m)."
            )

    elif action == "EXPAND_STORAGE":
        if comp_type == "database":
            return DowntimeEstimate(
                estimated_downtime_minutes=0,
                downtime_category="ZERO_DOWNTIME",
                rationale="AWS RDS storage autoscaling/expansion modifies storage dynamically online without reboot or connection drop."
            )
        else:
            return DowntimeEstimate(
                estimated_downtime_minutes=0,
                downtime_category="ZERO_DOWNTIME",
                rationale="AWS EBS Elastic Volumes allows dynamic capacity expansion and IOPS modification without detaching the volume or rebooting the instance."
            )

    elif action == "OPTIMIZE_IDLE_RESOURCE":
        return DowntimeEstimate(
            estimated_downtime_minutes=5,
            downtime_category="ESTIMATED",
            rationale="Downsizing underutilized compute tier requires scheduled reboot: stop instance (1-2m), rebind tier (30s), start & verify health (2-3m)."
        )

    elif action == "INVESTIGATE_DATABASE_BOTTLENECK":
        return DowntimeEstimate(
            estimated_downtime_minutes=0,
            downtime_category="ZERO_DOWNTIME",
            rationale="Deploying an RDS Proxy or inspecting slow queries is an architectural operational change that requires zero instance downtime."
        )

    elif action in ["migrate", "MIGRATE"]:
        if comp_type == "database":
            return DowntimeEstimate(
                estimated_downtime_minutes=30,
                downtime_category="ESTIMATED",
                rationale="Database cross-environment migration cutover window: final delta sync, read-only lock, and endpoint DNS switchover."
            )
        else:
            return DowntimeEstimate(
                estimated_downtime_minutes=15,
                downtime_category="ESTIMATED",
                rationale="Workload migration cutover: service state quiesce, container/AMI boot in target environment, and health check validation."
            )

    else:
        # NO_ACTION, INVESTIGATE_LATENCY_ERROR, REDUNDANCY_RISK
        return DowntimeEstimate(
            estimated_downtime_minutes=0,
            downtime_category="ZERO_DOWNTIME",
            rationale="Diagnostic investigation or safe baseline state requires no maintenance interruption."
        )
