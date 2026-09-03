import boto3
import json
from botocore.exceptions import ClientError

import os

SUPPORTED_TYPES = [
    "AWS::EC2::VPC",
    "AWS::EC2::Subnet",
    "AWS::EC2::SecurityGroup",
    "AWS::EC2::Instance",
    "AWS::RDS::DBInstance",
    "AWS::ElasticLoadBalancingV2::LoadBalancer",
    "AWS::S3::Bucket",
    "AWS::EC2::RouteTable",
    "AWS::EC2::InternetGateway",
    "AWS::EC2::NatGateway",
    "AWS::EC2::NetworkInterface"
]

def check_config_status(client):
    try:
        response = client.describe_configuration_recorder_status()
        status_list = response.get("ConfigurationRecordersStatus", [])
        for status in status_list:
            if status.get("recording"):
                return True
        return False
    except ClientError as e:
        print(f"Error checking Config status: {e}")
        return False

def extract_name_from_tags(tags):
    if not tags:
        return "Unknown"
    try:
        # Sometimes tags are dicts, sometimes lists of dicts
        if isinstance(tags, dict):
            return tags.get("Name", "Unknown")
        elif isinstance(tags, list):
            for t in tags:
                if t.get("key") == "Name" or t.get("Key") == "Name":
                    return t.get("value") or t.get("Value") or "Unknown"
    except Exception:
        pass
    return "Unknown"

def discover_resources(client, region):
    results = {rt: [] for rt in SUPPORTED_TYPES}
    normalized_resources = []
    
    for rtype in SUPPORTED_TYPES:
        try:
            paginator = client.get_paginator('list_discovered_resources')
            resource_keys = []
            
            for page in paginator.paginate(resourceType=rtype):
                for res in page.get('resourceIdentifiers', []):
                    resource_keys.append({
                        'resourceType': res['resourceType'],
                        'resourceId': res['resourceId']
                    })
            
            # batch_get_resource_config can handle up to 100 per batch
            for i in range(0, len(resource_keys), 100):
                batch = resource_keys[i:i+100]
                batch_res = client.batch_get_resource_config(resourceKeys=batch)
                
                for item in batch_res.get('baseConfigurationItems', []):
                    # extract name
                    name = item.get('resourceName')
                    if not name:
                        name = extract_name_from_tags(item.get('tags'))
                    if name == "Unknown" or not name:
                        name = f"{rtype.split('::')[-1]}-{item.get('resourceId')}"
                    
                    config = {}
                    if item.get('configuration'):
                        try:
                            config = json.loads(item['configuration'])
                        except:
                            config = item['configuration']
                            
                    status = config.get('state', config.get('status', 'Unknown')) if isinstance(config, dict) else 'Unknown'
                    
                    normalized = {
                        "resource_id": item.get('resourceId'),
                        "resource_type": item.get('resourceType'),
                        "name": name,
                        "region": item.get('awsRegion', region),
                        "arn": item.get('arn', ''),
                        "status": status,
                        "raw_configuration": config
                    }
                    normalized_resources.append(normalized)
                    results[rtype].append(normalized)
                    
        except ClientError as e:
            if e.response['Error']['Code'] == 'AccessDeniedException':
                print(f"Access Denied for {rtype}: Missing permissions to list discovered resources.")
            else:
                print(f"Error fetching {rtype}: {e}")
                
    return results, normalized_resources

def main():
    try:
        session = boto3.Session()
        region = os.environ.get("AWS_REGION") or session.region_name or "us-east-1"
        client = session.client('config', region_name=region)
        
        print(f"AWS Region: {region}")
        
        is_recording = check_config_status(client)
        print(f"AWS Config: {'Recording' if is_recording else 'Not Recording'}")
        
        if not is_recording:
            print("Please ensure AWS Config is enabled and recording.")
            # Even if not recording, it might have historical data, but let's proceed anyway
        
        print("\nDiscovering resources...")
        results, normalized_resources = discover_resources(client, region)
        
        print("\nDiscovered resources:")
        for rtype in SUPPORTED_TYPES:
            short_name = rtype.split("::")[-1]
            if short_name == "DBInstance": short_name = "RDS"
            if short_name == "LoadBalancer": short_name = "Load Balancer"
            print(f"{short_name}: {len(results[rtype])}")
            
        print("\n--- Sample Details ---")
        for res in normalized_resources:
            print(f"- {res['resource_type']} | {res['resource_id']} | {res['name']}")
            
    except ClientError as e:
        print(f"AWS Error: {e}")
    except Exception as e:
        print(f"Unexpected Error: {e}")

if __name__ == "__main__":
    main()
