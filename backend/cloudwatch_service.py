import boto3
from datetime import datetime, timedelta
from botocore.exceptions import ClientError
import json

def _get_cw_client(component):
    region = "us-east-1"
    if isinstance(component, dict):
        region = component.get("location", region)
    else:
        region = getattr(component, "location", region)
    if region and region.startswith("AWS-"):
        region = region.replace("AWS-", "")
    if not region:
        region = "us-east-1"
    return boto3.client('cloudwatch', region_name=region)

def _get_dimensions_and_namespace(component):
    meta = {}
    if isinstance(component, dict):
        comp_type = component.get("type", "")
        comp_id = component.get("id", "")
        comp_name = component.get("name", "")
        meta = component.get("metadata_col", {})
    else:
        comp_type = getattr(component, "type", "")
        comp_id = getattr(component, "id", "")
        comp_name = getattr(component, "name", "")
        meta = getattr(component, "metadata_col", {})

    if not isinstance(meta, dict):
        try:
            meta = json.loads(meta)
        except:
            meta = {}

    namespace = None
    dimensions = []

    if comp_type == "server" and "aws_ec2_instance" in comp_id:
        namespace = "AWS/EC2"
        instance_id = meta.get("instanceId")
        if instance_id:
            dimensions = [{"Name": "InstanceId", "Value": instance_id}]
            
    elif comp_type == "database" and "aws_rds_dbinstance" in comp_id:
        namespace = "AWS/RDS"
        db_id = meta.get("dBInstanceIdentifier")
        if db_id:
            dimensions = [{"Name": "DBInstanceIdentifier", "Value": db_id}]
            
    elif comp_type == "network" and "elasticloadbalancingv2" in comp_id:
        namespace = "AWS/ApplicationELB"
        lb_arn = meta.get("loadBalancerArn")
        if lb_arn:
            lb_name = "/".join(lb_arn.split(":")[-1].split("/")[1:])
            dimensions = [{"Name": "LoadBalancer", "Value": lb_name}]
            
    elif comp_type == "storage" and "aws_s3_bucket" in comp_id:
        namespace = "AWS/S3"
        bucket_name = comp_name
        if bucket_name:
            dimensions = [
                {"Name": "BucketName", "Value": bucket_name}, 
                {"Name": "StorageType", "Value": "StandardStorage"}
            ]

    return namespace, dimensions

def _get_metric_average(client, namespace, metric_name, dimensions, period, days_back=1):
    if not dimensions:
        return None
    
    end_time = datetime.utcnow()
    
    if namespace == "AWS/S3":
        # S3 metrics are updated daily
        start_time = end_time - timedelta(days=3)
        period = 86400 # 1 day
    else:
        start_time = end_time - timedelta(seconds=period * 2) 
        
    try:
        response = client.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric_name,
            Dimensions=dimensions,
            StartTime=start_time,
            EndTime=end_time,
            Period=period,
            Statistics=['Average']
        )
        datapoints = response.get('Datapoints', [])
        if not datapoints:
            return None
        # Sort by timestamp descending
        latest = sorted(datapoints, key=lambda x: x['Timestamp'], reverse=True)[0]
        return round(latest['Average'], 2)
    except ClientError:
        return None
    except Exception:
        return None

def get_cpu_utilization(component, period=300):
    client = _get_cw_client(component)
    namespace, dimensions = _get_dimensions_and_namespace(component)
    if namespace in ["AWS/EC2", "AWS/RDS"]:
        return _get_metric_average(client, namespace, "CPUUtilization", dimensions, period)
    return None

def get_memory_utilization(component, period=300):
    client = _get_cw_client(component)
    namespace, dimensions = _get_dimensions_and_namespace(component)
    if namespace == "AWS/RDS":
        # Returns raw bytes converted to MB
        val = _get_metric_average(client, namespace, "FreeableMemory", dimensions, period)
        if val is not None:
            return round(val / (1024 * 1024), 2)
    return None

def get_active_alarms(component):
    client = _get_cw_client(component)
    namespace, dimensions = _get_dimensions_and_namespace(component)
    if not dimensions:
        return []
    
    alarms = []
    try:
        if namespace in ["AWS/EC2", "AWS/RDS"]:
            res = client.describe_alarms_for_metric(
                MetricName="CPUUtilization",
                Namespace=namespace,
                Dimensions=dimensions
            )
            for alarm in res.get("MetricAlarms", []):
                if alarm.get("StateValue") == "ALARM":
                    alarms.append(alarm.get("AlarmName"))
    except ClientError:
        pass
    return alarms

def get_resource_health(component):
    comp_id = component.get("id") if isinstance(component, dict) else getattr(component, "id", "unknown")
    comp_type = component.get("type") if isinstance(component, dict) else getattr(component, "type", "unknown")
    
    cpu = get_cpu_utilization(component)
    memory = get_memory_utilization(component)
    alarms = get_active_alarms(component)
    
    status = "healthy"
    if alarms:
        status = "degraded"
        
    return {
        "resource_id": comp_id,
        "resource_type": comp_type,
        "status": status,
        "metrics": {
            "cpu_utilization": cpu,
            "memory_utilization": memory
        },
        "alarms": alarms
    }

if __name__ == "__main__":
    import database, models
    print("Testing CloudWatch Integration for S3 Bucket...")
    db = next(database.get_db())
    s3_comp = db.query(models.Component).filter(models.Component.id.like("%aws_s3_bucket%")).first()
    if s3_comp:
        health = get_resource_health(s3_comp)
        print("\n--- Health Report ---")
        print(json.dumps(health, indent=2))
        
        print("\n--- Testing Custom S3 Metric (BucketSizeBytes) ---")
        client = _get_cw_client(s3_comp)
        ns, dims = _get_dimensions_and_namespace(s3_comp)
        size = _get_metric_average(client, ns, "BucketSizeBytes", dims, period=86400, days_back=3)
        print(f"BucketSizeBytes: {size} bytes")
    else:
        print("No S3 bucket component found in database to test.")
