import sys
import boto3
from sqlalchemy.orm import Session
import database
import models

try:
    import aws_sync
    import aws_mapper
except ImportError as e:
    print(f"Error importing modules: {e}")
    sys.exit(1)

def sync_database():
    session_aws = boto3.Session()
    region = session_aws.region_name or "us-east-1"
    client = session_aws.client('config', region_name=region)

    raw_results, normalized_resources = aws_sync.discover_resources(client, region)
    
    aws_components = []
    for r in normalized_resources:
        aws_components.append(aws_mapper.resource_to_component(r))
        
    aws_dependencies = aws_mapper.extract_dependencies(normalized_resources)
    
    db = next(database.get_db())
    
    stats = {
        "comp_discovered": len(aws_components),
        "comp_inserted": 0,
        "comp_updated": 0,
        "comp_unchanged": 0,
        "dep_discovered": len(aws_dependencies),
        "dep_inserted": 0,
        "dep_existing": 0
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
                    # We don't want to overwrite metadata_col if not strictly necessary, 
                    # but since it's deterministic we can check for changes
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
        
        # --- COST EXPLORER SYNC ---
        print("Retrieving AWS Cost Explorer data...")
        try:
            import cost_explorer_service
            costs = cost_explorer_service.get_current_month_service_costs()
            if costs.get("_status") == "pending":
                print("Cost Explorer data is currently pending (Data Unavailable). Skipping cost update.")
            elif not costs:
                print("No cost data returned by Cost Explorer (or Access Denied). Skipping cost update.")
            else:
                service_map = {
                    "Simple Storage Service": "aws_s3",
                    "Elastic Compute Cloud": "aws_ec2",
                    "Relational Database Service": "aws_rds",
                    "Virtual Private Cloud": "aws_ec2_vpc",
                    "Elastic Load Balancing": "aws_elasticloadbalancing"
                }
                
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
                db.commit()
                print("Cost Explorer data mapped to AWS components successfully.")
        except Exception as e:
            db.rollback()
            print(f"Error synchronizing costs: {e}")

        print("\nAWS Database Sync")
        print("=================")
        print(f"Discovered components: {stats['comp_discovered']}")
        print(f"Inserted components: {stats['comp_inserted']}")
        print(f"Updated components: {stats['comp_updated']}")
        print(f"Existing components unchanged: {stats['comp_unchanged']}\n")
        
        print(f"Discovered dependencies: {stats['dep_discovered']}")
        print(f"Inserted dependencies: {stats['dep_inserted']}")
        print(f"Existing dependencies: {stats['dep_existing']}\n")
        print(f"Database: {database.SQLALCHEMY_DATABASE_URL}")
        
    except Exception as e:
        db.rollback()
        print(f"Database sync failed, rolled back. Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    sync_database()
