import sys
import boto3

try:
    import aws_sync
except ImportError:
    print("Error: aws_sync.py not found in the same directory.")
    sys.exit(1)

def get_component_id(aws_type, resource_id):
    # AWS::EC2::VPC -> aws_ec2_vpc
    type_normalized = aws_type.replace("AWS::", "").replace("::", "_").lower()
    return f"aws_{type_normalized}_{resource_id}"

def map_component_type(aws_type):
    mapping = {
        "AWS::EC2::VPC": "network",
        "AWS::EC2::Subnet": "network",
        "AWS::EC2::SecurityGroup": "network",
        "AWS::EC2::Instance": "server",
        "AWS::RDS::DBInstance": "database",
        "AWS::ElasticLoadBalancingV2::LoadBalancer": "network",
        "AWS::S3::Bucket": "storage",
        "AWS::EC2::RouteTable": "network",
        "AWS::EC2::InternetGateway": "network",
        "AWS::EC2::NatGateway": "network",
        "AWS::EC2::NetworkInterface": "network"
    }
    return mapping.get(aws_type, "cloud_resource")

def resource_to_component(resource):
    comp_id = get_component_id(resource['resource_type'], resource['resource_id'])
    comp_type = map_component_type(resource['resource_type'])
    
    return {
        "id": comp_id,
        "name": resource.get('name', comp_id),
        "type": comp_type,
        "environment": "cloud",
        "location": resource.get('region', 'us-east-1'),
        "criticality": "medium", # Use safe default
        "owner": "AWS Config",
        "status": "active" if resource.get('status', '').lower() in ['available', 'running', 'active'] else "degraded",
        "cpu": None,
        "memory": None,
        "cost_per_month": 0.0,
        "metadata_col": resource.get('raw_configuration', {})
    }

