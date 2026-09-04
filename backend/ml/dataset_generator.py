import os
import sys
import random
import numpy as np
import pandas as pd
from typing import List, Dict, Any

# Add backend root to sys.path for standalone script execution
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml.feature_extractor import CATEGORICAL_FEATURES, NUMERICAL_FEATURES, vectorize_features, get_feature_names

def generate_simulation_dataset(num_scenarios: int = 2400, random_seed: int = 42) -> pd.DataFrame:
    """
    Generates a simulation-grounded training dataset for the ML Solution Suggestion Engine.
    
    Notice: This is a simulation-generated proof-of-concept training dataset representing
    architectural operational outcomes across diverse Digital Twin topology & telemetry scenarios.
    """
    random.seed(random_seed)
    np.random.seed(random_seed)
    
    component_types = ["server", "database", "application", "lambda", "container", "storage"]
    criticalities = ["critical", "high", "medium", "low"]
    statuses = ["active", "degraded", "warning"]
    actions = ["migrate", "scale", "restart", "fail"]
    strategies = [
        "direct_lift_shift",
        "phased_blue_green",
        "multi_az_modernize",
        "read_replica_offload",
        "auto_scaling_group",
        "dependency_circuit_breaker"
    ]
    
    rows = []
    
    for _ in range(num_scenarios):
        # Sample infrastructure scenario
        comp_type = random.choice(component_types)
        crit = random.choice(criticalities)
        status = random.choice(statuses)
        action = random.choice(actions)
        
        upstream_count = random.randint(0, 8)
        downstream_count = random.randint(0, 6)
        total_affected = upstream_count + downstream_count
        crit_callers = min(random.randint(0, 4), upstream_count)
        max_depth = random.randint(0, 4) if upstream_count > 0 else 0
        is_spof = 1 if (upstream_count >= 2 and downstream_count >= 1 and random.random() > 0.4) else 0
        cross_env = random.randint(0, 3) if action == "migrate" else 0
        
        has_cpu = 1 if random.random() > 0.15 else 0
        cpu_percent = round(random.uniform(10.0, 95.0), 1) if has_cpu else -1.0
        
        has_storage = 1 if comp_type in ["database", "storage", "server"] and random.random() > 0.2 else 0
        storage_gb = round(random.uniform(5.0, 1000.0), 1) if has_storage else -1.0
        
        cost_month = round(random.uniform(20.0, 2500.0), 2)
        
        # Risk baseline
        crit_w = {"critical": 35, "high": 22, "medium": 12, "low": 5}[crit]
        act_w = {"fail": 35, "migrate": 15, "scale": 8, "restart": 5}[action]
        health_w = 20 if (status == "degraded" or (cpu_percent > 80.0)) else 0
        blast_w = min(upstream_count * 10 + crit_callers * 8, 30)
        spof_w = 15 if is_spof else 0
        risk_score = min(max(crit_w + act_w + health_w + blast_w + spof_w + cross_env * 5, 5), 100)
        
        has_dt = 1 if has_storage or action in ["migrate", "fail"] else 0
        sim_dt = round(storage_gb * 0.05 + max_depth * 5 + (30 if comp_type == "database" else 15), 1) if has_dt else -1.0
        
        has_cost = 1 if cost_month > 0 else 0
        sim_cost_delta = round(cost_month * (0.20 if action == "migrate" else (0.50 if action == "scale" else 0.0)), 2)
        
        # Evaluate each strategy for this scenario
        for strat in strategies:
            strat_complexity = 1 if strat == "direct_lift_shift" else (2 if strat in ["phased_blue_green", "auto_scaling_group"] else 3)
            provides_red = 1 if strat in ["multi_az_modernize", "phased_blue_green", "auto_scaling_group"] else 0
            requires_sync = 1 if strat in ["phased_blue_green", "read_replica_offload"] else 0
            zero_dt = 1 if strat in ["multi_az_modernize", "phased_blue_green", "auto_scaling_group"] else 0
            
            # --- Domain-Grounded Suitability Function (Ground Truth for Training) ---
            suitability = 0.50  # baseline
            
            if strat == "direct_lift_shift":
                if comp_type in ["database", "storage"] and action == "migrate":
                    suitability -= 0.35  # High risk of data loss/downtime for stateful migration
                elif upstream_count >= 3 or is_spof:
                    suitability -= 0.25  # Maintenance window disrupts too many callers
                elif comp_type in ["lambda", "container"] and upstream_count <= 1:
                    suitability += 0.35  # Fast and simple for low-dependency stateless workloads
                else:
                    suitability += 0.10
                    
            elif strat == "phased_blue_green":
                if action == "migrate" and comp_type in ["database", "server", "application"]:
                    suitability += 0.35  # Live sync allows zero downtime cutover
                if upstream_count >= 2:
                    suitability += 0.15  # Continuous SLA protection
                if comp_type == "lambda":
                    suitability -= 0.20  # Overhead unnecessary for serverless
                    
            elif strat == "multi_az_modernize":
                if is_spof or crit in ["critical", "high"]:
                    suitability += 0.40  # Eliminates articulation point and single point of failure
                if comp_type in ["database", "server"]:
                    suitability += 0.20
                if comp_type == "lambda":
                    suitability -= 0.10
                    
            elif strat == "read_replica_offload":
                if comp_type == "database" and (upstream_count >= 3 or cpu_percent > 75.0):
                    suitability += 0.45  # Offloads heavy query reads
                elif comp_type != "database":
                    suitability -= 0.40  # Inapplicable for non-database components
                    
            elif strat == "auto_scaling_group":
                if comp_type in ["server", "container", "application"] and (cpu_percent > 75.0 or action == "scale"):
                    suitability += 0.45  # Elastic elasticity for compute
                elif comp_type in ["database", "storage"]:
                    suitability -= 0.35  # Stateful storage cannot be arbitrarily scaled in ASG
                    
            elif strat == "dependency_circuit_breaker":
                if upstream_count >= 3 and crit_callers >= 1:
                    suitability += 0.40  # Decouples cascade failure propagation
                elif upstream_count == 0:
                    suitability -= 0.35  # Useless for leaf nodes with no callers
                    
            # Apply Gaussian noise to prevent perfect deterministic memorization
            noise = np.random.normal(0.0, 0.04)
            final_suitability = float(np.clip(suitability + noise, 0.05, 0.98))
            is_recommended = 1 if final_suitability >= 0.70 else 0
            
            feat_dict = {
                "component_type": comp_type,
                "criticality": crit,
                "status": status,
                "action": action,
                "strategy_type": strat,
                "upstream_callers_count": upstream_count,
                "downstream_deps_count": downstream_count,
                "total_affected_count": total_affected,
                "critical_callers_count": crit_callers,
                "max_dependency_depth": max_depth,
                "is_spof": is_spof,
                "cross_env_links": cross_env,
                "cpu_percent": cpu_percent,
                "has_cpu_telemetry": has_cpu,
                "storage_gb": storage_gb,
                "has_storage_telemetry": has_storage,
                "cost_per_month": cost_month,
                "risk_score": risk_score,
                "simulated_downtime_minutes": sim_dt,
                "has_downtime_metric": has_dt,
                "simulated_cost_delta": sim_cost_delta,
                "has_cost_metric": has_cost,
                "strategy_complexity": strat_complexity,
                "provides_redundancy": provides_red,
                "requires_data_sync": requires_sync,
                "zero_downtime_capable": zero_dt,
                "suitability_score": round(final_suitability, 4),
                "is_suitable_label": is_recommended
            }
            rows.append(feat_dict)
            
    df = pd.DataFrame(rows)
    return df

def save_generated_dataset(output_path: str = None) -> str:
    default_path = os.path.join(os.path.dirname(__file__), "data", "simulation_training_data.csv")
    out = output_path or default_path
    os.makedirs(os.path.dirname(out), exist_ok=True)
    df = generate_simulation_dataset()
    df.to_csv(out, index=False)
    print(f"Simulation training dataset successfully saved to: {out} ({len(df)} samples)")
    return out

if __name__ == "__main__":
    save_generated_dataset()
