import sys
import os
import boto3
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from botocore.exceptions import ClientError, NoCredentialsError

import database
import models
import aws_sync
import aws_mapper
import cost_explorer_service

def get_aws_region(explicit_region: str = None) -> str:
    if explicit_region:
        return explicit_region
    session = boto3.Session()
    return os.environ.get("AWS_REGION") or session.region_name or "us-east-1"

def check_aws_status(region: str = None) -> Dict[str, Any]:
    """
    Checks AWS connection, Config recorder status, and current region.
    """
    active_region = get_aws_region(region)
    try:
        session = boto3.Session()
        client = session.client('config', region_name=active_region)
        is_recording = aws_sync.check_config_status(client)
        
        # Test STS identity if possible
        sts = session.client('sts', region_name=active_region)
        identity = sts.get_caller_identity()
        account_id = identity.get("Account", "Unknown")
        arn = identity.get("Arn", "Unknown")

        return {
            "status": "connected",
            "region": active_region,
            "account_id": account_id,
            "arn": arn,
            "config_recording": is_recording,
            "message": "AWS connection established."
        }
    except NoCredentialsError:
        return {
            "status": "no_credentials",
            "region": active_region,
            "config_recording": False,
            "message": "No AWS credentials found in environment or AWS profile."
        }
    except ClientError as e:
        return {
            "status": "client_error",
            "region": active_region,
            "config_recording": False,
            "message": str(e)
        }
    except Exception as e:
        return {
            "status": "error",
            "region": active_region,
            "config_recording": False,
            "message": str(e)
        }

def sync_aws_infrastructure(db: Session, region: str = None) -> Dict[str, Any]:
    """
    Executes live AWS discovery, maps components and topology dependencies,
    and synchronizes them into the SQLite database under source_environment='aws'.
    """
    active_region = get_aws_region(region)
    session = boto3.Session()
    client = session.client('config', region_name=active_region)

    is_recording = aws_sync.check_config_status(client)
    raw_results, normalized_resources = aws_sync.discover_resources(client, active_region)
    
    aws_components = []
    for r in normalized_resources:
        comp_dict = aws_mapper.resource_to_component(r)
        comp_dict["source_environment"] = "aws"
        comp_dict["location"] = active_region
        aws_components.append(comp_dict)
        
    aws_dependencies = aws_mapper.extract_dependencies(normalized_resources)
    for d in aws_dependencies:
        d["source_environment"] = "aws"

    stats = {
        "region": active_region,
        "config_recording": is_recording,
        "discovered_components": len(aws_components),
        "discovered_dependencies": len(aws_dependencies),
        "inserted_components": 0,
        "updated_components": 0,
        "inserted_dependencies": 0,
        "costs_mapped": False
    }

    try:
        now_str = datetime.now(timezone.utc).isoformat()
        # Ingest components
        for comp_data in aws_components:
            existing = db.query(models.Component).filter(
                models.Component.id == comp_data["id"],
                models.Component.source_environment == "aws"
            ).first()
            if not existing:
                new_comp = models.Component(**comp_data, created_at=now_str, updated_at=now_str)
                db.add(new_comp)
                stats["inserted_components"] += 1
            else:
                changed = False
                for key, value in comp_data.items():
                    if getattr(existing, key) != value:
                        setattr(existing, key, value)
                        changed = True
                if changed:
                    existing.updated_at = now_str
                    stats["updated_components"] += 1

        db.flush()

        # Ingest dependencies
        for dep_data in aws_dependencies:
            source_id = dep_data["source_id"]
            target_id = dep_data["target_id"]
            rel_type = dep_data["relationship_type"]

            src_exists = db.query(models.Component).filter(
                models.Component.id == source_id,
                models.Component.source_environment == "aws"
            ).first()
            tgt_exists = db.query(models.Component).filter(
                models.Component.id == target_id,
                models.Component.source_environment == "aws"
            ).first()
            if not src_exists or not tgt_exists:
                continue

            existing_dep = db.query(models.Dependency).filter(
                models.Dependency.source_id == source_id,
                models.Dependency.target_id == target_id,
                models.Dependency.relationship_type == rel_type,
                models.Dependency.source_environment == "aws"
            ).first()


            if not existing_dep:
                new_dep = models.Dependency(**dep_data, created_at=now_str)
                db.add(new_dep)
                stats["inserted_dependencies"] += 1

        db.commit()

        # Allocate costs from Cost Explorer
        try:
            costs = cost_explorer_service.get_current_month_service_costs()
            if costs and costs.get("_status") != "pending":
                service_map = {
                    "Simple Storage Service": "aws_s3",
                    "Elastic Compute Cloud": "aws_ec2",
                    "Relational Database Service": "aws_rds",
                    "Virtual Private Cloud": "aws_ec2_vpc",
                    "Elastic Load Balancing": "aws_elasticloadbalancing"
                }
                for service_name, total_cost in costs.items():
                    if service_name.startswith("_"):
                        continue
                    matched_prefix = None
                    for key_name, pfx in service_map.items():
                        if key_name in service_name:
                            matched_prefix = pfx
                            break
                    if matched_prefix:
                        matched = db.query(models.Component).filter(
                            models.Component.id.like(f"{matched_prefix}%"),
                            models.Component.source_environment == "aws"
                        ).all()
                        if matched:
                            cost_each = total_cost / len(matched)
                            for c in matched:
                                c.cost_per_month = round(cost_each, 2)
                db.commit()
                stats["costs_mapped"] = True
        except Exception as ce_err:
            print(f"Cost sync error: {ce_err}")

        return stats
    except Exception as e:
        db.rollback()
        raise e

def get_current_costs() -> Dict[str, Any]:
    return cost_explorer_service.get_current_month_service_costs()
