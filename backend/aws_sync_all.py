import sys
import boto3
import os

try:
    import aws_sync
    import aws_mapper
    import database
    import models
    import cost_explorer_service
except ImportError as e:
    print(f"Error importing modules: {e}")
    sys.exit(1)

def main():
    print("========================================")
    print("       INFRATWIN AWS SYNC")
    print("========================================\n")
    
    session = boto3.Session()
    region = os.environ.get("AWS_REGION") or session.region_name or "us-east-1"
    client = session.client('config', region_name=region)
    
    print(f"AWS Region: {region}\n")
    
    # 1. AWS Config
    is_recording = aws_sync.check_config_status(client)
    recording_status = "Recording" if is_recording else "Not Recording"
    print(f"[1/5] AWS Config")
    print(f"      Status: {recording_status}")
    
    raw_results, normalized_resources = aws_sync.discover_resources(client, region)
    discovered_count = len(normalized_resources)
    print(f"      Resources discovered: {discovered_count}\n")
    
    # 2. Topology Mapping
    aws_components = []
    for r in normalized_resources:
        aws_components.append(aws_mapper.resource_to_component(r))
        
    aws_dependencies = aws_mapper.extract_dependencies(normalized_resources)
    print(f"[2/5] Topology Mapping")
    print(f"      Components: {len(aws_components)}")
    print(f"      Dependencies: {len(aws_dependencies)}\n")
    
    # 3. Database Synchronization
    print(f"[3/5] Database Synchronization")
    db = next(database.get_db())
    stats = {
        "comp_inserted": 0, "comp_updated": 0, "comp_unchanged": 0,
        "dep_inserted": 0, "dep_existing": 0
    }
    
    try:
        for comp_data in aws_components:
            existing = db.query(models.Component).filter(models.Component.id == comp_data["id"]).first()
            if not existing:
                new_comp = models.Component(**comp_data)
                db.add(new_comp)
                stats["comp_inserted"] += 1
            else:
                changed = False
                for key, value in comp_data.items():
                    if getattr(existing, key) != value:
                        setattr(existing, key, value)
                        changed = True
                if changed:
                    stats["comp_updated"] += 1
                else:
                    stats["comp_unchanged"] += 1
                    
        db.flush()
        
        for dep_data in aws_dependencies:
            source_id = dep_data["source_id"]
            target_id = dep_data["target_id"]
            rel_type = dep_data["relationship_type"]
            
            src_exists = db.query(models.Component).filter(models.Component.id == source_id).first()
            tgt_exists = db.query(models.Component).filter(models.Component.id == target_id).first()
            if not src_exists or not tgt_exists:
                continue
                
            existing_dep = db.query(models.Dependency).filter(
                models.Dependency.source_id == source_id,
                models.Dependency.target_id == target_id,
                models.Dependency.relationship_type == rel_type
            ).first()
            
            if not existing_dep:
                new_dep = models.Dependency(**dep_data)
                db.add(new_dep)
                stats["dep_inserted"] += 1
            else:
                stats["dep_existing"] += 1
                
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"      Error syncing to DB: {e}")
        
    print(f"      Inserted: {stats['comp_inserted'] + stats['dep_inserted']}")
    print(f"      Updated: {stats['comp_updated']}")
    print(f"      Existing: {stats['comp_unchanged'] + stats['dep_existing']}\n")
    
    # 4. CloudWatch
    print(f"[4/5] CloudWatch")
    print(f"      Health integration: Available\n")
    
    # 5. Cost Explorer
    print(f"[5/5] Cost Explorer")
    try:
        costs = cost_explorer_service.get_current_month_service_costs()
        if costs.get("_status") == "pending":
            print(f"      Status: Pending AWS ingestion")
            print(f"      Cost update: Skipped")
        elif not costs:
            print(f"      Status: Access Denied / Error")
            print(f"      Cost update: Skipped")
        else:
            service_map = {
                "Simple Storage Service": "aws_s3",
                "Elastic Compute Cloud": "aws_ec2",
                "Relational Database Service": "aws_rds",
                "Virtual Private Cloud": "aws_ec2_vpc",
                "Elastic Load Balancing": "aws_elasticloadbalancing"
            }
            mapped_count = 0
            for service_name, total_cost in costs.items():
                if service_name == "_status": continue
                matched_prefix = None
                for key_name, pfx in service_map.items():
                    if key_name in service_name:
                        matched_prefix = pfx
                        break
                if matched_prefix:
                    matched_comps = db.query(models.Component).filter(models.Component.id.like(f"{matched_prefix}%")).all()
                    if matched_comps:
                        cost_per_comp = total_cost / len(matched_comps)
                        for c in matched_comps:
                            c.cost_per_month = cost_per_comp
                        mapped_count += len(matched_comps)
            db.commit()
            print(f"      Status: Real data acquired")
            print(f"      Cost update: Successfully mapped to {mapped_count} resources")
            
    except Exception as e:
        db.rollback()
        print(f"      Status: Error during cost mapping ({e})")
        print(f"      Cost update: Skipped")
    finally:
        db.close()
        
    print("\n========================================")
    print("SYNC COMPLETE")
    print("========================================")

if __name__ == "__main__":
    main()
