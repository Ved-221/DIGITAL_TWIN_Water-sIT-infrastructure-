from sqlalchemy.orm import Session
import database, models
import uuid

def seed_data(db: Session):
    if db.query(models.Component).count() > 0:
        return

    # Seed Environment record
    env = db.query(models.Environment).filter(models.Environment.id == "manual_waters").first()
    if not env:
        env = models.Environment(id="manual_waters", name="Waters Representative Lab Infrastructure", type="manual")
        db.add(env)

    # Seed Manual Project record for UI
    proj = db.query(models.ManualProject).filter(models.ManualProject.id == "manual_waters").first()
    if not proj:
        proj = models.ManualProject(id="manual_waters", name="Waters Representative Lab Infrastructure")
        db.add(proj)

    components_data = [
        # Applications
        {"id": "app_core_api", "name": "Core Microservices API", "type": "application", "environment": "on_prem", "location": "US-East", "criticality": "critical", "owner": "Platform Engineering", "cost_per_month": 5000.0},
        {"id": "app_erp", "name": "ERP System", "type": "application", "environment": "on_prem", "location": "US-East", "criticality": "critical", "owner": "Finance", "cost_per_month": 8000.0},
        {"id": "app_crm", "name": "CRM Platform", "type": "application", "environment": "cloud", "location": "AWS-us-east-1", "criticality": "high", "owner": "Sales Ops", "cost_per_month": 3000.0},
        {"id": "app_reporting", "name": "Reporting & Analytics", "type": "application", "environment": "on_prem", "location": "US-East", "criticality": "medium", "owner": "Data Team", "cost_per_month": 1500.0},
        {"id": "app_portal", "name": "Customer Web Portal", "type": "application", "environment": "hybrid", "location": "Global", "criticality": "high", "owner": "Web Engineering", "cost_per_month": 2500.0},
        
        # Databases
        {"id": "db_core", "name": "Core Transactions DB", "type": "database", "environment": "on_prem", "location": "US-East", "criticality": "critical", "owner": "DBA Team", "cost_per_month": 2000.0},
        {"id": "db_erp", "name": "ERP Relational DB", "type": "database", "environment": "on_prem", "location": "US-East", "criticality": "critical", "owner": "DBA Team", "cost_per_month": 4000.0},
        {"id": "db_analytics", "name": "Analytics DB", "type": "database", "environment": "cloud", "location": "AWS-us-east-1", "criticality": "high", "owner": "Data Team", "cost_per_month": 3500.0},
        
        # Servers
        {"id": "srv_app_01", "name": "On-prem App Server 01", "type": "server", "environment": "on_prem", "location": "US-East", "criticality": "high", "owner": "IT Ops", "cost_per_month": 800.0, "source_environment": "manual_waters"},
        {"id": "srv_app_02", "name": "On-prem App Server 02", "type": "server", "environment": "on_prem", "location": "US-East", "criticality": "high", "owner": "IT Ops", "cost_per_month": 800.0, "source_environment": "manual_waters"},
        {"id": "srv_db_01", "name": "On-prem DB Server", "type": "server", "environment": "on_prem", "location": "US-East", "criticality": "critical", "owner": "IT Ops", "cost_per_month": 1200.0, "source_environment": "manual_waters"},
        {"id": "edge_gw", "name": "Lab Instrument Gateway", "type": "server", "environment": "on_prem", "location": "Lab-01", "criticality": "high", "owner": "Lab Systems", "cost_per_month": 300.0, "source_environment": "manual_waters"},
        
        # Network & Security
        {"id": "net_wan", "name": "Corporate WAN", "type": "network", "environment": "hybrid", "location": "Global", "criticality": "critical", "owner": "NetSec", "cost_per_month": 10000.0, "source_environment": "manual_waters"},
        {"id": "net_fw", "name": "Core Firewall", "type": "network", "environment": "on_prem", "location": "US-East", "criticality": "critical", "owner": "NetSec", "cost_per_month": 2000.0, "source_environment": "manual_waters"},
        {"id": "sec_auth", "name": "Authentication Service (SSO)", "type": "identity", "environment": "on_prem", "location": "US-East", "criticality": "critical", "owner": "IAM", "cost_per_month": 500.0, "source_environment": "manual_waters"},
        
        # Cloud/Edge
        {"id": "cloud_compute", "name": "AWS EC2 Cluster", "type": "cloud_resource", "environment": "cloud", "location": "AWS-us-east-1", "criticality": "high", "owner": "Cloud Ops", "cost_per_month": 4500.0},
        {"id": "cloud_s3", "name": "AWS S3 Data Lake", "type": "cloud_resource", "environment": "cloud", "location": "AWS-us-east-1", "criticality": "high", "owner": "Data Team", "cost_per_month": 1200.0},
        
        # Storage
        {"id": "sto_primary", "name": "Primary SAN", "type": "storage", "environment": "on_prem", "location": "US-East", "criticality": "critical", "owner": "Storage Team", "cost_per_month": 6000.0, "source_environment": "manual_waters"},
    ]

    for data in components_data:
        data.setdefault("source_environment", "manual_waters")
        data.setdefault("discovery_source", "manual_waters")
        comp = models.Component(**data)
        db.add(comp)
    db.commit()

    dependencies_data = [
        # Core Microservices stack
        {"source_id": "app_core_api", "target_id": "db_core", "relationship_type": "depends_on", "criticality": "critical"},
        {"source_id": "app_core_api", "target_id": "srv_app_01", "relationship_type": "hosted_on", "criticality": "critical"},
        {"source_id": "app_core_api", "target_id": "sec_auth", "relationship_type": "authenticates_via", "criticality": "critical"},
        {"source_id": "db_core", "target_id": "srv_db_01", "relationship_type": "hosted_on", "criticality": "critical"},
        {"source_id": "db_core", "target_id": "sto_primary", "relationship_type": "stores_in", "criticality": "critical"},
        {"source_id": "edge_gw", "target_id": "app_core_api", "relationship_type": "connects_to", "criticality": "high"},
        
        # ERP stack
        {"source_id": "app_erp", "target_id": "db_erp", "relationship_type": "depends_on", "criticality": "critical", "source_environment": "manual_waters"},
        {"source_id": "app_erp", "target_id": "srv_app_02", "relationship_type": "hosted_on", "criticality": "critical", "source_environment": "manual_waters"},
        {"source_id": "app_erp", "target_id": "sec_auth", "relationship_type": "authenticates_via", "criticality": "critical", "source_environment": "manual_waters"},
        {"source_id": "db_erp", "target_id": "srv_db_01", "relationship_type": "hosted_on", "criticality": "critical", "source_environment": "manual_waters"},
        {"source_id": "db_erp", "target_id": "sto_primary", "relationship_type": "stores_in", "criticality": "critical", "source_environment": "manual_waters"},

        # Analytics
        {"source_id": "app_reporting", "target_id": "db_analytics", "relationship_type": "depends_on", "criticality": "high", "source_environment": "manual_waters"},
        {"source_id": "db_analytics", "target_id": "db_erp", "relationship_type": "connects_to", "criticality": "medium", "source_environment": "manual_waters"},
        {"source_id": "db_analytics", "target_id": "cloud_s3", "relationship_type": "stores_in", "criticality": "high", "source_environment": "manual_waters"},
        {"source_id": "app_reporting", "target_id": "cloud_compute", "relationship_type": "hosted_on", "criticality": "high", "source_environment": "manual_waters"},
        
        # Network deps
        {"source_id": "srv_app_01", "target_id": "net_wan", "relationship_type": "connects_to", "criticality": "critical", "source_environment": "manual_waters"},
        {"source_id": "srv_app_02", "target_id": "net_wan", "relationship_type": "connects_to", "criticality": "critical", "source_environment": "manual_waters"},
        {"source_id": "srv_db_01", "target_id": "net_wan", "relationship_type": "connects_to", "criticality": "critical", "source_environment": "manual_waters"},
        {"source_id": "net_wan", "target_id": "net_fw", "relationship_type": "depends_on", "criticality": "critical", "source_environment": "manual_waters"},
        {"source_id": "cloud_compute", "target_id": "net_wan", "relationship_type": "connects_to", "criticality": "high", "source_environment": "manual_waters"},
        
        # CRM
        {"source_id": "app_crm", "target_id": "cloud_compute", "relationship_type": "hosted_on", "criticality": "high", "source_environment": "manual_waters"},
        {"source_id": "app_crm", "target_id": "sec_auth", "relationship_type": "authenticates_via", "criticality": "critical", "source_environment": "manual_waters"},
        
        # Portal
        {"source_id": "app_portal", "target_id": "app_core_api", "relationship_type": "connects_to", "criticality": "high"},
        {"source_id": "app_portal", "target_id": "sec_auth", "relationship_type": "authenticates_via", "criticality": "critical"},
        {"source_id": "app_portal", "target_id": "cloud_compute", "relationship_type": "hosted_on", "criticality": "high"},
    ]

    for data in dependencies_data:
        dep_dict = {
            "source_component_id": data["source_id"],
            "target_component_id": data["target_id"],
            "source_id": data["source_id"],
            "target_id": data["target_id"],
            "relationship_type": data["relationship_type"],
            "criticality": data["criticality"],
            "source": data.get("source_environment", "manual_waters"),
            "source_environment": data.get("source_environment", "manual_waters"),
            "discovery_source": "manual_waters",
            "metadata_col": {"origin": "enterprise_baseline"}
        }
        dep = models.Dependency(**dep_dict)
        db.add(dep)
    db.commit()
    print("Seed data inserted.")