def extract_dependencies(resources):
    dependencies = []
    
    for res in resources:
        raw = res.get('raw_configuration', {})
        if not raw:
            continue
            
        source_id = get_component_id(res['resource_type'], res['resource_id'])
        rtype = res['resource_type']
        
        # Subnet -> VPC relationship
        # Rationale: Subnets inherently belong to and depend on a VPC
        if rtype == "AWS::EC2::Subnet":
            vpc_id = raw.get('vpcId')
            if vpc_id:
                target_id = get_component_id("AWS::EC2::VPC", vpc_id)
                dependencies.append({
                    "source_id": source_id,
                    "target_id": target_id,
                    "relationship_type": "depends_on",
                    "criticality": "high"
                })
                
        # SecurityGroup -> VPC relationship
        # Rationale: Security Groups belong to a VPC
        elif rtype == "AWS::EC2::SecurityGroup":
            vpc_id = raw.get('vpcId')
            if vpc_id:
                target_id = get_component_id("AWS::EC2::VPC", vpc_id)
                dependencies.append({
                    "source_id": source_id,
                    "target_id": target_id,
                    "relationship_type": "depends_on",
                    "criticality": "medium"
                })

        # EC2 Instance relationships
        elif rtype == "AWS::EC2::Instance":
            vpc_id = raw.get('vpcId')
            if vpc_id:
                dependencies.append({
                    "source_id": source_id,
                    "target_id": get_component_id("AWS::EC2::VPC", vpc_id),
                    "relationship_type": "hosted_on",
                    "criticality": "high"
                })
            
            subnet_id = raw.get('subnetId')
            if subnet_id:
                dependencies.append({
                    "source_id": source_id,
                    "target_id": get_component_id("AWS::EC2::Subnet", subnet_id),
                    "relationship_type": "connects_to",
                    "criticality": "high"
                })
                
            for sg in raw.get('securityGroups', []):
                sg_id = sg.get('groupId')
                if sg_id:
                    dependencies.append({
                        "source_id": source_id,
                        "target_id": get_component_id("AWS::EC2::SecurityGroup", sg_id),
                        "relationship_type": "connects_to",
                        "criticality": "medium"
                    })
                    
        # RDS DBInstance relationships
        elif rtype == "AWS::RDS::DBInstance":
            db_subnet_group = raw.get('dbSubnetGroup', {})
            vpc_id = db_subnet_group.get('vpcId')
            if vpc_id:
                dependencies.append({
                    "source_id": source_id,
                    "target_id": get_component_id("AWS::EC2::VPC", vpc_id),
                    "relationship_type": "hosted_on",
                    "criticality": "high"
                })
            
            for sg in raw.get('vpcSecurityGroups', []):
                sg_id = sg.get('vpcSecurityGroupId')
                if sg_id:
                    dependencies.append({
                        "source_id": source_id,
                        "target_id": get_component_id("AWS::EC2::SecurityGroup", sg_id),
                        "relationship_type": "connects_to",
                        "criticality": "medium"
                    })
                    
        # ELBv2 LoadBalancer relationships
        elif rtype == "AWS::ElasticLoadBalancingV2::LoadBalancer":
            vpc_id = raw.get('vpcId')
            if vpc_id:
                dependencies.append({
                    "source_id": source_id,
                    "target_id": get_component_id("AWS::EC2::VPC", vpc_id),
                    "relationship_type": "hosted_on",
                    "criticality": "high"
                })
                
            for sg in raw.get('securityGroups', []):
                dependencies.append({
                    "source_id": source_id,
                    "target_id": get_component_id("AWS::EC2::SecurityGroup", sg),
                    "relationship_type": "connects_to",
                    "criticality": "medium"
                })

        # Route Table relationships
        elif rtype == "AWS::EC2::RouteTable":
            vpc_id = raw.get('vpcId')
            if vpc_id:
                dependencies.append({
                    "source_id": source_id,
                    "target_id": get_component_id("AWS::EC2::VPC", vpc_id),
                    "relationship_type": "depends_on",
                    "criticality": "high"
                })
            for route in raw.get('routes', []):
                gw_id = route.get('gatewayId')
                if gw_id and gw_id.startswith('igw-'):
                    dependencies.append({
                        "source_id": source_id,
                        "target_id": get_component_id("AWS::EC2::InternetGateway", gw_id),
                        "relationship_type": "connects_to",
                        "criticality": "high"
                    })
                nat_id = route.get('natGatewayId')
                if nat_id and nat_id.startswith('nat-'):
                    dependencies.append({
                        "source_id": source_id,
                        "target_id": get_component_id("AWS::EC2::NatGateway", nat_id),
                        "relationship_type": "connects_to",
                        "criticality": "high"
                    })

        # Internet Gateway relationships
        elif rtype == "AWS::EC2::InternetGateway":
            for attachment in raw.get('attachments', []):
                vpc_id = attachment.get('vpcId')
                if vpc_id:
                    dependencies.append({
                        "source_id": source_id,
                        "target_id": get_component_id("AWS::EC2::VPC", vpc_id),
                        "relationship_type": "depends_on",
                        "criticality": "high"
                    })

        # Network Interface relationships
        elif rtype == "AWS::EC2::NetworkInterface":
            vpc_id = raw.get('vpcId')
            if vpc_id:
                dependencies.append({
                    "source_id": source_id,
                    "target_id": get_component_id("AWS::EC2::VPC", vpc_id),
                    "relationship_type": "depends_on",
                    "criticality": "high"
                })
            subnet_id = raw.get('subnetId')
            if subnet_id:
                dependencies.append({
                    "source_id": source_id,
                    "target_id": get_component_id("AWS::EC2::Subnet", subnet_id),
                    "relationship_type": "connects_to",
                    "criticality": "high"
                })
            attachment = raw.get('attachment')
            if attachment and attachment.get('instanceId'):
                dependencies.append({
                    "source_id": source_id,
                    "target_id": get_component_id("AWS::EC2::Instance", attachment.get('instanceId')),
                    "relationship_type": "depends_on",
                    "criticality": "high"
                })
                    
    return dependencies

def main():
    try:
        session = boto3.Session()
        region = session.region_name or "us-east-1"
        client = session.client('config', region_name=region)
        
        print(f"AWS Region: {region}")
        print("Discovering resources via aws_sync...")
        
        # This will call the underlying boto3 APIs configured in aws_sync.py
        raw_results, normalized_resources = aws_sync.discover_resources(client, region)
        
        components = []
        for r in normalized_resources:
            components.append(resource_to_component(r))
            
        dependencies = extract_dependencies(normalized_resources)
        
        print("\n--- Components by InfraTwin Type ---")
        counts = {}
        for c in components:
            t = c['type']
            counts[t] = counts.get(t, 0) + 1
        
        if not counts:
            print("No components mapped.")
        for k, v in counts.items():
            print(f"{k.capitalize()}: {v}")
            
        print("\n--- Extracted Dependencies ---")
        if not dependencies:
            print("No dependencies found.")
        for d in dependencies:
            print(f"{d['source_id']} --[{d['relationship_type']}]--> {d['target_id']}")
            
        print("\n--- Sample Components ---")
        for c in components[:10]:
            print(f"- {c['id']} ({c['name']}) [Type: {c['type']}]")
            
    except Exception as e:
        print(f"Error executing aws_mapper: {e}")

if __name__ == "__main__":
    main()
